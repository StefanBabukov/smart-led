import time
import random
import math
from led_operations import set_pixel, set_all, fade_to_black

# Global state for the Christmas scene
xmas_scene_state = {
    'initialized': False,
    'frame_count': 0,
    'background_offset': 0,
    'hue_base': 0.0,          # Base hue for background
    'hue_direction': 1,       # Direction for hue shifts

    # Elements
    'snowflakes': [],
    'reindeers': [],
    'santa': None,
    'treats': [],

    # Parameters
    'max_snowflakes': 20,
    'snowflake_spawn_chance': 0.1,
    'snowflake_speed_min': 0.02,
    'snowflake_speed_max': 0.05,

    'max_treats': 5,
    'treat_spawn_chance': 0.005,
    'treat_base_color': (255,255,255), # Overridden by specific treat kind
    'treat_speed': 0.02,   # gentle sway
    'treat_sway_period': (50,150),

    'max_reindeers': 2,
    'reindeer_spawn_chance': 0.001,
    'reindeer_speed': 0.1,
    'reindeer_pause_chance': 0.01,

    'santa_spawn_chance': 0.0005,
    'santa_speed': 0.12,

    # Timers and effects
    'twinkle_chance': 0.002,
    'twinkle_pixels': [],  # short-lived sparkles
}

class Snowflake:
    def __init__(self, pos, speed):
        self.pos = float(pos)
        self.speed = speed
        self.color = (255,255,255)  # white snowflake
    
    def update(self):
        self.pos += self.speed

class Treat:
    def __init__(self, pos, color, kind):
        self.pos = float(pos)
        self.color = color
        self.kind = kind
        # Treats gently sway around their initial position
        self.origin = self.pos
        self.direction = random.choice([-1,1])
        self.sway_timer = random.randint(50,150)
    
    def update(self, speed):
        self.sway_timer -= 1
        if self.sway_timer <= 0:
            self.direction *= -1
            self.sway_timer = random.randint(50,150)
        self.pos += self.direction * speed
        # keep treat close to origin
        # clamp slightly so it doesn't wander too far
        if abs(self.pos - self.origin) > 2:
            # reverse direction to bring it back
            self.direction *= -1

class Reindeer:
    # Reindeer: 8 pixels: 7 brown, 1 red nose at the front
    def __init__(self, start_pos, direction):
        self.pos = float(start_pos)
        self.direction = direction
        brown = (139,69,19)
        red = (255,0,0)
        self.colors = [brown]*7 + [red]
        self.width = len(self.colors)
        self.paused = False
        self.pause_timer = 0
    
    def update(self, speed, treats):
        # Simple AI: if treat ahead and close, slow down or pause
        ahead_pos = self.pos + (self.width * self.direction)
        close_treat = any(abs(t.pos - ahead_pos) < 5 for t in treats)
        if close_treat and not self.paused:
            # occasional pause
            if random.random() < 0.3:
                self.paused = True
                self.pause_timer = random.randint(20,50)
            else:
                # slow down
                speed *= 0.5
        
        if self.paused:
            self.pause_timer -= 1
            if self.pause_timer <= 0:
                self.paused = False
        else:
            self.pos += speed * self.direction

class Santa:
    # Santa: length=10, pattern of red, white, face, etc.
    def __init__(self, start_pos, direction):
        self.pos = float(start_pos)
        self.direction = direction
        red = (255,0,0)
        white = (255,255,255)
        black = (0,0,0)
        face = (255,200,150)
        self.colors = [red, white, face, red, black, red, white, red, red, red]
        self.width = len(self.colors)
        self.sparkle_trail = []  # positions Santa left recently
    
    def update(self, speed, treats):
        # Santa speeds up slightly if treat ahead
        ahead_pos = self.pos + (self.width * self.direction)
        close_treat = any(abs(t.pos - ahead_pos) < 10 for t in treats)
        if close_treat:
            speed *= 1.3  # Santa gets excited

        old_pos = self.pos
        self.pos += speed * self.direction
        # leave sparkle trail
        start_p = int(old_pos)
        end_p = int(self.pos)
        trail_positions = range(min(start_p,end_p), max(start_p,end_p)+1)
        for p in trail_positions:
            self.sparkle_trail.append((p,5)) # sparkle lasts 5 frames

