import asyncio
import functools
import json
import time
from threading import Event, Lock, Thread

from rpi_ws281x import PixelStrip

from ai_animations import (
    call_ollama,
    compile_ai_animation,
    delete_ai_animation,
    extract_code,
    load_all_ai_animations,
    make_safe_step,
    prompt_to_name,
    save_ai_animation,
    validate_code,
)
from animations import *
from fire import fire_step
from game_mode import ZombieGameMode
from halloween_scene import halloween_scene_step, reset_halloween_scene_state
from led_operations import fill_all, get_pixel, set_pixel
from pacifica import pacifica_step
from static_mode import StaticMode
from xmas_scene import reset_xmas_scene_state, xmas_scene_step

try:
    import websockets
except ImportError:
    import sys

    sys.exit("websockets not installed. Run: sudo pip3 install websockets --break-system-packages")


# LED strip configuration
LED_COUNT = 300
LED_GPIO_PIN = 18  # PWM pin; setup.sh disables onboard audio to avoid animation flicker.
LED_FREQ_HZ = 800000
LED_DMA = 10
LED_BRIGHTNESS = 255
LED_INVERT = False
LED_CHANNEL = 0
BALL_COUNT_MIN = 1
BALL_COUNT_MAX = 12

effect_stop_event = Event()
strip_lock = Lock()
server_loop = None

selected_effect = -1
current_mode = "animation"
current_effect_thread = None
animations_enabled = True
current_brightness = LED_BRIGHTNESS

# Set up the LED strip
strip = PixelStrip(LED_COUNT, LED_GPIO_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)
strip.begin()

# Initialize static mode handler
static_mode = StaticMode(strip)
zombie_game = ZombieGameMode(LED_COUNT)

# Connected WebSocket clients
connected_clients = set()
command_lock = asyncio.Lock()

animation_config = {
    "running_lights": {"color": (255, 0, 0)},
    "color_wipe": {"color": (0, 255, 0)},
    "theater_chase": {"color": (255, 0, 0)},
    "bouncing_balls": {"count": 3},
}

# AI-generated animation state
ai_generating = False
ai_preview_state = None  # {"name", "prompt", "code", "step_fn"} or None
ai_previous_effect = None  # effect index to restore on discard
ai_progress_tokens = 0  # token count during generation, broadcast to clients
AI_EFFECT_DEFINITIONS = []  # loaded from disk at startup


def running_lights_current_step(active_strip):
    running_lights_step(active_strip, *animation_config["running_lights"]["color"])


def color_wipe_current_step(active_strip):
    color_wipe_step(active_strip, *animation_config["color_wipe"]["color"])


def theater_chase_current_step(active_strip):
    theater_chase_step(active_strip, *animation_config["theater_chase"]["color"])


def bouncing_balls_current_step(active_strip):
    bouncing_colored_balls_step(
        active_strip,
        animation_config["bouncing_balls"]["count"],
        BALL_COLORS,
        False,
    )


def meteor_current_step(active_strip):
    meteor_rain_step(active_strip, 255, 255, 255, 8, 60, False, 30)


def game_current_step(active_strip):
    zombie_game.step(active_strip)


