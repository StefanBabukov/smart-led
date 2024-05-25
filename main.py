import time
import random
import ctypes
from threading import Thread, Event
from gpiozero import Button
from rpi_ws281x import PixelStrip, Color
import evdev
from pacifica import pacifica
from animations import *
from static_mode import StaticMode  # Import StaticMode class

animations_enabled = True  

# LED strip configuration
LED_COUNT = 300        # Number of LED pixels.
LED_PIN = 18           # GPIO pin connected to the pixels (must support PWM!).
LED_FREQ_HZ = 800000   # LED signal frequency in hertz (usually 800khz)
LED_DMA = 10           # DMA channel to use for generating signal (try 10)
LED_BRIGHTNESS = 255   # Set to 0 for darkest and 255 for brightest
LED_INVERT = False     # True to invert the signal (when using NPN transistor level shift)
LED_CHANNEL = 0        # 0 or 1
effect_stop_event = Event()

selected_effect = -1
current_mode = 'animation'
current_command = 0
current_effect_thread = None

# Set up the LED strip
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
    print("No device found!")
    return None

ir_device = get_ir_device()

# Debounce settings
DEBOUNCE_DELAY = 0.2  # 200 milliseconds
last_command_time = 0

def handle_ir():
    global current_command, last_command_time
    current_debounce = DEBOUNCE_DELAY
    if current_mode == 'static':
        current_debounce = 0
    while True:
        event = ir_device.read_one()
        if event and event.value:
            current_time = time.time()
            if current_time - last_command_time > current_debounce:
                current_command = event.value
                print("Received command", event.value)
                last_command_time = current_time

def terminate_thread(thread):
    if not thread.is_alive():
        return

    exc = ctypes.py_object(SystemExit)
    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(thread.ident), exc)
    if res == 0:
        raise ValueError("Thread id not found")
    elif res > 1:
        ctypes.pythonapi.PyThreadState_SetAsyncExc(thread.ident, None)
        raise SystemError("PyThreadState_SetAsyncExc failed")

def run_effect(selected_effect):
    print('in run effect')
    global current_effect_thread

    effect_stop_event.set()  # Signal the current effect to stop
    if current_effect_thread:
        terminate_thread(current_effect_thread)  # Terminate the current effect thread

    effect_stop_event.clear()  # Clear the event to start a new effect
    print(f"Running effect: {selected_effect}")
    effects = {
        0: lambda: fade_in_out(strip, 255, 0, 0),
        1: lambda: pacifica(strip, effect_stop_event),  # Integrate pacifica as effect 0
        2: lambda: strobe(strip, 255, 255, 255, 10, 50, 1000),
        3: lambda: halloween_eyes(strip, 255, 0, 0, 1, 4, True, random.randint(5, 50), random.randint(50, 150), random.randint(1000, 10000)),
        4: lambda: cylon_bounce(strip, 255, 0, 0, 4, 10, 50),
        5: lambda: cylon_bounce(strip, 255, 0, 0, 8, 10, 50),
        6: lambda: twinkle(strip, 255, 0, 0, 10, 100, False),
        7: lambda: twinkle_random(strip, 300, 100, False),
        8: lambda: sparkle(strip, 255, 255, 255, 0),
        9: lambda: snow_sparkle(strip, 16, 16, 16, 20, random.randint(100, 1000)),
        10: lambda: running_lights(strip, 255, 0, 0, 50),
        11: lambda: color_wipe(strip, 0, 255, 0, 50),
        12: lambda: rainbow_cycle(strip, 20),  # Add argument for rainbow_cycle
        13: lambda: theater_chase(strip, 255, 0, 0, 50),
        14: lambda: theater_chase_rainbow(strip, 50),  # Add argument for theater_chase_rainbow
        15: lambda: fire(strip, 55, 120, 15),
        16: lambda: bouncing_colored_balls(strip, 1, [(255, 0, 0)], False),
        17: lambda: bouncing_colored_balls(strip, 20, [(255, 0, 0), (255, 255, 255), (0, 0, 255)], False),
        18: lambda: meteor_rain(strip, 255, 255, 255, 10, 64, True, 30),
    }
    effect_function = effects.get(selected_effect)
    current_effect_thread = Thread(target=effect_function)
    current_effect_thread.daemon = True
    current_effect_thread.start()

def next_effect():
    global selected_effect
    selected_effect = (selected_effect + 1) % 19
    run_effect(selected_effect)

def previous_effect():
    global selected_effect
    selected_effect = (selected_effect - 1) % 19
    run_effect(selected_effect)

def stop_animations():
    effect_stop_event.set()  # Stop any running effect
    if current_effect_thread:
        terminate_thread(current_effect_thread)  # Terminate the current effect thread
    set_all(strip, 0, 0, 0)  # Ensure all LEDs are turned off    

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

def ir_listener():
    global current_command, selected_effect, animations_enabled, current_mode
    print('IR Listener thread started')
    selected_effect = 0
    while True:
        if current_command != 0:
            print(f"Current command: {current_command}")
            match current_command:
                case 69:
                    set_all(strip, 0, 0, 0)  
                    current_mode = 'animation'
                case 70:
                    stop_animations()
                    current_mode = 'static'
                case 90:  # NEXT
                    mode_commands[current_mode]['next']()
                case 8:  # PREVIOUS
                    mode_commands[current_mode]['previous']()
                case 28:  # TOGGLE ANIMATIONS ON/OFF
                    animations_enabled = not animations_enabled
                    if not animations_enabled:
                        stop_animations()
                    else:
                        run_effect(selected_effect)
                case 24:  # UP
                    if 'up' in mode_commands[current_mode]:
                        mode_commands[current_mode]['up']()
                case 82:  # DOWN
                    if 'down' in mode_commands[current_mode]:
                        mode_commands[current_mode]['down']()
            current_command = 0
            time.sleep(0.1)

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
    finally:
        strip._cleanup()