def hsv_to_rgb(h, s, v):
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
    return (int(r*255),int(g*255),int(b*255))

def random_treat():
    kinds = ['candy_cane', 'bell', 'ornament']
    kind = random.choice(kinds)
    if kind == 'candy_cane':
        # Represent as white + red pixel
        color = (255,255,255)
    elif kind == 'bell':
        # Gold bell
        color = (255,215,0)
    else:
        # Ornament: choose a calm Christmas color
        palette = [(255,0,0),(0,255,0),(255,255,255),(255,215,0),(200,0,0),(0,200,0)]
        color = random.choice(palette)
    return color, kind

def spawn_snowflake(strip, st):
    if len(st['snowflakes']) < st['max_snowflakes']:
        pos = 0
        speed = random.uniform(st['snowflake_speed_min'], st['snowflake_speed_max'])
        flake = Snowflake(pos, speed)
        st['snowflakes'].append(flake)

def spawn_treat(strip, st):
    if len(st['treats']) < st['max_treats']:
        pos = random.randint(0, strip.numPixels()-1)
        color, kind = random_treat()
        t = Treat(pos, color, kind)
        st['treats'].append(t)

def spawn_reindeer(strip, st):
    if len(st['reindeers']) < st['max_reindeers']:
        start_pos = random.randint(0, strip.numPixels()-10)
        direction = random.choice([-1,1])
        r = Reindeer(start_pos, direction)
        st['reindeers'].append(r)

def spawn_santa(strip, st):
    if st['santa'] is None:
        start_pos = 0 if random.random() > 0.5 else strip.numPixels()-11
        direction = 1 if start_pos == 0 else -1
        st['santa'] = Santa(start_pos, direction)

def update_snowflakes(strip, st):
    new_list = []
    num_leds = strip.numPixels()
    for s in st['snowflakes']:
        s.update()
        if s.pos < num_leds:
            new_list.append(s)
    st['snowflakes'] = new_list

def update_treats(strip, st):
    for t in st['treats']:
        t.update(st['treat_speed'])

def update_reindeers(strip, st):
    new_list = []
    num_leds = strip.numPixels()
    for r in st['reindeers']:
        r.update(st['reindeer_speed'], st['treats'])
        end_pos = int(r.pos) + r.width
        if end_pos >= 0 and r.pos < num_leds:
            new_list.append(r)
    st['reindeers'] = new_list

def update_santa(strip, st):
    if st['santa'] is not None:
        s = st['santa']
        s.update(st['santa_speed'], st['treats'])
        num_leds = strip.numPixels()
        end_pos = int(s.pos) + s.width
        if end_pos < 0 or s.pos >= num_leds:
            # Santa off-screen
            st['santa'] = None
        else:
            # Update sparkle trail: decrement lifetime
            new_trail = []
            for pos, life in s.sparkle_trail:
                if life > 1:
                    new_trail.append((pos, life-1))
            s.sparkle_trail = new_trail

def background_color(i, st, num_leds):
    # Slowly shift hue between 0 (red) and 0.333 (green)
    # hue_base oscillates
    h = st['hue_base']
    # Subtle gradient along strip
    # Let's make the hue vary slightly along the strip
    # and also use a gentle brightness gradient
    length = num_leds
    ratio = i / length
    # We'll shift hue slightly with position
    hue = h + 0.1*math.sin(ratio*2*math.pi)
    hue = hue % 1.0
    # brightness breathing
    v = 0.8 + 0.2*math.sin((st['frame_count']*0.01) + (ratio*2*math.pi))
    s = 1.0
    return hsv_to_rgb(hue, s, v)

def draw_snowflake(strip, pos, color):
    p = int(pos)
    if 0 <= p < strip.numPixels():
        set_pixel(strip, p, *color)

def draw_treat(strip, t):
    p = int(t.pos)
    if 0 <= p < strip.numPixels():
        if t.kind == 'candy_cane':
            # candy cane: 2 pixels if possible
            set_pixel(strip, p, 255,255,255)
            if p+1 < strip.numPixels():
                set_pixel(strip, p+1, 255,0,0)
        else:
            # single pixel
            set_pixel(strip, p, *t.color)

