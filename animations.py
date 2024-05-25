import time
import random
import math
from threading import Event
from rpi_ws281x import Color

effect_stop_event = Event()

def set_pixel(strip, pixel, red, green, blue):
    strip.setPixelColor(pixel, Color(red, green, blue))

def set_all(strip, red, green, blue):
    for i in range(strip.numPixels()):
        set_pixel(strip, i, red, green, blue)
    strip.show()

def fade_to_black(strip, led_no, fade_value):
    color = strip.getPixelColor(led_no)
    r = max((color >> 16) - fade_value, 0)
    g = max((color >> 8 & 0xFF) - fade_value, 0)
    b = max((color & 0xFF) - fade_value, 0)
    set_pixel(strip, led_no, r, g, b)

def run_forever(effect):
    def wrapper(*args, **kwargs):
        while not effect_stop_event.is_set():
            effect(*args, **kwargs)
    return wrapper

@run_forever
def rgb_loop(strip):
    for j in range(3):
        for k in range(256):
            set_all(strip, k if j == 0 else 0, k if j == 1 else 0, k if j == 2 else 0)
            time.sleep(0.003)
        for k in range(255, -1, -1):
            set_all(strip, k if j == 0 else 0, k if j == 1 else 0, k if j == 2 else 0)
            time.sleep(0.003)

@run_forever
def fade_in_out(strip, red, green, blue):
    for k in range(256):
        set_all(strip, int((k / 256.0) * red), int((k / 256.0) * green), int((k / 256.0) * blue))
        time.sleep(0.01)
    for k in range(255, -1, -1):
        set_all(strip, int((k / 256.0) * red), int((k / 256.0) * green), int((k / 256.0) * blue))
        time.sleep(0.01)

@run_forever
def strobe(strip, red, green, blue, strobe_count, flash_delay, end_pause):
    for _ in range(strobe_count):
        set_all(strip, red, green, blue)
        time.sleep(flash_delay / 1000.0)
        set_all(strip, 0, 0, 0)
        time.sleep(flash_delay / 1000.0)
    time.sleep(end_pause / 1000.0)

@run_forever
def halloween_eyes(strip, red, green, blue, eye_width, eye_space, fade, steps, fade_delay, end_pause):
    start_point = random.randint(0, strip.numPixels() - (2 * eye_width) - eye_space)
    start_2nd_eye = start_point + eye_width + eye_space

    for i in range(eye_width):
        set_pixel(strip, start_point + i, red, green, blue)
        set_pixel(strip, start_2nd_eye + i, red, green, blue)
    strip.show()

    if fade:
        for j in range(steps, -1, -1):
            r = (j * (red / steps))
            g = (j * (green / steps))
            b = (j * (blue / steps))
            for i in range(eye_width):
                set_pixel(strip, start_point + i, int(r), int(g), int(b))
                set_pixel(strip, start_2nd_eye + i, int(r), int(g), int(b))
            strip.show()
            time.sleep(fade_delay / 1000.0)

    set_all(strip, 0, 0, 0)
    time.sleep(end_pause / 1000.0)