EFFECT_DEFINITIONS = [
    {
        "key": "fade_in_out",
        "name": "Fade In Out (Red)",
        "runner": lambda: start_effect(fade_in_out_step, 255, 0, 0),
    },
    {
        "key": "pacifica",
        "name": "Pacifica",
        "runner": lambda: start_effect(pacifica_step),
    },
    {
        "key": "color_wheel",
        "name": "Color Wheel",
        "runner": lambda: start_effect(wheel_step, (255, 0, 0), (0, 255, 0), 500),
    },
    {
        "key": "halloween_scene",
        "name": "Halloween Scene",
        "runner": lambda: start_effect(halloween_scene_step),
    },
    {
        "key": "split_cyclones",
        "name": "Split Cyclones",
        "runner": lambda: start_effect(split_cyclones_step),
    },
    {
        "key": "twinkle_red",
        "name": "Twinkle (Red)",
        "runner": lambda: start_effect(twinkle_step, 255, 0, 0, 10, False),
    },
    {
        "key": "twinkle_random",
        "name": "Twinkle Random",
        "runner": lambda: start_effect(twinkle_random_step, 300, False),
    },
    {
        "key": "sparkle",
        "name": "Eiffel Sparkle",
        "runner": lambda: start_effect(sparkle_step, 255, 255, 255),
    },
    {
        "key": "snow_sparkle",
        "name": "Snow Sparkle",
        "runner": lambda: start_effect(snow_sparkle_step, 16, 16, 16),
    },
    {
        "key": "running_lights",
        "name": "Running Lights",
        "runner": lambda: start_effect(running_lights_current_step),
        "supports_color": True,
    },
    {
        "key": "color_wipe",
        "name": "Color Wipe",
        "runner": lambda: start_effect(color_wipe_current_step),
        "supports_color": True,
    },
    {
        "key": "rainbow_cycle",
        "name": "Rainbow Cycle",
        "runner": lambda: start_effect(rainbow_cycle_step),
    },
    {
        "key": "theater_chase",
        "name": "Theater Chase",
        "runner": lambda: start_effect(theater_chase_current_step),
        "supports_color": True,
    },
    {
        "key": "theater_chase_rainbow",
        "name": "Theater Chase Rainbow",
        "runner": lambda: start_effect(theater_chase_rainbow_step),
    },
    {
        "key": "fire",
        "name": "Fire",
        "runner": lambda: start_effect(fire_step),
    },
    {
        "key": "bouncing_balls",
        "name": "Bouncing Balls",
        "runner": lambda: start_effect(bouncing_balls_current_step),
        "supports_ball_count": True,
    },
    {
        "key": "meteor_rain",
        "name": "Meteor Rain",
        "runner": lambda: start_effect(meteor_current_step),
    },
    {
        "key": "death_show",
        "name": "Death Show",
        "runner": lambda: start_effect(death_show_step),
    },
    {
        "key": "christmas_scene",
        "name": "Christmas Scene",
        "runner": lambda: start_effect(xmas_scene_step),
    },
]

EFFECT_CATALOG = []


def all_effects():
    return EFFECT_DEFINITIONS + AI_EFFECT_DEFINITIONS


def rebuild_effect_catalog():
    global EFFECT_CATALOG
    effects = all_effects()
    EFFECT_CATALOG = [
        {
            "index": index,
            "key": effect["key"],
            "name": effect["name"],
            "supports_color": bool(effect.get("supports_color")),
            "supports_ball_count": bool(effect.get("supports_ball_count")),
            "is_ai_generated": bool(effect.get("is_ai_generated")),
            "ai_id": effect.get("ai_id"),
        }
        for index, effect in enumerate(effects)
    ]


def rebuild_ai_effects():
    """Load saved AI animations from disk and rebuild the combined catalog."""
    global AI_EFFECT_DEFINITIONS
    saved = load_all_ai_animations()
    AI_EFFECT_DEFINITIONS = []
    for anim in saved:
        try:
            step_fn, _state = compile_ai_animation(anim["code"])
        except Exception:
            continue
        AI_EFFECT_DEFINITIONS.append({
            "key": f"ai_{anim['id']}",
            "name": f"AI: {anim['name']}",
            "runner": lambda fn=step_fn: start_effect(fn),
            "supports_color": False,
            "supports_ball_count": False,
            "is_ai_generated": True,
            "ai_id": anim["id"],
        })
    rebuild_effect_catalog()


def current_effect_definition():
    effects = all_effects()
    if 0 <= selected_effect < len(effects):
        return effects[selected_effect]
    return None


