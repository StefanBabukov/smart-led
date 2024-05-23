import time
import random
import math
from threading import Thread, Event
from gpiozero import Button
from rpi_ws281x import PixelStrip, Color
import evdev

# LED strip configuration
LED_COUNT = 300        # Number of LED pixels.
LED_PIN = 18           # GPIO pin connected to the pixels (must support PWM!).
LED_FREQ_HZ = 800000   # LED signal frequency in hertz (usually 800khz)
LED_DMA = 10           # DMA channel to use for generating signal (try 10)
LED_BRIGHTNESS = 255   # Set to 0 for darkest and 255 for brightest
LED_INVERT = False     # True to invert the signal (when using NPN transistor level shift)
LED_CHANNEL = 0        # 0 or 1
effect_stop_event = Event()

# Initialize variables
selected_effect = 0
current_command = 0

# Set up the LED strip
strip = PixelStrip(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)
strip.begin()

def get_ir_device():
    devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
    for device in devices:
        if device.name == "gpio_ir_recv":
            print("Using device", device.path, "\n")
            return device
    print("No device found!")
    return None

ir_device = get_ir_device()

def handle_ir():
    global current_command
    while True:
        event = ir_device.read_one()
        if event and event.value:
            current_command = event.value
            print("Received command", event.value)

def set_pixel(pixel, red, green, blue):
    strip.setPixelColor(pixel, Color(red, green, blue))

def set_all(red, green, blue):
    for i in range(strip.numPixels()):
        set_pixel(i, red, green, blue)
    strip.show()

def fade_to_black(led_no, fade_value):
    color = strip.getPixelColor(led_no)
    r = max((color >> 16) - fade_value, 0)
    g = max((color >> 8 & 0xFF) - fade_value, 0)
    b = max((color & 0xFF) - fade_value, 0)
    set_pixel(led_no, r, g, b)

def run_forever(effect):
    def wrapper(*args, **kwargs):
        while not effect_stop_event.is_set():
            effect(*args, **kwargs)
    return wrapper

@run_forever
def rgb_loop():
    for j in range(3):
        for k in range(256):
            set_all(k if j == 0 else 0, k if j == 1 else 0, k if j == 2 else 0)
            time.sleep(0.003)
        for k in range(255, -1, -1):
            set_all(k if j == 0 else 0, k if j == 1 else 0, k if j == 2 else 0)
            time.sleep(0.003)

@run_forever
def fade_in_out(red, green, blue):
    for k in range(256):
        set_all(int((k / 256.0) * red), int((k / 256.0) * green), int((k / 256.0) * blue))
        time.sleep(0.01)
    for k in range(255, -1, -1):
        set_all(int((k / 256.0) * red), int((k / 256.0) * green), int((k / 256.0) * blue))
        time.sleep(0.01)

@run_forever
def strobe(red, green, blue, strobe_count, flash_delay, end_pause):
    for _ in range(strobe_count):
        set_all(red, green, blue)
        time.sleep(flash_delay / 1000.0)
        set_all(0, 0, 0)
        time.sleep(flash_delay / 1000.0)
    time.sleep(end_pause / 1000.0)

@run_forever
def halloween_eyes(red, green, blue, eye_width, eye_space, fade, steps, fade_delay, end_pause):
    start_point = random.randint(0, LED_COUNT - (2 * eye_width) - eye_space)
    start_2nd_eye = start_point + eye_width + eye_space

    for i in range(eye_width):
        set_pixel(start_point + i, red, green, blue)
        set_pixel(start_2nd_eye + i, red, green, blue)
    strip.show()

    if fade:
        for j in range(steps, -1, -1):
            r = (j * (red / steps))
            g = (j * (green / steps))
            b = (j * (blue / steps))
            for i in range(eye_width):
                set_pixel(start_point + i, int(r), int(g), int(b))
                set_pixel(start_2nd_eye + i, int(r), int(g), int(b))
            strip.show()
            time.sleep(fade_delay / 1000.0)

    set_all(0, 0, 0)
    time.sleep(end_pause / 1000.0)