def draw_reindeer(strip, r):
    start = int(r.pos)
    for i, c in enumerate(r.colors):
        pos = start + i
        if 0 <= pos < strip.numPixels():
            set_pixel(strip, pos, *c)

def draw_santa(strip, s):
    start = int(s.pos)
    for i, c in enumerate(s.colors):
        pos = start + i
        if 0 <= pos < strip.numPixels():
            set_pixel(strip, pos, *c)
    # draw sparkle trail
    for pos, life in s.sparkle_trail:
        if 0 <= pos < strip.numPixels():
            # faint sparkle intensity
            intensity = life / 5.0
            r,g,b = 255*intensity,255*intensity,255*intensity
            set_pixel(strip, pos, int(r),int(g),int(b))

def draw_twinkles(strip, st):
    # Twinkles are momentary sparkles that fade quickly
    # We'll handle them separately
    # Each frame, we have a small chance to add a twinkle
    if random.random() < st['twinkle_chance']:
        p = random.randint(0, strip.numPixels()-1)
        st['twinkle_pixels'].append((p, 3)) # pixel, lifespan=3 frames
    
    # update twinkles
    new_twinkles = []
    for p, life in st['twinkle_pixels']:
        if 0 <= p < strip.numPixels():
            intensity = life / 3.0
            set_pixel(strip, p, int(255*intensity), int(255*intensity), int(255*intensity))
        if life > 1:
            new_twinkles.append((p, life-1))
    st['twinkle_pixels'] = new_twinkles

def reset_xmas_scene_state():
    xmas_scene_state.update({
        'initialized': False,
        'frame_count': 0,
        'background_offset': 0,
        'hue_base': 0.0,
        'hue_direction': 1,

        'snowflakes': [],
        'reindeers': [],
        'santa': None,
        'treats': [],

        'twinkle_pixels': []
    })

def xmas_scene_step(strip):
    st = xmas_scene_state
    num_leds = strip.numPixels()

    if not st['initialized']:
        st['initialized'] = True
        set_all(strip,0,0,0)

    st['frame_count'] += 1

    # Fade previous frame a bit for smooth transitions
    fade_to_black(strip, 20, st['frame_count'])

    # Gradually shift hue_base between 0 and ~0.333 (red <-> green)
    if st['hue_direction'] > 0:
        st['hue_base'] += 0.0005
        if st['hue_base'] > 0.33:
            st['hue_base'] = 0.33
            st['hue_direction'] = -1
    else:
        st['hue_base'] -= 0.0005
        if st['hue_base'] < 0.0:
            st['hue_base'] = 0.0
            st['hue_direction'] = 1

    # Spawning elements
    if random.random() < st['snowflake_spawn_chance']:
        spawn_snowflake(strip, st)

    if random.random() < st['treat_spawn_chance']:
        spawn_treat(strip, st)

    if random.random() < st['reindeer_spawn_chance']:
        spawn_reindeer(strip, st)

    if random.random() < st['santa_spawn_chance']:
        spawn_santa(strip, st)

    # Updates
    update_snowflakes(strip, st)
    update_treats(strip, st)
    update_reindeers(strip, st)
    update_santa(strip, st)

    # Draw background gradient
    # Since we faded to black, we draw background again to ensure it's visible
    for i in range(num_leds):
        r,g,b = background_color(i, st, num_leds)
        # We'll blend the background lightly over what's currently there
        # But we already faded, so just set background now
        # Actually, just set it, elements will overwrite as needed.
        set_pixel(strip, i, r,g,b)

    # Draw snow
    for s in st['snowflakes']:
        draw_snowflake(strip, s.pos, s.color)

    # Draw treats
    for t in st['treats']:
        draw_treat(strip, t)

    # Draw reindeers
    for r in st['reindeers']:
        draw_reindeer(strip, r)

    # Draw Santa
    if st['santa'] is not None:
        draw_santa(strip, st['santa'])

    # Draw twinkles
    draw_twinkles(strip, st)