def reset_states():
    fade_in_out_state.update({"direction": 1, "brightness": 0})
    running_lights_state.update({"position": 0})
    twinkle_state.update({"pixels": []})
    twinkle_random_state.update({"used_indices": []})
    sparkle_state.update({"initialized": False, "flash_levels": []})
    snow_sparkle_state.update({"pixels": [], "timer": 0, "base_color": (16, 16, 16)})
    cylon_state.update({"pos": 0, "forward": True})
    split_cyclones_state.update({"depth": 0, "phase": 1, "progress": 0.0, "max_depth": 0})
    color_wipe_state.update({"index": 0, "done": False, "last_color": None})
    rainbow_cycle_state.update({"step": 0})
    theater_chase_state.update({"index": 0})
    theater_chase_rainbow_state.update({"step": 0, "index": 0})
    bouncing_balls_state.update(
        {
            "init": False,
            "ball_count": 0,
            "positions": [],
            "velocities": [],
            "launch_times": [],
            "colors": [],
            "gravity": 650.0,
            "restitution": [],
            "last_time": 0.0,
            "settled_since": None,
        }
    )
    meteor_rain_state.update({"pos": 0.0, "speed": 2.2})
    wheel_step_state.update({"pos": 0})
    reset_death_show_state()


def run_animation(effect_function, *args, **kwargs):
    frame_time = 0.02  # ~50 FPS
    last_state_push = 0.0
    while not effect_stop_event.is_set():
        start = time.monotonic()
        with strip_lock:
            effect_function(strip, *args, **kwargs)
            strip.show()
        if current_mode == "game" and server_loop and connected_clients and (start - last_state_push) >= 0.25:
            asyncio.run_coroutine_threadsafe(broadcast_state(), server_loop)
            last_state_push = start
        elapsed = time.monotonic() - start
        if elapsed < frame_time:
            time.sleep(frame_time - elapsed)


def start_effect(effect_function, *args, **kwargs):
    global current_effect_thread
    effect_stop_event.set()
    if current_effect_thread and current_effect_thread.is_alive():
        current_effect_thread.join()

    reset_states()
    if effect_function == halloween_scene_step:
        reset_halloween_scene_state()
    if effect_function == xmas_scene_step:
        reset_xmas_scene_state()

    with strip_lock:
        fill_all(strip, 0, 0, 0)
        strip.show()

    effect_stop_event.clear()
    current_effect_thread = Thread(target=run_animation, args=(effect_function, *args), kwargs=kwargs)
    current_effect_thread.daemon = True
    current_effect_thread.start()


def run_effect(idx):
    effects = all_effects()
    if 0 <= idx < len(effects):
        effects[idx]["runner"]()


def set_effect_by_index(idx):
    global selected_effect
    effects = all_effects()
    if 0 <= idx < len(effects):
        selected_effect = idx
        if current_mode == "animation" and animations_enabled:
            run_effect(selected_effect)
        return True
    return False


def start_game_mode():
    zombie_game.reset()
    start_effect(game_current_step)


def next_effect():
    global selected_effect
    selected_effect = (selected_effect + 1) % len(all_effects())
    run_effect(selected_effect)


def previous_effect():
    global selected_effect
    selected_effect = (selected_effect - 1) % len(all_effects())
    run_effect(selected_effect)


def stop_animations():
    effect_stop_event.set()
    if current_effect_thread and current_effect_thread.is_alive():
        current_effect_thread.join()
    with strip_lock:
        fill_all(strip, 0, 0, 0)
        strip.show()


def change_brightness(up=True):
    global current_brightness
    step = 20
    if up:
        current_brightness = min(255, current_brightness + step)
    else:
        current_brightness = max(0, current_brightness - step)
    with strip_lock:
        strip.setBrightness(current_brightness)
        strip.show()


mode_commands = {
    "animation": {
        "next": next_effect,
        "previous": previous_effect,
        "up": lambda: change_brightness(up=True),
        "down": lambda: change_brightness(up=False),
    },
    "static": {
        "next": static_mode.increase_hue,
        "previous": static_mode.decrease_hue,
        "up": lambda: change_brightness(up=True),
        "down": lambda: change_brightness(up=False),
    },
    "game": {
        "next": lambda: None,
        "previous": lambda: None,
        "up": lambda: change_brightness(up=True),
        "down": lambda: change_brightness(up=False),
    },
}


