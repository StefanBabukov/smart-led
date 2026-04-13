import asyncio
import json
import time
from threading import Event, Lock, Thread

from rpi_ws281x import PixelStrip

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
LED_GPIO_PIN = 18
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


def current_effect_definition():
    if 0 <= selected_effect < len(EFFECT_DEFINITIONS):
        return EFFECT_DEFINITIONS[selected_effect]
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
    if 0 <= idx < len(EFFECT_DEFINITIONS):
        EFFECT_DEFINITIONS[idx]["runner"]()


def start_game_mode():
    zombie_game.reset()
    start_effect(game_current_step)


def next_effect():
    global selected_effect
    selected_effect = (selected_effect + 1) % len(EFFECT_DEFINITIONS)
    run_effect(selected_effect)


def previous_effect():
    global selected_effect
    selected_effect = (selected_effect - 1) % len(EFFECT_DEFINITIONS)
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
        "total_effects": len(EFFECT_DEFINITIONS),
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


async def handle_command(action, data):
    global current_mode, animations_enabled, selected_effect, current_brightness
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
                await handle_command(action, data)
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
