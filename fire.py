import random

from led_operations import set_pixel

COOLING = 24
SPARKING = 200
FIRE_HEIGHT_RATIO = 0.75

fire_state = {
    "heat": None,
    "virtual_leds": 0,
}

PALETTE = [
    (0, 0, 0),
    (8, 0, 0),
    (18, 0, 0),
    (34, 0, 0),
    (54, 0, 0),
    (80, 0, 0),
    (112, 4, 0),
    (148, 10, 0),
    (186, 18, 0),
    (224, 30, 0),
    (255, 48, 0),
    (255, 68, 0),
    (255, 88, 0),
    (255, 110, 0),
    (255, 130, 0),
    (255, 148, 0),
    (255, 164, 0),
    (255, 180, 0),
    (255, 194, 8),
    (255, 208, 18),
    (255, 220, 34),
    (255, 232, 56),
    (255, 240, 84),
    (255, 246, 120),
]


def fire_step(strip, cooling=COOLING, sparking=SPARKING, speed_delay=5):
    num_leds = strip.numPixels()
    virtual_leds = max(32, int(num_leds * FIRE_HEIGHT_RATIO))

    if fire_state["heat"] is None or fire_state["virtual_leds"] != virtual_leds:
        fire_state["heat"] = [0] * virtual_leds
        fire_state["virtual_leds"] = virtual_leds

    heat = fire_state["heat"]

    for i in range(virtual_leds):
        cooldown = random.randint(0, ((cooling * 10) // virtual_leds) + 2)
        heat[i] = max(0, heat[i] - cooldown)

    for k in range(virtual_leds - 1, 1, -1):
        heat[k] = (heat[k - 1] + heat[k - 2] + heat[k - 2]) // 3

    if random.randint(0, 255) < sparking:
        spark_index = random.randint(0, min(12, virtual_leds - 1))
        heat[spark_index] = min(255, heat[spark_index] + random.randint(180, 255))

    for j in range(num_leds):
        source_index = (j * (virtual_leds - 1)) // max(1, num_leds - 1)
        color_index = (heat[source_index] * (len(PALETTE) - 1)) // 255
        red, green, blue = PALETTE[color_index]
        set_pixel(strip, j, red, green, blue)