@run_forever
def cylon_bounce(strip, red, green, blue, eye_size, speed_delay, return_delay):
    for i in range(strip.numPixels() - eye_size - 2):
        set_all(strip, 0, 0, 0)
        set_pixel(strip, i, red // 10, green // 10, blue // 10)
        for j in range(1, eye_size + 1):
            set_pixel(strip, i + j, red, green, blue)
        set_pixel(strip, i + eye_size + 1, red // 10, green // 10, blue // 10)
        strip.show()
        time.sleep(speed_delay / 1000.0)

    time.sleep(return_delay / 1000.0)

    for i in range(strip.numPixels() - eye_size - 2, -1, -1):
        set_all(strip, 0, 0, 0)
        set_pixel(strip, i, red // 10, green // 10, blue // 10)
        for j in range(1, eye_size + 1):
            set_pixel(strip, i + j, red, green, blue)
        set_pixel(strip, i + eye_size + 1, red // 10, green // 10, blue // 10)
        strip.show()
        time.sleep(speed_delay / 1000.0)

    time.sleep(return_delay / 1000.0)

@run_forever
def twinkle(strip, red, green, blue, count, speed_delay, only_one):
    set_all(strip, 0, 0, 0)
    for _ in range(count):
        set_pixel(strip, random.randint(0, strip.numPixels() - 1), red, green, blue)
        strip.show()
        time.sleep(speed_delay / 1000.0)
        if only_one:
            set_all(strip, 0, 0, 0)
    time.sleep(speed_delay / 1000.0)

@run_forever
def twinkle_random(strip, count, speed_delay, only_one):
    set_all(strip, 0, 0, 0)
    used_indices = []

    for _ in range(count):
        if len(used_indices) >= strip.numPixels():
            break  # All LEDs have been used

        # Find a new random index not used before
        while True:
            index = random.randint(0, strip.numPixels() - 1)
            if index not in used_indices:
                break

        used_indices.append(index)
        set_pixel(strip, index, random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
        strip.show()
        time.sleep(speed_delay / 1000.0)

        if only_one:
            set_all(strip, 0, 0, 0)
            used_indices = []  # Reset used indices if only one LED should be lit at a time

    time.sleep(speed_delay / 1000.0)

@run_forever
def sparkle(strip, red, green, blue, speed_delay):
    for _ in range(strip.numPixels()):
        pixel = random.randint(0, strip.numPixels() - 1)
        set_pixel(strip, pixel, red, green, blue)
        strip.show()
        time.sleep(speed_delay / 1000.0)
        set_pixel(strip, pixel, 0, 0, 0)

@run_forever
def snow_sparkle(strip, red, green, blue, sparkle_delay, speed_delay):
    set_all(strip, red, green, blue)
    for _ in range(strip.numPixels()):
        pixel = random.randint(0, strip.numPixels() - 1)
        pixel2 = random.randint(0, strip.numPixels() - 1)

        set_pixel(strip, pixel, 255, 255, 255)
        set_pixel(strip, pixel2, 255, 255, 255)

        strip.show()
        time.sleep(sparkle_delay / 1000.0)
        set_pixel(strip, pixel, red, green, blue)
        set_pixel(strip, pixel2, red, green, blue)

        strip.show()
        time.sleep(speed_delay / 1000.0)

@run_forever
def running_lights(strip, red, green, blue, wave_delay):
    position = 0
    for _ in range(strip.numPixels() * 2):
        position += 1
        for i in range(strip.numPixels()):
            set_pixel(strip, i, int(((math.sin(i + position) * 127 + 128) / 255) * red),
                        int(((math.sin(i + position) * 127 + 128) / 255) * green),
                        int(((math.sin(i + position) * 127 + 128) / 255) * blue))
        strip.show()
        time.sleep(wave_delay / 1000.0)

@run_forever
def color_wipe(strip, red, green, blue, speed_delay):
    for i in range(strip.numPixels()):
        set_pixel(strip, i, red, green, blue)
        strip.show()
        time.sleep(speed_delay / 1000.0)

@run_forever
def rainbow_cycle(strip, speed_delay):
    for j in range(256 * 5):  # 5 cycles of all colors on wheel
        for i in range(strip.numPixels()):
            color = wheel((int(i * 256 / strip.numPixels()) + j) & 255)
            set_pixel(strip, i, color[0], color[1], color[2])
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
def theater_chase(strip, red, green, blue, speed_delay):
    for j in range(10):  # do 10 cycles of chasing
        for q in range(3):
            for i in range(0, strip.numPixels(), 3):
                set_pixel(strip, i + q, red, green, blue)
            strip.show()
            time.sleep(speed_delay / 1000.0)
            for i in range(0, strip.numPixels(), 3):
                set_pixel(strip, i + q, 0, 0, 0)

@run_forever
def theater_chase_rainbow(strip, speed_delay):
    for j in range(256):  # cycle all 256 colors in the wheel
        for q in range(3):
            for i in range(0, strip.numPixels(), 3):
                color = wheel((i + j) % 255)
                set_pixel(strip, i + q, color[0], color[1], color[2])
            strip.show()
            time.sleep(speed_delay / 1000.0)
            for i in range(0, strip.numPixels(), 3):
                set_pixel(strip, i + q, 0, 0, 0)

@run_forever
def fire(strip, cooling, sparking, speed_delay):
    heat = [0] * strip.numPixels()
    for _ in range(strip.numPixels()):
        cooldown = random.randint(0, ((cooling * 10) // strip.numPixels()) + 2)
        heat[_] = max(heat[_] - cooldown, 0)
    for k in range(strip.numPixels() - 1, 1, -1):
        heat[k] = (heat[k - 1] + heat[k - 2] + heat[k - 2]) // 3
    if random.randint(0, 255) < sparking:
        y = random.randint(0, 7)
        heat[y] = heat[y] + random.randint(160, 255)
    for j in range(strip.numPixels()):
        set_pixel_heat_color(strip, j, heat[j])
    strip.show()
    time.sleep(speed_delay / 1000.0)

def set_pixel_heat_color(strip, pixel, temperature):
    t192 = round((temperature / 255.0) * 191)
    heatramp = t192 & 0x3F
    heatramp <<= 2
    if t192 > 0x80:
        set_pixel(strip, pixel, 255, 255, heatramp)
    elif t192 > 0x40:
        set_pixel(strip, pixel, 255, heatramp, 0)
    else:
        set_pixel(strip, pixel, heatramp, 0, 0)

@run_forever
def bouncing_colored_balls(strip, ball_count, colors, continuous):
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
            position[i] = round(height[i] * (strip.numPixels() - 1) / start_height)

        set_all(strip, 0, 0, 0)  # Clear the strip before drawing new positions
        for i in range(ball_count):
            if ball_bouncing[i]:
                balls_still_bouncing = True
            set_pixel(strip, position[i], colors[i % len(colors)][0], colors[i % len(colors)][1], colors[i % len(colors)][2])
        strip.show()
        time.sleep(0.02)  # Small delay for smoother animation

@run_forever
def meteor_rain(strip, red, green, blue, meteor_size, meteor_trail_decay, meteor_random_decay, speed_delay):
    set_all(strip, 0, 0, 0)
    for i in range(strip.numPixels() * 2):
        for j in range(strip.numPixels()):
            if not meteor_random_decay or random.randint(0, 10) > 5:
                fade_to_black(strip, j, meteor_trail_decay)
        for j in range(meteor_size):
            if (i - j < strip.numPixels()) and (i - j >= 0):
                set_pixel(strip, i - j, red, green, blue)
        strip.show()
        time.sleep(speed_delay / 1000.0)
