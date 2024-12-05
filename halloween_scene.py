import time
import random
import math
from led_operations import set_pixel, set_all, fade_to_black

# Global state for the Halloween scene
halloween_scene_state = {
    'initialized': False,
    'frame_count': 0,
    'background_offset': 0,
    'pumpkin_position': 0.0,
    'pumpkin_direction': 1,
    'pumpkin_color_phase': 0,
    'pumpkin_side_color_phase': 0,
    'eye_color_phase': 0,
    'teeth_flash_state': False,
    'teeth_flash_timer': 0,

    'pumpkin_speed': 0.05,
    'pumpkin_accel': 0.0,
    'next_direction_change': 0,
    'treats': [],
    'last_treat_spawn': 0,
    'treats_eaten': 0,
    'pumpkin_width': 20,
    'teeth_width': 5,
    'side_flicker_timer': 0,
    'eat_flash_timer': 0,
    'eat_inner_flash_timer': 0,
}

def reset_halloween_scene_state():
    halloween_scene_state.update({
        'initialized': False,
        'frame_count': 0,
        'background_offset': 0,
        'pumpkin_position': 0.0,
        'pumpkin_direction': 1,
        'pumpkin_color_phase': 0,
        'pumpkin_side_color_phase': 0,
        'eye_color_phase': 0,
        'teeth_flash_state': False,
        'teeth_flash_timer': 0,
        'pumpkin_speed': 0.05,
        'pumpkin_accel': 0.0,
        'next_direction_change': 0,
        'treats': [],
        'last_treat_spawn': 0,
        'treats_eaten': 0,
        'pumpkin_width': 20,
        'teeth_width': 5,
        'side_flicker_timer': 0,
        'eat_flash_timer': 0,
        'eat_inner_flash_timer': 0,
    })

