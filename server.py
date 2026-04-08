import time
import random
import ctypes
import asyncio
import json
from threading import Thread, Event
from rpi_ws281x import PixelStrip, Color

from pacifica import pacifica_step
from animations import *
from static_mode import StaticMode
from fire import fire_step
from color_bounce import color_bounce_step
from led_operations import set_all
from halloween_scene import halloween_scene_step, reset_halloween_scene_state
from xmas_scene import xmas_scene_step, reset_xmas_scene_state

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

effect_stop_event = Event()

selected_effect = -1
current_mode = 'animation'
current_effect_thread = None
animations_enabled = True
current_brightness = LED_BRIGHTNESS

# Set up the LED strip
strip = PixelStrip(LED_COUNT, LED_GPIO_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)
strip.begin()

# Initialize static mode handler
static_mode = StaticMode(strip)

# Connected WebSocket clients
connected_clients = set()
command_lock = asyncio.Lock()


def run_animation(effect_function, *args, **kwargs):
    frame_time = 0.02  # ~50 FPS
    while not effect_stop_event.is_set():
        start = time.time()
        effect_function(strip, *args, **kwargs)
        strip.show()
        elapsed = time.time() - start
        if elapsed < frame_time:
            time.sleep(frame_time - elapsed)


def reset_states():
    fade_in_out_state.update({'direction': 1, 'brightness': 0})
    running_lights_state.update({'position': 0})
    twinkle_state.update({'pixels': []})
    twinkle_random_state.update({'used_indices': []})
    sparkle_state.update({'on_pixel': None, 'timer': 0})
    snow_sparkle_state.update({'pixels': [], 'timer': 0, 'base_color': (16, 16, 16)})
    cylon_state.update({'pos': 0, 'forward': True})
    color_wipe_state.update({'index': 0, 'done': False})
    rainbow_cycle_state.update({'step': 0})
    theater_chase_state.update({'step': 0, 'index': 0})
    theater_chase_rainbow_state.update({'step': 0, 'index': 0})
    bouncing_balls_state.update({'init': False, 'positions': [], 'velocities': [], 'clock': [], 'colors': [], 'gravity': -9.81, 'startTime': 0})
    meteor_rain_state.update({'pos': 0, 'direction': 1, 'initialized': False, 'trail_length': 10, 'red': 255, 'green': 255, 'blue': 255, 'meteor_size': 5, 'random_decay': True, 'speed_delay': 30})
    wheel_step_state.update({'pos': 0})


def start_effect(effect_function, *args, **kwargs):
    global current_effect_thread
    effect_stop_event.set()
    if current_effect_thread and current_effect_thread.is_alive():
        current_effect_thread.join()

    set_all(strip, 0, 0, 0)
    strip.show()
    reset_states()

    if effect_function == halloween_scene_step:
        reset_halloween_scene_state()
    if effect_function == xmas_scene_step:
        reset_xmas_scene_state()

    effect_stop_event.clear()

    current_effect_thread = Thread(target=run_animation, args=(effect_function, *args), kwargs=kwargs)
    current_effect_thread.daemon = True
    current_effect_thread.start()


def wheel_step(strip, c1=(255, 0, 0), c2=(0, 255, 0), step=500):
    st = wheel_step_state
    num_leds = strip.numPixels()
    pos = st['pos']
    for i in range(num_leds):
        ratio = ((i + pos) % step) / step
        r = int(c1[0] * (1 - ratio) + c2[0] * ratio)
        g = int(c1[1] * (1 - ratio) + c2[1] * ratio)
        b = int(c1[2] * (1 - ratio) + c2[2] * ratio)
        set_pixel(strip, i, r, g, b)
    st['pos'] += 1


effects = {
    0: lambda: start_effect(fade_in_out_step, 255, 0, 0),
    1: lambda: start_effect(pacifica_step),
    2: lambda: start_effect(wheel_step, (255, 0, 0), (0, 255, 0), 500),
    3: lambda: start_effect(halloween_scene_step),
    4: lambda: start_effect(cylon_bounce_step, 255, 0, 0, 4, 10, 50),
    5: lambda: start_effect(cylon_bounce_step, 255, 0, 0, 8, 10, 50),
    6: lambda: start_effect(twinkle_step, 255, 0, 0, 10, False),
    7: lambda: start_effect(twinkle_random_step, 300, False),
    8: lambda: start_effect(sparkle_step, 255, 255, 255),
    9: lambda: start_effect(snow_sparkle_step, 16, 16, 16),
    10: lambda: start_effect(running_lights_step, 255, 0, 0),
    11: lambda: start_effect(color_wipe_step, 0, 255, 0),
    12: lambda: start_effect(rainbow_cycle_step),
    13: lambda: start_effect(theater_chase_step, 255, 0, 0),
    14: lambda: start_effect(theater_chase_rainbow_step),
    15: lambda: start_effect(fire_step, 80, 220),
    16: lambda: start_effect(bouncing_colored_balls_step, 1, [(255, 0, 0)], False),
    17: lambda: start_effect(bouncing_colored_balls_step, 20, [(255, 0, 0), (255, 255, 255), (0, 0, 255)], False),
    18: lambda: start_effect(meteor_rain_step, 255, 255, 255, 10, 64, True, 30),
    19: lambda: start_effect(xmas_scene_step),
}

