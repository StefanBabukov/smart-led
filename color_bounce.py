from led_operations import set_pixel, set_all
import time

color_bounce_state = {
    'pos1': 0,
    'pos2': 0,
    'direction': 1,
    'color1': (255,0,0),
    'color2': (0,0,255),
    'initialized': False
}

def color_bounce_step(strip, c1=(255,0,0), c2=(0,0,255), speed_delay=10):
    st = color_bounce_state
    num_leds = strip.numPixels()
    if not st['initialized']:
        st['pos1'] = 0
        st['pos2'] = num_leds - 1
        st['color1'] = c1
        st['color2'] = c2
        set_all(strip, 0, 0, 0)
        st['initialized'] = True

    # Clear previous positions
    set_all(strip, 0, 0, 0)

    # Move positions
    st['pos1'] += st['direction']
    st['pos2'] -= st['direction']

    # Bounce?
    if st['pos1'] >= num_leds - 1 or st['pos1'] <= 0:
        st['direction'] *= -1
        # Shift colors slightly
        st['color1'] = ((st['color1'][0] + 10) % 256, (st['color1'][1] + 10) % 256, (st['color1'][2] + 10) % 256)
        st['color2'] = ((st['color2'][0] + 10) % 256, (st['color2'][1] + 10) % 256, (st['color2'][2] + 10) % 256)

    # Set pixels at positions
    set_pixel(strip, st['pos1'], *st['color1'])
    set_pixel(strip, st['pos2'], *st['color2'])