def halloween_scene_step(strip):
    st = halloween_scene_state
    num_leds = strip.numPixels()
    if not st['initialized']:
        st['initialized'] = True
        # Start pumpkin roughly in the middle
        st['pumpkin_position'] = num_leds // 2
        # Clear strip initially
        set_all(strip, 0, 0, 0)

    st['frame_count'] += 1
    st['background_offset'] += 1

    # Reset if pumpkin too big
    if st['pumpkin_width'] >= num_leds:
        reset_halloween_scene_state()
        return

    # Max pumpkin speed
    max_pumpkin_speed = 0.7

    # Spawn treats occasionally
    if (st['frame_count'] - st['last_treat_spawn'] > 50) and (random.random() > 0.95):
        pumpkin_pos = st['pumpkin_position']
        group_size = random.randint(1,3)
        for _ in range(group_size):
            attempts = 0
            while True:
                pos = random.randint(0, num_leds-1)
                if abs(pos - pumpkin_pos) > 20:
                    break
                attempts += 1
                if attempts > 50:
                    break
            direction = random.choice([-1,1])
            is_special = (random.random() > 0.9)
            if is_special:
                length = 3
                base_speed = 0.4
            else:
                length = random.randint(1,3)
                base_speed = 0.5 - (length-1)*0.15

            r = random.randint(100,255)
            g = random.randint(100,255)
            b = random.randint(100,255)

            st['treats'].append({
                'pos': float(pos),
                'dir': direction,
                'r': r,
                'g': g,
                'b': b,
                'panic_timer': 0,
                'length': length,
                'base_speed': base_speed,
                'special': is_special
            })
        st['last_treat_spawn'] = st['frame_count']

    # Smooth color transitions for pumpkin:
    # Slowly rotate hue
    st['pumpkin_color_phase'] = (st['pumpkin_color_phase'] + 1) % 360
    # Side color is offset by +30 degrees
    st['pumpkin_side_color_phase'] = (st['pumpkin_color_phase'] + 30) % 360

    # Use a sine wave to modulate brightness slightly
    sine_factor = (math.sin(st['frame_count'] * 0.05) + 1) / 2
    # Sine factor in [0..1], adjust value (v)
    v = 0.8 + 0.2 * sine_factor  # brightness between 0.8 and 1.0
    pumpkin_r, pumpkin_g, pumpkin_b = hsv_to_rgb((st['pumpkin_color_phase'] / 360.0), 1.0, v)

    # Background
    for i in range(num_leds):
        base_r, base_g, base_b = background_color(i + st['background_offset'])
        set_pixel(strip, i, base_r, base_g, base_b)

    # Treat interactions
    for i in range(len(st['treats'])):
        for j in range(i+1, len(st['treats'])):
            if abs(st['treats'][i]['pos'] - st['treats'][j]['pos']) < 2:
                st['treats'][i]['dir'] *= -1
                st['treats'][j]['dir'] *= -1

    pumpkin_pos = st['pumpkin_position']
    if st['treats']:
        # Chase closest treat
        closest_treat = min(st['treats'], key=lambda t: abs(t['pos'] - pumpkin_pos))
        dist = closest_treat['pos'] - pumpkin_pos
        st['pumpkin_direction'] = 1 if dist > 0 else -1
        distance_abs = abs(dist)
        base_speed = 0.3
        if distance_abs < 20:
            base_speed += 0.2
        if distance_abs < 10:
            base_speed += 0.2
        if distance_abs < 5:
            base_speed += 0.3
        if random.random() > 0.99:
            st['pumpkin_direction'] *= -1
        st['pumpkin_speed'] = min(base_speed, max_pumpkin_speed)
    else:
        # No treats: wander
        if st['frame_count'] > st['next_direction_change']:
            st['pumpkin_direction'] = random.choice([-1,1])
            st['next_direction_change'] = st['frame_count'] + random.randint(50,150)
        if random.random() > 0.95:
            st['pumpkin_accel'] = random.uniform(-0.02, 0.02)
        st['pumpkin_speed'] += st['pumpkin_accel']
        if st['pumpkin_speed'] < 0.01:
            st['pumpkin_speed'] = 0.01
        if st['pumpkin_speed'] > 0.2:
            st['pumpkin_speed'] = 0.2

    st['pumpkin_position'] += st['pumpkin_speed'] * st['pumpkin_direction']
    # Bounds
    if st['pumpkin_position'] < 0:
        st['pumpkin_position'] = 0
    elif st['pumpkin_position'] > num_leds-1:
        st['pumpkin_position'] = num_leds - 1

    # Side colors (no flicker)
    side_r, side_g, side_b = hsv_to_rgb((st['pumpkin_side_color_phase']/360.0), 1.0, v)

    # Move & draw treats
    new_treats = []
    for t in st['treats']:
        dist_from_pumpkin = abs(t['pos'] - pumpkin_pos)
        if dist_from_pumpkin > 40:
            treat_speed = t['base_speed'] * 0.1
        elif dist_from_pumpkin > 20:
            treat_speed = t['base_speed'] * 0.5
        else:
            treat_speed = t['base_speed'] * 1.2
            if t['panic_timer'] == 0 and random.random() > 0.9:
                t['dir'] *= -1
                t['panic_timer'] = 20

        if t['panic_timer'] > 0:
            t['panic_timer'] -= 1

        if random.random() > 0.995:
            t['dir'] = -t['dir']

        t['pos'] += t['dir'] * treat_speed

        if t['special']:
            # special treat: random bright colors each frame
            t['r'], t['g'], t['b'] = hsv_random_bright_color()
        else:
            # Slight flicker adjustments
            if random.random() > 0.95:
                t['r'] = min(255, max(100, t['r'] + random.randint(-20,20)))
                t['g'] = min(255, max(100, t['g'] + random.randint(-20,20)))
                t['b'] = min(255, max(100, t['b'] + random.randint(-20,20)))

        if 0 <= t['pos'] < num_leds:
            start_pos = int(t['pos'])
            for l_i in range(t['length']):
                treat_pixel = start_pos + (l_i * t['dir'])
                if 0 <= treat_pixel < num_leds:
                    set_pixel(strip, treat_pixel, t['r'], t['g'], t['b'])
            new_treats.append(t)
    st['treats'] = new_treats

    pumpkin_center = int(st['pumpkin_position'])
    pumpkin_start = pumpkin_center - st['pumpkin_width'] // 2
    pumpkin_end = pumpkin_start + st['pumpkin_width']

    # Side flicker after eating
    if st['side_flicker_timer'] > 0:
        st['side_flicker_timer'] -= 1

    # Draw pumpkin body
    for i in range(pumpkin_start, pumpkin_end):
        if 0 <= i < num_leds:
            edge_dist = min(i - pumpkin_start, pumpkin_end - i - 1)
            if edge_dist < 3:
                blend_factor = (3 - edge_dist)/3.0
                pr = pumpkin_r*(1-blend_factor) + side_r*blend_factor
                pg = pumpkin_g*(1-blend_factor) + side_g*blend_factor
                pb = pumpkin_b*(1-blend_factor) + side_b*blend_factor
            else:
                pr,pg,pb = pumpkin_r, pumpkin_g, pumpkin_b

            if st['eat_inner_flash_timer'] > 0:
                # slight flash inside
                if random.random() < 0.1:
                    pr, pg, pb = 255, 255, 255

            set_pixel(strip, i, int(pr), int(pg), int(pb))

    # Draw eyes according to pumpkin size
    draw_eyes(strip, pumpkin_center, st['pumpkin_width'])

    # Teeth logic
    st['teeth_width'] = max(5, st['pumpkin_width'] // 4)
    teeth_start = pumpkin_center - st['teeth_width']//2
    teeth_positions = range(teeth_start, teeth_start+st['teeth_width'])

    if st['teeth_flash_timer'] == 0 and random.randint(0,100) > 98:
        st['teeth_flash_state'] = not st['teeth_flash_state']
        st['teeth_flash_timer'] = 50
    if st['teeth_flash_timer'] > 0:
        st['teeth_flash_timer'] -= 1

    if st['teeth_flash_state']:
        for tpos in teeth_positions:
            if 0 <= tpos < num_leds:
                set_pixel(strip, tpos, 255,255,255)
    else:
        for tpos in teeth_positions:
            if 0 <= tpos < num_leds:
                set_pixel(strip, tpos, 200,200,150)

    # Check eating
    eaten_count = 0
    special_eaten = 0
    remaining_treats = []
    for t in st['treats']:
        treat_positions = [int(t['pos'] + i*t['dir']) for i in range(t['length'])]
        if any(pumpkin_start <= p <= pumpkin_end for p in treat_positions):
            eaten_count += 1
            if t['special']:
                special_eaten += 1
        else:
            remaining_treats.append(t)
    st['treats'] = remaining_treats

    if eaten_count > 0:
        st['treats_eaten'] += eaten_count
        st['side_flicker_timer'] = 20
        st['eat_flash_timer'] = 10
        st['eat_inner_flash_timer'] = 10

        # Growth logic
        growth = 0
        if st['treats_eaten'] % 5 == 0:
            growth += 5
        if special_eaten > 0:
            growth += 10 * special_eaten

        if growth > 0:
            st['pumpkin_width'] += growth

    if st['eat_inner_flash_timer'] > 0:
        st['eat_inner_flash_timer'] -= 1


def draw_eyes(strip, center, width):
    # As the pumpkin grows bigger, eyes get more complex:
    # Small (<30): single red pixel at center
    # Medium (30<=width<50): two pixels, red and orange gradient
    # Large (>=50): four pixels, red center, orange outwards, darker edges
    num_leds = strip.numPixels()

    if width < 30:
        # Single red pixel
        if 0 <= center < num_leds:
            set_pixel(strip, center, 255,0,0)
    elif width < 50:
        # Two pixels: center (red), center+1 (orange)
        if 0 <= center < num_leds:
            set_pixel(strip, center, 255,0,0)
        if 0 <= center+1 < num_leds:
            set_pixel(strip, center+1, 255,100,0)
    else:
        # Four pixels: 
        # center-1: dark red
        # center: bright red
        # center+1: red-orange
        # center+2: orange-black mix (dim orange)
        eye_pixels = [
            (center-1, (200,0,0)),
            (center,   (255,0,0)),
            (center+1, (255,80,0)),
            (center+2, (180,80,0))
        ]
        for pos, color in eye_pixels:
            if 0 <= pos < num_leds:
                set_pixel(strip, pos, color[0], color[1], color[2])

def hsv_random_bright_color():
    h = random.random()
    s = 1.0
    v = 1.0
    r,g,b = hsv_to_rgb(h,s,v)
    return (int(r), int(g), int(b))

def background_color(position):
    # Background hue range [200..280]
    hue = (position % 600) / 600.0 * 80 + 200
    r,g,b = hsv_to_rgb(hue/360.0, 1.0, 0.2)
    return (int(r), int(g), int(b))

def hsv_to_rgb(h, s, v):
    """Convert HSV to RGB [0..1]."""
    i = int(h*6)
    f = h*6 - i
    p = v*(1 - s)
    q = v*(1 - f*s)
    t = v*(1 - (1-f)*s)
    i = i % 6
    if i == 0:
        r,g,b = v,t,p
    elif i == 1:
        r,g,b = q,v,p
    elif i == 2:
        r,g,b = p,v,t
    elif i == 3:
        r,g,b = p,q,v
    elif i == 4:
        r,g,b = t,p,v
    elif i == 5:
        r,g,b = v,p,q
    return (r*255,g*255,b*255)
