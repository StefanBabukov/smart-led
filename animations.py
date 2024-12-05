import time
import random
import math
from rpi_ws281x import Color
from led_operations import set_pixel, set_all, fade_to_black

# State containers for animations
fade_in_out_state = {'direction': 1, 'brightness': 0}
running_lights_state = {'position': 0}
twinkle_state = {'pixels': []}
twinkle_random_state = {'used_indices': []}
sparkle_state = {'on_pixel': None, 'timer': 0}
snow_sparkle_state = {'pixels': [], 'timer': 0, 'base_color': (16,16,16)}
cylon_state = {'pos': 0, 'forward': True}
halloween_eyes_state = {'phase': 0, 'start_point':0, 'start_2nd_eye':0, 'params':None, 'fade_step':0}
color_wipe_state = {'index':0, 'done':False}
rainbow_cycle_state = {'step': 0}
theater_chase_state = {'step': 0, 'index':0}
theater_chase_rainbow_state = {'step':0,'index':0}
fire_state = {'heat': None}
bouncing_balls_state = {'initialized': False}
meteor_rain_state = {'pos':0,'direction':1,'initialized':False}
wheel_step_state = {'pos':0}  # For wheel_step

def fade_in_out_step(strip, red, green, blue):
    st = fade_in_out_state
    st['brightness'] += st['direction']
    if st['brightness'] > 255:
        st['brightness'] = 255
        st['direction'] = -1
    elif st['brightness'] < 0:
        st['brightness'] = 0
        st['direction'] = 1

    val_r = (st['brightness'] * red) // 255
    val_g = (st['brightness'] * green) // 255
    val_b = (st['brightness'] * blue) // 255
    set_all(strip, val_r, val_g, val_b)

# Strobe step as a state machine
# We simulate a strobe: turn on for a few frames, off for a few frames
# Params: red, green, blue, strobe_count, flash_delay, end_pause
strobe_state = {'count':0, 'on':True, 'timer':0, 'params':None}
def strobe_step(strip, red, green, blue, strobe_count, flash_delay, end_pause):
    # Initialize parameters if needed
    st = strobe_state
    if st['params'] is None:
        st['params'] = (red, green, blue, strobe_count, flash_delay, end_pause)
        st['count'] = 0
        st['on'] = True
        st['timer'] = 0

    red, green, blue, sc, fd, ep = st['params']
    # Each call, we advance a little
    if st['count'] < sc:
        if st['on']:
            set_all(strip, red, green, blue)
        else:
            set_all(strip, 0, 0, 0)
        # Toggle on/off each call
        st['on'] = not st['on']
        st['count'] += 0.5  # each full cycle (on+off) counts as 1
    else:
        # end pause - just keep off for a while
        set_all(strip, 0, 0, 0)
        # once done, reset?
        st['params'] = None

# Halloween eyes step as state machine:
# Steps:
# 1. Choose random start, draw eyes
# 2. Fade if needed
# 3. Clear and pause
def halloween_eyes_step(strip, red, green, blue, eye_width, eye_space, fade, steps, fade_delay, end_pause):
    st = halloween_eyes_state
    num_leds = strip.numPixels()
    if st['params'] is None:
        st['params'] = (red,green,blue,eye_width,eye_space,fade,steps,fade_delay,end_pause)
        start_point = random.randint(0, num_leds - (2 * eye_width) - eye_space)
        start_2nd_eye = start_point + eye_width + eye_space
        st['start_point'] = start_point
        st['start_2nd_eye'] = start_2nd_eye
        # phase 0: draw eyes
        for i in range(eye_width):
            set_pixel(strip, start_point + i, red, green, blue)
            set_pixel(strip, start_2nd_eye + i, red, green, blue)
        st['phase'] = 0
        st['fade_step'] = steps

    red,green,blue,eye_width,eye_space,fade,steps,fade_delay,end_pause = st['params']

    if st['phase'] == 0:
        # eyes drawn, next phase fade or skip to clear
        if fade:
            st['phase'] = 1
        else:
            st['phase'] = 2
            st['fade_step'] = end_pause / 10

    elif st['phase'] == 1:
        # fade phase
        if st['fade_step'] > 0:
            j = st['fade_step']
            r = int(j * (red / steps))
            g = int(j * (green / steps))
            b = int(j * (blue / steps))
            for i in range(eye_width):
                set_pixel(strip, st['start_point'] + i, r, g, b)
                set_pixel(strip, st['start_2nd_eye'] + i, r, g, b)
            st['fade_step'] -= 1
        else:
            # Fade done
            st['phase'] = 2
            st['fade_step'] = end_pause / 10

    elif st['phase'] == 2:
        # end pause
        if st['fade_step'] > 0:
            st['fade_step'] -= 1
        else:
            # clear and restart
            set_all(strip,0,0,0)
            st['params'] = None
            st['phase'] = 0

