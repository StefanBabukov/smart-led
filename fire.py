import random
import time
from rpi_ws281x import Color
from led_operations import set_pixel, set_all, fade_to_black
from animations import effect_stop_event

COOLING = 20
SPARKING = 120

# Define a more colorful fire palette
PALETTE = [
    (0, 0, 0), (32, 0, 0), (64, 0, 0), (96, 0, 0),
    (128, 0, 0), (160, 0, 0), (192, 0, 0), (224, 0, 0),
    (255, 0, 0), (255, 32, 0), (255, 64, 0), (255, 96, 0),
    (255, 128, 0), (255, 160, 0), (255, 192, 0), (255, 224, 0),
    (255, 255, 0), (255, 255, 32), (255, 255, 64), (255, 255, 96),
    (255, 255, 128), (255, 255, 160), (255, 255, 192), (255, 255, 224),
    (255, 255, 255), (224, 224, 255), (192, 192, 255), (160, 160, 255),
    (128, 128, 255), (96, 96, 255), (64, 64, 255), (32, 32, 255),
    (0, 0, 255)
]

def fire_animation(strip):
    num_leds = strip.numPixels()
    heat = [0] * (num_leds)  # Increase the heat array size

    while not effect_stop_event.is_set():
        for i in range(len(heat)):
            heat[i] = max(heat[i] - random.randint(0, ((COOLING * 10) // len(heat)) + 2), 0)

        for k in range(len(heat) - 1, 1, -1):
            heat[k] = (heat[k - 1] + heat[k - 2] + heat[k - 2]) // 3

        if random.randint(0, 255) < SPARKING:
            y = random.randint(0, 7)
            heat[y] = min(heat[y] + random.randint(160, 255), 255)

        for j in range(num_leds):
            colorindex = (heat[j] * (len(PALETTE) - 1)) // 255
            color = PALETTE[colorindex]
            set_pixel(strip, j, color[0], color[1], color[2])

        strip.show()