@run_forever
def cylon_bounce(red, green, blue, eye_size, speed_delay, return_delay):
    for i in range(strip.numPixels() - eye_size - 2):
        set_all(0, 0, 0)
        set_pixel(i, red // 10, green // 10, blue // 10)
        for j in range(1, eye_size + 1):
            set_pixel(i + j, red, green, blue)
        set_pixel(i + eye_size + 1, red // 10, green // 10, blue // 10)
        strip.show()
        time.sleep(speed_delay / 1000.0)

    time.sleep(return_delay / 1000.0)

    for i in range(strip.numPixels() - eye_size - 2, -1, -1):
        set_all(0, 0, 0)
        set_pixel(i, red // 10, green // 10, blue // 10)
        for j in range(1, eye_size + 1):
            set_pixel(i + j, red, green, blue)
        set_pixel(i + eye_size + 1, red // 10, green // 10, blue // 10)
        strip.show()
        time.sleep(speed_delay / 1000.0)

    time.sleep(return_delay / 1000.0)

@run_forever
def twinkle(red, green, blue, count, speed_delay, only_one):
    set_all(0, 0, 0)
    for _ in range(count):
        set_pixel(random.randint(0, LED_COUNT-1), red, green, blue)
        strip.show()
        time.sleep(speed_delay / 1000.0)
        if only_one:
            set_all(0, 0, 0)
    time.sleep(speed_delay / 1000.0)

@run_forever
def twinkle_random(count, speed_delay, only_one):
    set_all(0, 0, 0)
    for _ in range(count):
        set_pixel(random.randint(0, LED_COUNT-1), random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
        strip.show()
        time.sleep(speed_delay / 1000.0)
        if only_one:
            set_all(0, 0, 0)
    time.sleep(speed_delay / 1000.0)

@run_forever
def sparkle(red, green, blue, speed_delay):
    for _ in range(LED_COUNT):
        pixel = random.randint(0, LED_COUNT-1)
        set_pixel(pixel, red, green, blue)
        strip.show()
        time.sleep(speed_delay / 1000.0)
        set_pixel(pixel, 0, 0, 0)

@run_forever
def snow_sparkle(red, green, blue, sparkle_delay, speed_delay):
    set_all(red, green, blue)
    for _ in range(LED_COUNT):
        pixel = random.randint(0, LED_COUNT-1)
        set_pixel(pixel, 255, 255, 255)
        strip.show()
        time.sleep(sparkle_delay / 1000.0)
        set_pixel(pixel, red, green, blue)
        strip.show()
        time.sleep(speed_delay / 1000.0)

@run_forever
def running_lights(red, green, blue, wave_delay):
    position = 0
    for _ in range(LED_COUNT * 2):
        position += 1
        for i in range(strip.numPixels()):
            set_pixel(i, int(((math.sin(i + position) * 127 + 128) / 255) * red),
                        int(((math.sin(i + position) * 127 + 128) / 255) * green),
                        int(((math.sin(i + position) * 127 + 128) / 255) * blue))
        strip.show()
        time.sleep(wave_delay / 1000.0)

@run_forever
def color_wipe(red, green, blue, speed_delay):
    for i in range(strip.numPixels()):
        set_pixel(i, red, green, blue)
        strip.show()
        time.sleep(speed_delay / 1000.0)

@run_forever
def rainbow_cycle(speed_delay):
    for j in range(256 * 5):  # 5 cycles of all colors on wheel
        for i in range(strip.numPixels()):
            color = wheel((int(i * 256 / strip.numPixels()) + j) & 255)
            set_pixel(i, color[0], color[1], color[2])
        strip.show()
        time.sleep(speed_delay / 1000.0)

def wheel(pos):
    if pos < 85:
        return [pos * 3, 255 - pos * 3, 0]
    elif pos < 170:
        pos -= 85
        return [255 - pos * 3, 0, pos * 3]
    else:
        pos -= 170
        return [0, pos * 3, 255 - pos * 3]

@run_forever
def theater_chase(red, green, blue, speed_delay):
    for j in range(10):  # do 10 cycles of chasing
        for q in range(3):
            for i in range(0, strip.numPixels(), 3):
                set_pixel(i + q, red, green, blue)
            strip.show()
            time.sleep(speed_delay / 1000.0)
            for i in range(0, strip.numPixels(), 3):
                set_pixel(i + q, 0, 0, 0)

@run_forever
def theater_chase_rainbow(speed_delay):
    for j in range(256):  # cycle all 256 colors in the wheel
        for q in range(3):
            for i in range(0, strip.numPixels(), 3):
                color = wheel((i + j) % 255)
                set_pixel(i + q, color[0], color[1], color[2])
            strip.show()
            time.sleep(speed_delay / 1000.0)
            for i in range(0, strip.numPixels(), 3):
                set_pixel(i + q, 0, 0, 0)

@run_forever
def fire(cooling, sparking, speed_delay):
    heat = [0] * LED_COUNT
    for _ in range(LED_COUNT):
        cooldown = random.randint(0, ((cooling * 10) // LED_COUNT) + 2)
        heat[_] = max(heat[_] - cooldown, 0)
    for k in range(LED_COUNT - 1, 1, -1):
        heat[k] = (heat[k - 1] + heat[k - 2] + heat[k - 2]) // 3
    if random.randint(0, 255) < sparking:
        y = random.randint(0, 7)
        heat[y] = heat[y] + random.randint(160, 255)
    for j in range(LED_COUNT):
        set_pixel_heat_color(j, heat[j])
    strip.show()
    time.sleep(speed_delay / 1000.0)

def set_pixel_heat_color(pixel, temperature):
    t192 = round((temperature / 255.0) * 191)
    heatramp = t192 & 0x3F
    heatramp <<= 2
    if t192 > 0x80:
        set_pixel(pixel, 255, 255, heatramp)
    elif t192 > 0x40:
        set_pixel(pixel, 255, heatramp, 0)
    else:
        set_pixel(pixel, heatramp, 0, 0)

@run_forever
def bouncing_colored_balls(ball_count, colors, continuous):
    gravity = -9.81
    start_height = 1
    height = [start_height] * ball_count
    impact_velocity_start = math.sqrt(2 * abs(gravity) * start_height)
    impact_velocity = [impact_velocity_start] * ball_count
    time_since_last_bounce = [0] * ball_count
    position = [0] * ball_count
    clock_time_since_last_bounce = [time.time()] * ball_count
    dampening = [0.90 - float(i) / ball_count ** 2 for i in range(ball_count)]
    ball_bouncing = [True] * ball_count

    while True:
        balls_still_bouncing = False
        for i in range(ball_count):
            time_since_last_bounce[i] = time.time() - clock_time_since_last_bounce[i]
            height[i] = 0.5 * gravity * (time_since_last_bounce[i] ** 2) + impact_velocity[i] * time_since_last_bounce[i]
            if height[i] < 0:
                height[i] = 0
                impact_velocity[i] *= dampening[i]
                clock_time_since_last_bounce[i] = time.time()
                if impact_velocity[i] < 0.01:
                    if continuous:
                        impact_velocity[i] = impact_velocity_start
                    else:
                        ball_bouncing[i] = False
            position[i] = round(height[i] * (LED_COUNT - 1) / start_height)

        set_all(0, 0, 0)  # Clear the strip before drawing new positions
        for i in range(ball_count):
            if ball_bouncing[i]:
                balls_still_bouncing = True
            set_pixel(position[i], colors[i % len(colors)][0], colors[i % len(colors)][1], colors[i % len(colors)][2])
        strip.show()
        time.sleep(0.02)  # Small delay for smoother animation

@run_forever
def meteor_rain(red, green, blue, meteor_size, meteor_trail_decay, meteor_random_decay, speed_delay):
    set_all(0, 0, 0)
    for i in range(strip.numPixels() * 2):
        for j in range(strip.numPixels()):
            if not meteor_random_decay or random.randint(0, 10) > 5:
                fade_to_black(j, meteor_trail_decay)
        for j in range(meteor_size):
            if (i - j < strip.numPixels()) and (i - j >= 0):
                set_pixel(i - j, red, green, blue)
        strip.show()
        time.sleep(speed_delay / 1000.0)

def run_effect(selected_effect):
    effect_stop_event.clear()  # Clear the event to start a new effect
    print(f"Running effect: {selected_effect}")
    effects = {
        0: lambda: rgb_loop(),
        1: lambda: fade_in_out(255, 0, 0),
        2: lambda: strobe(255, 255, 255, 10, 50, 1000),
        3: lambda: halloween_eyes(255, 0, 0, 1, 4, True, random.randint(5, 50), random.randint(50, 150), random.randint(1000, 10000)),
        4: lambda: cylon_bounce(255, 0, 0, 4, 10, 50),
        5: lambda: cylon_bounce(255, 0, 0, 8, 10, 50),
        6: lambda: twinkle(255, 0, 0, 10, 100, False),
        7: lambda: twinkle_random(20, 100, False),
        8: lambda: sparkle(255, 255, 255, 0),
        9: lambda: snow_sparkle(16, 16, 16, 20, random.randint(100, 1000)),
        10: lambda: running_lights(255, 0, 0, 50),
        11: lambda: color_wipe(0, 255, 0, 50),
        12: lambda: rainbow_cycle(50),
        13: lambda: theater_chase(255, 0, 0, 50),
        14: lambda: theater_chase_rainbow(50),
        15: lambda: fire(55, 120, 15),
        16: lambda: bouncing_colored_balls(1, [(255, 0, 0)], False),
        17: lambda: bouncing_colored_balls(20, [(255, 0, 0), (255, 255, 255), (0, 0, 255)], False),
        18: lambda: meteor_rain(255, 255, 255, 10, 64, True, 30),
    }
    effect_function = effects.get(selected_effect)
    effect_thread = Thread(target=effect_function)
    effect_thread.daemon = True
    effect_thread.start()

def ir_listener():
    global current_command
    print('IR Listener thread started')
    selected_effect = 0
    while True:
        if current_command:
            print(f"Current command: {current_command} type of command {(current_command == 90)}")
            if current_command == 90:  # NEXT
                selected_effect = (selected_effect + 1) % 19
                print('should call next effect', selected_effect)

                effect_stop_event.set()  # Stop current effect
                time.sleep(0.1)  # Small delay to ensure the current effect stops
                run_effect(selected_effect)
            elif current_command == 8:  # PREVIOUS
                selected_effect = (selected_effect - 1) % 19
                effect_stop_event.set()  # Stop current effect
                time.sleep(0.1)  # Small delay to ensure the current effect stops
                run_effect(selected_effect)
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