def cylon_bounce_step(strip, red, green, blue, eye_size, speed_delay, return_delay):
    st = cylon_state
    num_leds = strip.numPixels()
    set_all(strip,0,0,0)
    pos = st['pos']
    forward = st['forward']
    # Draw current position
    # dim head and tail
    set_pixel(strip, pos, red//10, green//10, blue//10)
    for j in range(1, eye_size+1):
        if pos+j < num_leds:
            set_pixel(strip, pos+j, red, green, blue)
    if pos+eye_size+1 < num_leds:
        set_pixel(strip, pos+eye_size+1, red//10, green//10, blue//10)

    # Move position
    if forward:
        if pos < num_leds - eye_size - 2:
            st['pos'] += 1
        else:
            st['forward'] = False
    else:
        if pos > 0:
            st['pos'] -= 1
        else:
            st['forward'] = True

def twinkle_step(strip, red, green, blue, count, only_one):
    # We'll just randomly light up a single pixel each step
    # If only_one, clear all first
    if only_one:
        set_all(strip,0,0,0)
    idx = random.randint(0, strip.numPixels()-1)
    set_pixel(strip, idx, red, green, blue)

def twinkle_random_step(strip, count, only_one):
    st = twinkle_random_state
    num_leds = strip.numPixels()
    if only_one:
        set_all(strip,0,0,0)
        st['used_indices'] = []
    # Just light up random pixels each step
    idx = random.randint(0,num_leds-1)
    set_pixel(strip, idx, random.randint(0,255), random.randint(0,255), random.randint(0,255))

def sparkle_step(strip, red, green, blue):
    # Turn on a random pixel for one step, then turn it off next step
    st = sparkle_state
    num_leds = strip.numPixels()
    if st['on_pixel'] is None:
        # Turn on a new pixel
        st['on_pixel'] = random.randint(0,num_leds-1)
        set_pixel(strip, st['on_pixel'], red, green, blue)
        st['timer'] = 1
    else:
        # Turn it off
        if st['timer'] > 0:
            st['timer'] -= 1
            if st['timer'] == 0:
                set_pixel(strip, st['on_pixel'], 0,0,0)
                st['on_pixel'] = None

def snow_sparkle_step(strip, red, green, blue):
    # Similar to sparkle but with two white pixels that turn back to base color
    st = snow_sparkle_state
    num_leds = strip.numPixels()
    base_r, base_g, base_b = st['base_color']

    if st['timer'] == 0:
        # place two white pixels
        st['pixels'] = random.sample(range(num_leds), 2)
        for p in st['pixels']:
            set_pixel(strip, p, 255,255,255)
        st['timer'] = 5
    else:
        st['timer'] -= 1
        if st['timer'] == 0:
            # restore base color
            for p in st['pixels']:
                set_pixel(strip,p,red,green,blue)

def running_lights_step(strip, red, green, blue):
    st = running_lights_state
    pos = st['position']
    num_leds = strip.numPixels()

    for i in range(num_leds):
        level = (math.sin((i + pos) / 10.0) + 1) * 127.5
        r = int((level / 255) * red)
        g = int((level / 255) * green)
        b = int((level / 255) * blue)
        set_pixel(strip, i, r, g, b)

    st['position'] += 1

def color_wipe_step(strip, red, green, blue):
    st = color_wipe_state
    num_leds = strip.numPixels()
    if not st['done']:
        if st['index'] < num_leds:
            set_pixel(strip, st['index'], red, green, blue)
            st['index'] += 1
        else:
            st['done'] = True

def rainbow_cycle_step(strip):
    st = rainbow_cycle_state
    step = st['step']
    num_leds = strip.numPixels()

    def wheel(pos):
        if pos < 85:
            return [pos * 3, 255 - pos * 3, 0]
        elif pos < 170:
            pos -= 85
            return [255 - pos * 3, 0, pos * 3]
        else:
            pos -= 170
            return [0, pos * 3, 255 - pos * 3]

    for i in range(num_leds):
        c = wheel((i * 256 // num_leds + step) & 255)
        set_pixel(strip, i, c[0], c[1], c[2])
    st['step'] += 1

def theater_chase_step(strip, red, green, blue):
    # Just chase three LEDs along the strip
    st = theater_chase_state
    num_leds = strip.numPixels()
    i = st['index']
    # Clear first
    set_all(strip,0,0,0)
    for j in range(i, num_leds, 3):
        set_pixel(strip, j, red, green, blue)
    st['index'] = (st['index']+1)%3

def theater_chase_rainbow_step(strip):
    st = theater_chase_rainbow_state
    num_leds = strip.numPixels()
    step = st['step']
    i = st['index']

    def wheel(pos):
        if pos < 85:
            return [pos * 3, 255 - pos * 3, 0]
        elif pos < 170:
            pos -= 85
            return [255 - pos * 3, 0, pos * 3]
        else:
            pos -= 170
            return [0, pos * 3, 255 - pos * 3]

    set_all(strip,0,0,0)
    for j in range(num_leds):
        c = wheel((j+step)%256)
        if (j % 3) == i:
            set_pixel(strip, j, c[0], c[1], c[2])
    st['index'] = (st['index']+1)%3
    if st['index']==0:
        st['step'] += 1

def fire_step(strip, cooling, sparking):
    st = fire_state
    num_leds = strip.numPixels()
    heat = st['heat'] if st['heat'] is not None else [0]*num_leds
    # cool down
    for i in range(num_leds):
        cooldown = random.randint(0, ((cooling * 10) // num_leds) + 2)
        heat[i] = max(0, heat[i] - cooldown)

    # heat diffusion
    for k in range(num_leds - 1, 1, -1):
        heat[k] = (heat[k-1] + heat[k-2] + heat[k-2])//3

    # ignite sparks near bottom
    if random.randint(0,255)<sparking:
        y = random.randint(0,7)
        heat[y] = min(heat[y] + random.randint(160,255),255)

    # map heat to colors
    for j in range(num_leds):
        set_pixel_heat_color(strip, j, heat[j])

    st['heat'] = heat

def set_pixel_heat_color(strip, pixel, temperature):
    t192 = round((temperature/255.0)*191)
    heatramp = (t192 & 0x3F)<<2
    if t192 > 0x80:
        set_pixel(strip, pixel, 255,255,heatramp)
    elif t192 >0x40:
        set_pixel(strip, pixel, 255,heatramp,0)
    else:
        set_pixel(strip, pixel, heatramp,0,0)

# Implement meteor_rain_step and bouncing_colored_balls_step as incremental steps
# Similar logic applies: track position in state, advance by one step each call,
# no internal loops or sleeps.

meteor_rain_state = {'pos':0, 'initialized':False, 'trail_length':10, 'red':255,'green':255,'blue':255,'meteor_size':5,'random_decay':True,'speed_delay':30,'direction':1}
def meteor_rain_step(strip, red, green, blue, meteor_size, meteor_trail_decay, meteor_random_decay, speed_delay):
    st = meteor_rain_state
    num_leds = strip.numPixels()

    # Initialize if needed
    if not st['initialized']:
        st['red'], st['green'], st['blue'] = red, green, blue
        st['meteor_size'] = meteor_size
        st['trail_length'] = meteor_trail_decay
        st['random_decay'] = meteor_random_decay
        st['pos'] = 0
        st['direction'] = 1
        st['initialized'] = True

    # Fade all LEDs one step
    for j in range(num_leds):
        if not st['random_decay'] or random.randint(0,10)>5:
            fade_to_black(strip,j, st['trail_length'])

    # Draw meteor
    for i in range(st['meteor_size']):
        if (st['pos']-i)>=0 and (st['pos']-i)<num_leds:
            set_pixel(strip, st['pos']-i, red, green, blue)

    st['pos'] += st['direction']
    if st['pos'] >= num_leds:
        st['pos'] = 0

bouncing_balls_state = {'init':False,'positions':[],'velocities':[],'clock':[],'colors':[],'gravity':-9.81,'startTime':0}
def bouncing_colored_balls_step(strip, ballCount, colors, continuous):
    # This is a complex animation. For simplicity, we do a small increment each call.
    st = bouncing_balls_state
    num_leds = strip.numPixels()
    if not st['init']:
        st['colors'] = colors
        st['positions'] = [0]*ballCount
        st['velocities'] = [0]*ballCount
        st['clock'] = [time.time()]*ballCount
        st['init'] = True
        set_all(strip,0,0,0)

    # One small increment per call
    set_all(strip,0,0,0)
    for i in range(ballCount):
        t = time.time()
        dt = t - st['clock'][i]
        st['clock'][i] = t
        # position and velocity update
        st['velocities'][i] += st['gravity'] * dt
        st['positions'][i] += st['velocities'][i]

        if st['positions'][i] < 0:
            st['positions'][i] = 0
            st['velocities'][i] = -st['velocities'][i]*0.90 # bounce

        idx = int(st['positions'][i])
        if idx < num_leds:
            c = st['colors'][i % len(st['colors'])]
            set_pixel(strip, idx, c[0], c[1], c[2])
