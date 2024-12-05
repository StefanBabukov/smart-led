import time
import random
import ctypes
from threading import Thread, Event
from gpiozero import Button
from rpi_ws281x import PixelStrip, Color
import evdev
from pacifica import pacifica_step
from animations import *
from static_mode import StaticMode
from fire import fire_step
from color_bounce import color_bounce_step  # Ensure this follows the same pattern (no loops/sleeps)
from led_operations import set_all

# LED strip configuration
LED_COUNT = 300       # Number of LED pixels.
LED_PIN = 18          # GPIO pin connected to the pixels (must support PWM!).
LED_FREQ_HZ = 800000  # LED signal frequency in hertz (usually 800khz)
LED_DMA = 10          # DMA channel to use for generating signal (try 10)
LED_BRIGHTNESS = 255  # Set to 0 for darkest and 255 for brightest
LED_INVERT = False    # True to invert the signal (when using NPN transistor level shift)
LED_CHANNEL = 0       # Set to 1 for GPIOs 13,19,41,45,53

effect_stop_event = Event()

selected_effect = -1
current_mode = 'animation'
current_command = 0
current_effect_thread = None

# Initialize the LED strip
strip = PixelStrip(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)
strip.begin()

# Initialize static mode handler
static_mode = StaticMode(strip)

def get_ir_device():
    devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
    for device in devices:
        if device.name == "gpio_ir_recv":
            print("Using device", device.path, "\n")
            return device
    print("No IR device found!")
    return None

ir_device = get_ir_device()

# Debounce settings
DEBOUNCE_DELAY = 0.2
last_command_time = 0

def handle_ir():
    global current_command, last_command_time
    while True:
        event = ir_device.read_one()
        if event and event.value:
            current_time = time.time()
            current_debounce = DEBOUNCE_DELAY if current_mode == 'animation' else 0
            if current_time - last_command_time > current_debounce:
                current_command = event.value
                print("Received command", event.value)
                last_command_time = current_time
        # Add a small delay to prevent tight looping that can cause CPU spikes
        time.sleep(0.01)

def run_animation(effect_function, *args, **kwargs):
    """
    Run a given effect function in a loop until effect_stop_event is set.
    Use a stable frame rate delay for smoother animations.
    """
    # Target frame time (e.g. 20ms for ~50 FPS)
    frame_time = 0.02  
    while not effect_stop_event.is_set():
        start = time.time()
        effect_function(strip, *args, **kwargs)
        strip.show()
        elapsed = time.time() - start
        # Sleep to maintain stable frame rate if there's time left in the frame
        if elapsed < frame_time:
            time.sleep(frame_time - elapsed)

def start_effect(effect_function, *args, **kwargs):
    global current_effect_thread
    # Stop current effect if running
    effect_stop_event.set()
    if current_effect_thread and current_effect_thread.is_alive():
        current_effect_thread.join()
    effect_stop_event.clear()

    # Start new effect thread
    current_effect_thread = Thread(target=run_animation, args=(effect_function, *args), kwargs=kwargs)
    current_effect_thread.daemon = True
    current_effect_thread.start()

def no_op(strip, *args, **kwargs):
    pass

# Define wheel_step for the previously missing effect
def wheel_step(strip, c1=(255,0,0), c2=(0,255,0), step=500):
    # Simple wheel effect: just rotate through colors
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
    3: lambda: start_effect(halloween_eyes_step, 255, 0, 0, 1, 4, True, 5, 50, 1000),
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
    15: lambda: start_effect(fire_step, 55, 120),
    16: lambda: start_effect(bouncing_colored_balls_step, 1, [(255, 0, 0)], False),
    17: lambda: start_effect(bouncing_colored_balls_step, 20, [(255, 0, 0), (255, 255, 255), (0, 0, 255)], False),
    18: lambda: start_effect(meteor_rain_step, 255, 255, 255, 10, 64, True, 30),
    19: lambda: start_effect(fire_step, 55, 120)  # Another fire variant
}

def run_effect(selected_effect):
    print("Running effect:", selected_effect)
    effects.get(selected_effect, lambda: None)()

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
    set_all(strip, 0, 0, 0)  # Turn off LEDs

mode_commands = {
    'animation': {
        'next': next_effect,
        'previous': previous_effect
    },
    'static': {
        'next': static_mode.increase_hue,
        'previous': static_mode.decrease_hue,
        'up': static_mode.increase_brightness,
        'down': static_mode.decrease_brightness
    }
}

animations_enabled = True

def ir_listener():
    global current_command, selected_effect, animations_enabled, current_mode
    print('IR Listener thread started')
    selected_effect = 0
    run_effect(selected_effect)  # Start with the first effect
    while True:
        if current_command != 0:
            print(f"Current command: {current_command}")
            if current_command == 69:  # Animation mode
                set_all(strip, 0, 0, 0)
                current_mode = 'animation'
            elif current_command == 70:  # Static mode
                stop_animations()
                current_mode = 'static'
            elif current_command == 90:  # NEXT
                if current_mode == 'animation':
                    mode_commands['animation']['next']()
                else:
                    mode_commands['static']['next']()
            elif current_command == 8:   # PREVIOUS
                if current_mode == 'animation':
                    mode_commands['animation']['previous']()
                else:
                    mode_commands['static']['previous']()
            elif current_command == 28:  # TOGGLE ON/OFF
                animations_enabled = not animations_enabled
                if not animations_enabled:
                    stop_animations()
                else:
                    if current_mode == 'animation':
                        run_effect(selected_effect)
            elif current_command == 24:  # UP in static mode
                if current_mode == 'static' and 'up' in mode_commands['static']:
                    mode_commands['static']['up']()
            elif current_command == 82:  # DOWN in static mode
                if current_mode == 'static' and 'down' in mode_commands['static']:
                    mode_commands['static']['down']()

            current_command = 0
            time.sleep(0.1)  # Slight pause to avoid command flooding

if __name__ == "__main__":
    print("Setup complete. Waiting for IR input...")
    ir_thread = Thread(target=handle_ir)
    ir_thread.daemon = True
    ir_thread.start()

    effect_thread = Thread(target=ir_listener)
    effect_thread.daemon = True
    effect_thread.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Program stopped by user")
        stop_animations()
    finally:
        strip._cleanup()