def get_state_dict():
    state = {
        "type": "state",
        "mode": current_mode,
        "effect_index": selected_effect,
        "brightness": current_brightness,
        "enabled": animations_enabled,
        "total_effects": len(all_effects()),
        "available_effects": EFFECT_CATALOG,
        "ai_generating": ai_generating,
        "ai_previewing": ai_preview_state is not None,
        "ai_preview_name": ai_preview_state["name"] if ai_preview_state else None,
        "ai_progress_tokens": ai_progress_tokens,
        "effect_key": None,
        "supports_animation_color": False,
        "supports_ball_count": False,
        "animation_color": None,
        "ball_count": animation_config["bouncing_balls"]["count"],
        "game_score": 0,
        "game_wave": 1,
        "game_over": False,
    }

    if current_mode == "animation":
        effect = current_effect_definition()
        if effect:
            state["effect_name"] = effect["name"]
            state["effect_key"] = effect["key"]
            state["supports_animation_color"] = bool(effect.get("supports_color"))
            state["supports_ball_count"] = bool(effect.get("supports_ball_count"))
            if effect.get("supports_color"):
                r, g, b = animation_config[effect["key"]]["color"]
                state["animation_color"] = {"r": r, "g": g, "b": b}
            if effect.get("supports_ball_count"):
                state["ball_count"] = animation_config["bouncing_balls"]["count"]
        else:
            state["effect_name"] = "Unknown"
            state["effect_key"] = None
            state["supports_animation_color"] = False
            state["supports_ball_count"] = False
    elif current_mode == "static":
        r, g, b = static_mode.get_rgb()
        state["effect_name"] = f"Static (R{r} G{g} B{b})"
        state["color"] = {"r": r, "g": g, "b": b}
    else:
        snapshot = zombie_game.snapshot()
        state["effect_name"] = "Zombie Defense"
        state["game_score"] = snapshot["score"]
        state["game_wave"] = snapshot["wave"]
        state["game_over"] = snapshot["game_over"]

    return state


async def broadcast_state():
    if connected_clients:
        msg = json.dumps(get_state_dict())
        await asyncio.gather(*(client.send(msg) for client in connected_clients), return_exceptions=True)


def current_animation_key():
    effect = current_effect_definition()
    return effect["key"] if effect else None


def update_animation_color(r, g, b):
    key = current_animation_key()
    if key in ("running_lights", "color_wipe", "theater_chase"):
        animation_config[key]["color"] = (r, g, b)
        if key == "color_wipe":
            color_wipe_state.update({"index": 0, "done": False, "last_color": None})


def adjust_ball_count(delta):
    current_count = animation_config["bouncing_balls"]["count"]
    animation_config["bouncing_balls"]["count"] = max(
        BALL_COUNT_MIN,
        min(BALL_COUNT_MAX, current_count + delta),
    )


async def _broadcast_ai_progress(count):
    """Send a token-count progress update to all connected clients."""
    if connected_clients:
        msg = json.dumps({"type": "ai_progress", "tokens": count})
        await asyncio.gather(*(c.send(msg) for c in connected_clients), return_exceptions=True)


