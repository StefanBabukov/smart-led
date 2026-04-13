import random
from led_operations import set_pixel
COOLING = 20
SPARKING = 180

# Keep state in a dictionary so it's not reset every call
fire_state = {
    'heat': None
}

PALETTE = [
    # Black to dark red
    (0, 0, 0), (8, 0, 0), (16, 0, 0), (32, 0, 0),
    (64, 0, 0), (96, 0, 0), (128, 0, 0), (160, 0, 0),
    # Red to orange
    (192, 0, 0), (224, 16, 0), (255, 32, 0), (255, 64, 0),
    (255, 96, 0), (255, 128, 0), (255, 160, 0), (255, 192, 0),
    # Orange to yellow
    (255, 210, 0), (255, 224, 0), (255, 240, 0), (255, 255, 0),
    (255, 255, 32), (255, 255, 64),
    # Yellow to warm white tip
    (255, 255, 100), (255, 255, 140), (255, 255, 180),
]

def fire_step(strip, cooling=COOLING, sparking=SPARKING, speed_delay=5):
    num_leds = strip.numPixels()

    if fire_state['heat'] is None:
        fire_state['heat'] = [0] * num_leds

    heat = fire_state['heat']
    # Step 1. Cool down
    for i in range(num_leds):
        heat[i] = max(heat[i] - random.randint(0, ((cooling * 10) // num_leds) + 2), 0)

    # Step 2. Drift heat upward
    for k in range(num_leds - 1, 1, -1):
        heat[k] = (heat[k - 1] + heat[k - 2] + heat[k - 2]) // 3

    # Step 3. Random sparks at multiple points along the strip
    spark_zones = [0, num_leds // 4, num_leds // 2, (3 * num_leds) // 4]
    for zone_start in spark_zones:
        if random.randint(0, 255) < sparking:
            y = random.randint(zone_start, min(zone_start + 7, num_leds - 1))
            heat[y] = min(heat[y] + random.randint(160, 255), 255)

    # Step 4. Map heat to colors
    for j in range(num_leds):
        colorindex = (heat[j] * (len(PALETTE) - 1)) // 255
        color = PALETTE[colorindex]
        set_pixel(strip, j, color[0], color[1], color[2])
    
