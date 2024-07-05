from rpi_ws281x import PixelStrip
from led_operations import set_pixel, set_all, blend_colors
from animations import effect_stop_event, run_forever
import time

@run_forever
def color_bounce(strip, color1, color2, speed_delay):
    num_leds = strip.numPixels()
    pos1, pos2 = 0, num_leds - 1
    direction = 1

    while not effect_stop_event.is_set():
        print('SETTING PIXEL')
        set_all(strip, 0, 0, 0)


        if pos1 == pos2:
            mixed_color = blend_colors(color1, color2)
            set_pixel(strip, pos1, *mixed_color)

        # time.sleep(speed_delay / 1000.0)

        if pos1 == num_leds - 1 or pos1 == 0:
            direction *= -1
            color1 = (color1[0] + 10) % 256, (color1[1] + 10) % 256, (color1[2] + 10) % 256
            color2 = (color2[0] + 10) % 256, (color2[1] + 10) % 256, (color2[2] + 10) % 256

        pos1 += direction
        pos2 -= direction
        
        set_pixel(strip, pos1, *color1)
        set_pixel(strip, pos2, *color2)
        strip.show()