async def _ai_generate_task(prompt, websocket):
    """Run AI generation in a background thread and handle the result."""
    global ai_generating, ai_preview_state, ai_progress_tokens

    loop = asyncio.get_event_loop()
    ai_progress_tokens = 0

    def on_token(count, _partial):
        global ai_progress_tokens
        ai_progress_tokens = count
        asyncio.run_coroutine_threadsafe(_broadcast_ai_progress(count), loop)

    try:
        response_text = await loop.run_in_executor(
            None, functools.partial(call_ollama, prompt, on_token=on_token)
        )
        code = extract_code(response_text)
        if not code:
            raise ValueError("No valid code in AI response. Try rephrasing your prompt.")

        ok, err = validate_code(code)
        if not ok:
            raise ValueError(f"Generated code is unsafe: {err}")

        step_fn, _state = compile_ai_animation(code)

        # Wrap with runtime safety
        runtime_error_sent = [False]

        def on_runtime_error(error_msg):
            if not runtime_error_sent[0]:
                runtime_error_sent[0] = True
                asyncio.run_coroutine_threadsafe(
                    _send_ai_error(websocket, f"Animation crashed: {error_msg}"),
                    loop,
                )

        safe_fn = make_safe_step(step_fn, on_runtime_error)
        name = prompt_to_name(prompt)

        ai_preview_state = {
            "name": name,
            "prompt": prompt,
            "code": code,
            "step_fn": safe_fn,
        }
        ai_generating = False
        ai_progress_tokens = 0

        # Start previewing the animation
        start_effect(safe_fn)

        msg = json.dumps({
            "type": "ai_result",
            "status": "previewing",
            "name": name,
            "prompt": prompt,
        })
        try:
            await websocket.send(msg)
        except Exception:
            pass
        await broadcast_state()

    except Exception as exc:
        ai_generating = False
        ai_preview_state = None
        ai_progress_tokens = 0
        msg = json.dumps({
            "type": "ai_result",
            "status": "error",
            "error": str(exc),
        })
        try:
            await websocket.send(msg)
        except Exception:
            pass
        await broadcast_state()


async def _send_ai_error(websocket, error_msg):
    """Send a runtime error message to the client."""
    global ai_preview_state
    ai_preview_state = None
    msg = json.dumps({
        "type": "ai_result",
        "status": "runtime_error",
        "error": error_msg,
    })
    try:
        await websocket.send(msg)
    except Exception:
        pass
    await broadcast_state()