effect_names = [
    "Fade In Out (Red)",
    "Pacifica",
    "Color Wheel",
    "Halloween Scene",
    "Cylon Bounce (Narrow)",
    "Cylon Bounce (Wide)",
    "Twinkle (Red)",
    "Twinkle Random",
    "Sparkle",
    "Snow Sparkle",
    "Running Lights (Red)",
    "Color Wipe (Green)",
    "Rainbow Cycle",
    "Theater Chase (Red)",
    "Theater Chase Rainbow",
    "Fire",
    "Bouncing Ball",
    "Bouncing Balls",
    "Meteor Rain",
    "Christmas Scene",
]


def run_effect(idx):
    effects.get(idx, lambda: None)()


def next_effect():
    global selected_effect
    selected_effect = (selected_effect + 1) % len(effects)
    run_effect(selected_effect)


def previous_effect():
    global selected_effect
    selected_effect = (selected_effect - 1) % len(effects)
    run_effect(selected_effect)


def stop_animations():
    effect_stop_event.set()
    if current_effect_thread and current_effect_thread.is_alive():
        current_effect_thread.join()
    set_all(strip, 0, 0, 0)
    strip.show()


def change_brightness(up=True):
    global current_brightness
    step = 20
    if up:
        current_brightness = min(255, current_brightness + step)
    else:
        current_brightness = max(0, current_brightness - step)
    strip.setBrightness(current_brightness)
    strip.show()


mode_commands = {
    'animation': {
        'next': next_effect,
        'previous': previous_effect,
        'up': lambda: change_brightness(up=True),
        'down': lambda: change_brightness(up=False),
    },
    'static': {
        'next': static_mode.increase_hue,
        'previous': static_mode.decrease_hue,
        'up': lambda: change_brightness(up=True),
        'down': lambda: change_brightness(up=False),
    },
}


# --- WebSocket server ---

def get_state_dict():
    if current_mode == 'animation':
        name = effect_names[selected_effect] if 0 <= selected_effect < len(effect_names) else "Unknown"
    else:
        r, g, b = static_mode.get_rgb()
        name = f"Static (R{r} G{g} B{b})"
    state = {
        "type": "state",
        "mode": current_mode,
        "effect_index": selected_effect,
        "effect_name": name,
        "brightness": current_brightness,
        "enabled": animations_enabled,
        "total_effects": len(effects),
    }
    if current_mode == 'static':
        state["color"] = {"r": r, "g": g, "b": b}
    return state


async def broadcast_state():
    if connected_clients:
        msg = json.dumps(get_state_dict())
        await asyncio.gather(
            *(client.send(msg) for client in connected_clients),
            return_exceptions=True,
        )


async def handle_command(action, data):
    global current_mode, animations_enabled, selected_effect, current_brightness

    if action == "mode_animation":
        set_all(strip, 0, 0, 0)
        strip.show()
        current_mode = 'animation'
    elif action == "mode_static":
        stop_animations()
        current_mode = 'static'
    elif action in ("next", "previous", "up", "down"):
        mode_commands[current_mode][action]()
    elif action == "toggle":
        animations_enabled = not animations_enabled
        if not animations_enabled:
            stop_animations()
        else:
            if current_mode == 'animation':
                run_effect(selected_effect)
            elif current_mode == 'static':
                static_mode.show_color()
    elif action == "set_color":
        r = max(0, min(255, int(data.get("r", 255))))
        g = max(0, min(255, int(data.get("g", 255))))
        b = max(0, min(255, int(data.get("b", 255))))
        if current_mode == 'animation':
            stop_animations()
        current_mode = 'static'
        animations_enabled = True
        static_mode.set_rgb(r, g, b)
    elif action == "set_brightness":
        value = max(0, min(255, int(data.get("value", current_brightness))))
        current_brightness = value
        strip.setBrightness(current_brightness)
        strip.show()
    elif action == "get_state":
        pass  # state is broadcast after every command anyway

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
    except websockets.ConnectionClosed:
        pass
    finally:
        connected_clients.discard(websocket)


async def main():
    global selected_effect
    selected_effect = 0
    run_effect(selected_effect)

    async with websockets.serve(handler, "0.0.0.0", 8765):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        stop_animations()
    finally:
        strip._cleanup()