async def handle_command(action, data, websocket=None):
    global current_mode, animations_enabled, selected_effect, current_brightness
    global ai_generating, ai_preview_state, ai_previous_effect
    should_broadcast = True

    if action == "mode_animation":
        current_mode = "animation"
        if animations_enabled:
            run_effect(selected_effect)
        else:
            with strip_lock:
                fill_all(strip, 0, 0, 0)
                strip.show()
    elif action == "mode_static":
        stop_animations()
        current_mode = "static"
    elif action == "mode_game":
        current_mode = "game"
        if animations_enabled:
            start_game_mode()
        else:
            with strip_lock:
                fill_all(strip, 0, 0, 0)
                strip.show()
    elif action in ("next", "previous", "up", "down"):
        mode_commands[current_mode][action]()
    elif action == "toggle":
        animations_enabled = not animations_enabled
        if not animations_enabled:
            stop_animations()
        else:
            if current_mode == "animation":
                run_effect(selected_effect)
            elif current_mode == "game":
                start_game_mode()
            else:
                with strip_lock:
                    static_mode.show_color()
                    strip.show()
    elif action == "set_color":
        r = max(0, min(255, int(data.get("r", 255))))
        g = max(0, min(255, int(data.get("g", 255))))
        b = max(0, min(255, int(data.get("b", 255))))
        if current_mode in ("animation", "game"):
            stop_animations()
        current_mode = "static"
        animations_enabled = True
        with strip_lock:
            static_mode.set_rgb(r, g, b)
    elif action == "set_animation_color":
        r = max(0, min(255, int(data.get("r", 255))))
        g = max(0, min(255, int(data.get("g", 255))))
        b = max(0, min(255, int(data.get("b", 255))))
        update_animation_color(r, g, b)
    elif action == "set_effect":
        try:
            index = int(data.get("index", selected_effect))
        except (TypeError, ValueError):
            index = selected_effect
        set_effect_by_index(index)
    elif action == "increase_ball_count":
        adjust_ball_count(1)
    elif action == "decrease_ball_count":
        adjust_ball_count(-1)
    elif action == "move_left":
        if current_mode == "game":
            zombie_game.move_left()
    elif action == "move_right":
        if current_mode == "game":
            zombie_game.move_right()
    elif action == "shoot_left":
        if current_mode == "game":
            zombie_game.shoot_left()
    elif action == "shoot_right":
        if current_mode == "game":
            zombie_game.shoot_right()
    elif action == "set_brightness":
        value = max(0, min(255, int(data.get("value", current_brightness))))
        current_brightness = value
        with strip_lock:
            strip.setBrightness(current_brightness)
            strip.show()
    elif action == "set_pixel_range":
        start = max(0, min(LED_COUNT - 1, int(data.get("start", 0))))
        end = max(0, min(LED_COUNT - 1, int(data.get("end", start))))
        r = max(0, min(255, int(data.get("r", 255))))
        g = max(0, min(255, int(data.get("g", 255))))
        b = max(0, min(255, int(data.get("b", 255))))
        if current_mode in ("animation", "game"):
            stop_animations()
        current_mode = "static"
        animations_enabled = True
        with strip_lock:
            for i in range(start, end + 1):
                set_pixel(strip, i, r, g, b)
            strip.show()
        should_broadcast = False
    elif action == "ai_generate":
        prompt = str(data.get("prompt", "")).strip()
        if not prompt:
            should_broadcast = False
        elif len(prompt) > 500:
            should_broadcast = False
        else:
            ai_generating = True
            ai_previous_effect = selected_effect
            await broadcast_state()
            should_broadcast = False
            asyncio.get_event_loop().create_task(
                _ai_generate_task(prompt, websocket)
            )
    elif action == "ai_save":
        if ai_preview_state:
            name = str(data.get("name", ai_preview_state["name"])).strip()
            if not name:
                name = ai_preview_state["name"]
            save_ai_animation(name, ai_preview_state["prompt"], ai_preview_state["code"])
            ai_preview_state = None
            rebuild_ai_effects()
            # Select the newly saved animation (last in AI list)
            selected_effect = len(all_effects()) - 1
            if current_mode == "animation" and animations_enabled:
                run_effect(selected_effect)
        else:
            should_broadcast = False
    elif action == "ai_discard":
        if ai_preview_state:
            ai_preview_state = None
            if ai_previous_effect is not None:
                selected_effect = ai_previous_effect
                ai_previous_effect = None
                if current_mode == "animation" and animations_enabled:
                    run_effect(selected_effect)
        else:
            should_broadcast = False
    elif action == "ai_delete":
        ai_id = str(data.get("ai_id", ""))
        if ai_id and delete_ai_animation(ai_id):
            # If deleted effect was playing, switch to first built-in
            effect = current_effect_definition()
            if effect and effect.get("ai_id") == ai_id:
                selected_effect = 0
                if current_mode == "animation" and animations_enabled:
                    run_effect(selected_effect)
            rebuild_ai_effects()
            # Clamp selected_effect if it's now out of range
            if selected_effect >= len(all_effects()):
                selected_effect = max(0, len(all_effects()) - 1)
        else:
            should_broadcast = False
    elif action == "get_strip_colors":
        should_broadcast = False
    elif action == "get_state":
        pass

    if should_broadcast:
        await broadcast_state()


async def handler(websocket):
    connected_clients.add(websocket)
    try:
        await websocket.send(json.dumps(get_state_dict()))
        async for message in websocket:
            try:
                data = json.loads(message)
                action = data.get("action", "")
            except (json.JSONDecodeError, AttributeError):
                continue

            async with command_lock:
                await handle_command(action, data, websocket)
                if action == "get_strip_colors":
                    with strip_lock:
                        colors = [list(get_pixel(strip, i)) for i in range(LED_COUNT)]
                    await websocket.send(json.dumps({"type": "strip_colors", "colors": colors}))
                elif action == "get_state":
                    await websocket.send(json.dumps(get_state_dict()))

    except websockets.ConnectionClosed:
        pass
    finally:
        connected_clients.discard(websocket)


async def main():
    global selected_effect, server_loop
    server_loop = asyncio.get_running_loop()
    rebuild_ai_effects()
    selected_effect = 0
    run_effect(selected_effect)

    async with websockets.serve(handler, "0.0.0.0", 8765):
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        stop_animations()
    finally:
        strip._cleanup()
