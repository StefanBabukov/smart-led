import math
import random
import time

from led_operations import fade_to_black, fill_all, set_pixel


def monotonic_millis():
    return int(time.monotonic() * 1000)


def clamp(value, minimum=0, maximum=255):
    return max(minimum, min(maximum, int(value)))


def blend_colors(color_a, color_b, amount):
    ratio = max(0.0, min(1.0, amount))
    return (
        clamp(color_a[0] + (color_b[0] - color_a[0]) * ratio),
        clamp(color_a[1] + (color_b[1] - color_a[1]) * ratio),
        clamp(color_a[2] + (color_b[2] - color_a[2]) * ratio),
    )


def scale_color(color, factor):
    return (
        clamp(color[0] * factor),
        clamp(color[1] * factor),
        clamp(color[2] * factor),
    )


SPLIT_CYCLONE_COLORS = [
    (255, 40, 40),
    (255, 140, 30),
    (255, 220, 40),
    (90, 255, 120),
    (50, 230, 255),
    (70, 140, 255),
    (180, 90, 255),
    (255, 80, 180),
]

BALL_COLORS = [
    (255, 90, 90),
    (255, 180, 60),
    (255, 235, 90),
    (90, 255, 140),
    (90, 220, 255),
    (110, 140, 255),
    (220, 120, 255),
]

METEOR_PALETTE = [
    (18, 4, 0),
    (60, 14, 4),
    (130, 36, 10),
    (220, 90, 28),
    (255, 155, 60),
    (255, 220, 130),
    (170, 225, 255),
    (90, 170, 255),
    (210, 245, 255),
]


# State containers for animations
fade_in_out_state = {"direction": 1, "brightness": 0}
running_lights_state = {"position": 0}
twinkle_state = {"pixels": []}
twinkle_random_state = {"used_indices": []}
sparkle_state = {"initialized": False, "flash_levels": []}
snow_sparkle_state = {"pixels": [], "timer": 0, "base_color": (16, 16, 16)}
cylon_state = {"pos": 0, "forward": True}
split_cyclones_state = {"depth": 0, "phase": 1, "progress": 0.0, "max_depth": 0}
color_wipe_state = {"index": 0, "done": False, "last_color": None}
rainbow_cycle_state = {"step": 0}
theater_chase_state = {"index": 0}
theater_chase_rainbow_state = {"step": 0, "index": 0}
bouncing_balls_state = {
    "init": False,
    "ball_count": 0,
    "positions": [],
    "velocities": [],
    "launch_times": [],
    "colors": [],
    "gravity": 650.0,
    "restitution": [],
    "last_time": 0.0,
    "settled_since": None,
}
meteor_rain_state = {"pos": 0.0, "speed": 2.2}
wheel_step_state = {"pos": 0}
death_show_state = {
    "start_time": None,
    "last_time": 0.0,
    "waves": [],
    "bursts": [],
    "embers": [],
    "comets": [],
    "next_wave": 0.0,
    "next_burst": 0.0,
    "next_comet": 0.0,
    "finale_flash": False,
}
DEATH_SHOW_DURATION = 30.0


def fade_in_out_step(strip, red, green, blue):
    st = fade_in_out_state
    st["brightness"] += st["direction"]
    if st["brightness"] > 255:
        st["brightness"] = 255
        st["direction"] = -1
    elif st["brightness"] < 0:
        st["brightness"] = 0
        st["direction"] = 1

    val_r = (st["brightness"] * red) // 255
    val_g = (st["brightness"] * green) // 255
    val_b = (st["brightness"] * blue) // 255
    fill_all(strip, val_r, val_g, val_b)


strobe_state = {"count": 0, "on": True, "params": None}


def strobe_step(strip, red, green, blue, strobe_count, flash_delay, end_pause):
    st = strobe_state
    if st["params"] is None:
        st["params"] = (red, green, blue, strobe_count, flash_delay, end_pause)
        st["count"] = 0
        st["on"] = True

    red, green, blue, sc, fd, ep = st["params"]
    if st["count"] < sc:
        if st["on"]:
            fill_all(strip, red, green, blue)
        else:
            fill_all(strip, 0, 0, 0)
        st["on"] = not st["on"]
        st["count"] += 0.5
    else:
        fill_all(strip, 0, 0, 0)
        st["params"] = None


def cylon_bounce_step(strip, red, green, blue, eye_size, speed_delay, return_delay):
    st = cylon_state
    num_leds = strip.numPixels()
    fill_all(strip, 0, 0, 0)
    pos = st["pos"]
    forward = st["forward"]
    set_pixel(strip, pos, red // 10, green // 10, blue // 10)
    for j in range(1, eye_size + 1):
        if pos + j < num_leds:
            set_pixel(strip, pos + j, red, green, blue)
    if pos + eye_size + 1 < num_leds:
        set_pixel(strip, pos + eye_size + 1, red // 10, green // 10, blue // 10)

    if forward:
        if pos < num_leds - eye_size - 2:
            st["pos"] += 1
        else:
            st["forward"] = False
    else:
        if pos > 0:
            st["pos"] -= 1
        else:
            st["forward"] = True


def draw_cyclone_eye(strip, center, color, direction):
    num_leds = strip.numPixels()
    falloff = [0.18, 0.55, 1.0, 0.55, 0.18]
    for offset, scale in zip(range(-2, 3), falloff):
        index = center + offset
        if 0 <= index < num_leds:
            set_pixel(strip, index, *scale_color(color, scale))

    sparkle_index = center + direction
    if 0 <= sparkle_index < num_leds:
        sparkle_color = blend_colors(color, (255, 255, 255), 0.25)
        set_pixel(strip, sparkle_index, *sparkle_color)


def split_cyclones_step(strip):
    st = split_cyclones_state
    num_leds = strip.numPixels()
    min_segment_length = 16

    if st["max_depth"] == 0:
        st["max_depth"] = max(0, int(math.log2(max(1, num_leds // min_segment_length))))

    fill_all(strip, 0, 0, 0)

    segment_count = 2 ** st["depth"]
    segment_length = num_leds / segment_count
    collision_reached = True

    for segment_index in range(segment_count):
        segment_start = int(round(segment_index * segment_length))
        segment_end = int(round((segment_index + 1) * segment_length)) - 1
        if segment_index == segment_count - 1:
            segment_end = num_leds - 1

        if segment_start >= segment_end:
            continue

        max_progress = max(0.0, (segment_end - segment_start - 3) / 2.0)
        progress = min(st["progress"], max_progress)
        left_pos = int(round(segment_start + progress))
        right_pos = int(round(segment_end - progress))

        if progress < max_progress:
            collision_reached = False

        left_color = SPLIT_CYCLONE_COLORS[(segment_index + st["depth"]) % len(SPLIT_CYCLONE_COLORS)]
        right_color = SPLIT_CYCLONE_COLORS[(segment_index + st["depth"] + 3) % len(SPLIT_CYCLONE_COLORS)]

        draw_cyclone_eye(strip, left_pos, left_color, 1)
        draw_cyclone_eye(strip, right_pos, right_color, -1)

    st["progress"] += 1.35
    if collision_reached:
        if st["phase"] > 0:
            if st["depth"] < st["max_depth"]:
                st["depth"] += 1
            else:
                st["phase"] = -1
        else:
            if st["depth"] > 0:
                st["depth"] -= 1
            else:
                st["phase"] = 1
        st["progress"] = 0.0


def twinkle_step(strip, red, green, blue, count, only_one):
    if only_one:
        fill_all(strip, 0, 0, 0)
    idx = random.randint(0, strip.numPixels() - 1)
    set_pixel(strip, idx, red, green, blue)


def twinkle_random_step(strip, count, only_one):
    st = twinkle_random_state
    num_leds = strip.numPixels()
    if only_one:
        fill_all(strip, 0, 0, 0)
        st["used_indices"] = []
    idx = random.randint(0, num_leds - 1)
    set_pixel(strip, idx, random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))


def sparkle_step(strip, red, green, blue):
    st = sparkle_state
    num_leds = strip.numPixels()
    base_color = (255, 195, 120)
    flash_color = (255, 250, 235)

    if not st["initialized"] or len(st["flash_levels"]) != num_leds:
        st["flash_levels"] = [0] * num_leds
        st["initialized"] = True

    flash_count = random.randint(2, max(4, num_leds // 55))
    for _ in range(flash_count):
        st["flash_levels"][random.randint(0, num_leds - 1)] = random.randint(180, 255)

    for i in range(num_leds):
        st["flash_levels"][i] = max(0, st["flash_levels"][i] - random.randint(35, 70))
        level = st["flash_levels"][i] / 255.0
        color = blend_colors(base_color, flash_color, level)
        set_pixel(strip, i, *color)


def snow_sparkle_step(strip, red, green, blue):
    st = snow_sparkle_state
    num_leds = strip.numPixels()

    if st["timer"] == 0:
        st["pixels"] = random.sample(range(num_leds), 2)
        for p in st["pixels"]:
            set_pixel(strip, p, 255, 255, 255)
        st["timer"] = 5
    else:
        st["timer"] -= 1
        if st["timer"] == 0:
            for p in st["pixels"]:
                set_pixel(strip, p, red, green, blue)


def running_lights_step(strip, red, green, blue):
    st = running_lights_state
    pos = st["position"]
    num_leds = strip.numPixels()

    for i in range(num_leds):
        level = (math.sin((i + pos) / 10.0) + 1) * 127.5
        ratio = level / 255.0
        set_pixel(strip, i, red * ratio, green * ratio, blue * ratio)

    st["position"] += 1


def color_wipe_step(strip, red, green, blue):
    st = color_wipe_state
    num_leds = strip.numPixels()
    current_color = (red, green, blue)

    if st["last_color"] != current_color:
        st["index"] = 0
        st["done"] = False
        st["last_color"] = current_color
        fill_all(strip, 0, 0, 0)

    if not st["done"]:
        if st["index"] < num_leds:
            set_pixel(strip, st["index"], red, green, blue)
            st["index"] += 1
        else:
            st["done"] = True


def rainbow_cycle_step(strip):
    st = rainbow_cycle_state
    step = st["step"]
    num_leds = strip.numPixels()

    def wheel(pos):
        if pos < 85:
            return [pos * 3, 255 - pos * 3, 0]
        if pos < 170:
            pos -= 85
            return [255 - pos * 3, 0, pos * 3]
        pos -= 170
        return [0, pos * 3, 255 - pos * 3]

    for i in range(num_leds):
        c = wheel((i * 256 // num_leds + step) & 255)
        set_pixel(strip, i, c[0], c[1], c[2])
    st["step"] += 1


def theater_chase_step(strip, red, green, blue):
    st = theater_chase_state
    num_leds = strip.numPixels()
    fill_all(strip, 0, 0, 0)
    for j in range(st["index"], num_leds, 3):
        set_pixel(strip, j, red, green, blue)
    st["index"] = (st["index"] + 1) % 3


def theater_chase_rainbow_step(strip):
    st = theater_chase_rainbow_state
    num_leds = strip.numPixels()
    step = st["step"]
    offset = st["index"]

    def wheel(pos):
        if pos < 85:
            return [pos * 3, 255 - pos * 3, 0]
        if pos < 170:
            pos -= 85
            return [255 - pos * 3, 0, pos * 3]
        pos -= 170
        return [0, pos * 3, 255 - pos * 3]

    fill_all(strip, 0, 0, 0)
    for j in range(num_leds):
        if (j % 3) == offset:
            c = wheel((j + step) % 256)
            set_pixel(strip, j, c[0], c[1], c[2])

    st["index"] = (st["index"] + 1) % 3
    if st["index"] == 0:
        st["step"] += 1


def meteor_color_for_offset(offset, meteor_size, trail_length):
    if offset < meteor_size:
        head_palette = [
            (255, 250, 240),
            (205, 235, 255),
            (130, 200, 255),
            (90, 165, 255),
        ]
        return head_palette[min(offset, len(head_palette) - 1)]

    trail_offset = offset - meteor_size
    ratio = min(1.0, trail_offset / max(1, trail_length - 1))
    if ratio < 0.45:
        return blend_colors((80, 150, 255), (255, 210, 120), ratio / 0.45)
    return blend_colors((255, 210, 120), (45, 8, 0), (ratio - 0.45) / 0.55)


def meteor_rain_step(strip, red, green, blue, meteor_size, meteor_trail_decay, meteor_random_decay, speed_delay):
    st = meteor_rain_state
    num_leds = strip.numPixels()
    trail_length = max(18, meteor_trail_decay // 2)
    head_size = max(3, meteor_size // 2)

    for j in range(num_leds):
        fade_to_black(strip, j, 20)

    head_position = int(round(st["pos"]))
    total_length = head_size + trail_length
    for offset in range(total_length):
        pixel = head_position - offset
        if 0 <= pixel < num_leds:
            set_pixel(strip, pixel, *meteor_color_for_offset(offset, head_size, trail_length))

    st["pos"] += st["speed"]
    if st["pos"] - total_length > num_leds:
        st["pos"] = 0.0


def reset_death_show_state():
    death_show_state.update(
        {
            "start_time": None,
            "last_time": 0.0,
            "waves": [],
            "bursts": [],
            "embers": [],
            "comets": [],
            "next_wave": 0.0,
            "next_burst": 0.0,
            "next_comet": 0.0,
            "finale_flash": False,
        }
    )


def add_frame_color(frame, index, color):
    if 0 <= index < len(frame):
        frame[index][0] = clamp(frame[index][0] + color[0])
        frame[index][1] = clamp(frame[index][1] + color[1])
        frame[index][2] = clamp(frame[index][2] + color[2])


def draw_frame_glow(frame, center, radius, color, falloff_power=1.7):
    start = max(0, int(math.floor(center - radius - 1)))
    end = min(len(frame) - 1, int(math.ceil(center + radius + 1)))
    safe_radius = max(0.001, radius)
    for index in range(start, end + 1):
        distance = abs(index - center)
        if distance > safe_radius:
            continue
        strength = (1.0 - (distance / safe_radius)) ** falloff_power
        add_frame_color(frame, index, scale_color(color, strength))


def spawn_death_wave(origin, speed, width, color, strength=1.0):
    death_show_state["waves"].append(
        {
            "origin": origin,
            "radius": 0.0,
            "speed": speed,
            "width": width,
            "color": color,
            "strength": strength,
        }
    )


def spawn_death_burst(origin, size_scale=1.0):
    palette_core = random.choice(
        [
            ((255, 210, 145), (255, 110, 20)),
            ((255, 235, 190), (255, 70, 18)),
            ((210, 230, 255), (255, 120, 38)),
        ]
    )
    core_color, halo_color = palette_core
    death_show_state["bursts"].append(
        {
            "origin": origin,
            "age": 0.0,
            "duration": random.uniform(0.65, 1.05) * size_scale,
            "radius": random.uniform(5.0, 14.0) * size_scale,
            "core": core_color,
            "halo": halo_color,
        }
    )

    ember_count = max(6, int(random.randint(7, 14) * size_scale))
    for _ in range(ember_count):
        direction = random.choice([-1.0, 1.0])
        if random.random() < 0.2:
            direction *= random.uniform(0.15, 0.5)
        speed = direction * random.uniform(12.0, 58.0) * size_scale
        ember_color = blend_colors(halo_color, core_color, random.random() * 0.65)
        death_show_state["embers"].append(
            {
                "pos": origin,
                "vel": speed,
                "age": 0.0,
                "life": random.uniform(0.55, 1.6) * size_scale,
                "color": ember_color,
            }
        )


def spawn_death_comet(num_leds, direction=None):
    go_right = direction if direction is not None else random.choice([True, False])
    head_color = random.choice(
        [
            (255, 245, 220),
            (255, 220, 150),
            (210, 235, 255),
        ]
    )
    trail_color = random.choice(
        [
            (255, 90, 12),
            (255, 140, 32),
            (175, 70, 14),
        ]
    )
    length = random.uniform(14.0, 28.0)
    margin = random.uniform(3.0, 16.0)
    death_show_state["comets"].append(
        {
            "pos": -margin if go_right else (num_leds - 1.0 + margin),
            "speed": random.uniform(34.0, 86.0) * (1.0 if go_right else -1.0),
            "length": length,
            "head": head_color,
            "trail": trail_color,
        }
    )


def draw_death_wave(frame, wave):
    ring_center = wave["origin"]
    radius = wave["radius"]
    width = wave["width"]
    start = max(0, int(math.floor(ring_center - radius - width - 2)))
    end = min(len(frame) - 1, int(math.ceil(ring_center + radius + width + 2)))

    for index in range(start, end + 1):
        distance = abs(index - ring_center)
        ring_distance = abs(distance - radius)
        if ring_distance > width:
            continue
        strength = (1.0 - (ring_distance / max(0.001, width))) * wave["strength"]
        add_frame_color(frame, index, scale_color(wave["color"], strength))


def draw_death_burst(frame, burst):
    age_ratio = min(1.0, max(0.0, burst["age"] / burst["duration"]))
    radius = burst["radius"] * age_ratio
    center = burst["origin"]
    pulse = 0.6 + 0.4 * math.sin(age_ratio * math.pi)
    draw_frame_glow(frame, center, 1.6 + radius * 0.18, scale_color(burst["core"], pulse), 1.4)

    ring_width = max(1.5, 3.8 * (1.0 - age_ratio * 0.55))
    start = max(0, int(math.floor(center - radius - ring_width - 1)))
    end = min(len(frame) - 1, int(math.ceil(center + radius + ring_width + 1)))
    for index in range(start, end + 1):
        ring_distance = abs(abs(index - center) - radius)
        if ring_distance > ring_width:
            continue
        ring_strength = (1.0 - (ring_distance / ring_width)) * (1.0 - age_ratio * 0.35)
        add_frame_color(frame, index, scale_color(burst["halo"], ring_strength))


def draw_death_ember(frame, ember):
    age_ratio = min(1.0, max(0.0, ember["age"] / ember["life"]))
    ember_color = scale_color(ember["color"], 1.0 - age_ratio)
    draw_frame_glow(frame, ember["pos"], 1.4 + age_ratio * 0.9, ember_color, 2.3)


def draw_death_comet(frame, comet):
    direction = 1.0 if comet["speed"] >= 0 else -1.0
    head_position = comet["pos"]
    draw_frame_glow(frame, head_position, 2.8, comet["head"], 1.35)

    trail_steps = max(8, int(comet["length"]))
    for step in range(1, trail_steps + 1):
        offset = head_position - (step * direction)
        ratio = step / trail_steps
        trail_color = blend_colors(comet["head"], comet["trail"], min(1.0, ratio * 1.1))
        add_frame_color(frame, int(round(offset)), scale_color(trail_color, 1.0 - ratio * 0.82))


def death_show_step(strip):
    st = death_show_state
    now = time.monotonic()
    num_leds = strip.numPixels()

    if st["start_time"] is None or (now - st["start_time"]) >= DEATH_SHOW_DURATION:
        reset_death_show_state()
        st["start_time"] = now
        st["last_time"] = now

    elapsed = now - st["start_time"]
    dt = min(0.05, max(0.0, now - st["last_time"]))
    st["last_time"] = now
    frame = [[0, 0, 0] for _ in range(num_leds)]

    base_gain = 0.2 + 0.4 * (elapsed / DEATH_SHOW_DURATION)
    for index in range(num_leds):
        ember_wave = 0.5 + 0.5 * math.sin(index * 0.11 + elapsed * 2.2)
        ember_ripple = 0.5 + 0.5 * math.sin(index * 0.037 - elapsed * 4.6)
        red = 6 + ((18 * ember_wave) + (28 * ember_ripple)) * base_gain
        green = 1 + red * (0.12 + 0.04 * ember_wave)
        blue = 1 + max(0.0, elapsed - 21.0) * 0.8 * (0.3 + 0.7 * ember_ripple)
        frame[index][0] = clamp(red)
        frame[index][1] = clamp(green)
        frame[index][2] = clamp(blue * 0.18)

    center = (num_leds - 1) / 2.0
    scanner_primary = ((math.sin(elapsed * 1.25) + 1.0) * 0.5) * (num_leds - 1)
    draw_frame_glow(frame, scanner_primary, 13.0, (180, 24, 18), 1.8)

    if elapsed > 8.0:
        scanner_secondary = ((math.sin(elapsed * 2.05 + 1.3) + 1.0) * 0.5) * (num_leds - 1)
        draw_frame_glow(frame, scanner_secondary, 10.0, (255, 145, 30), 2.0)

    if elapsed > 24.0:
        chase_strength = min(1.0, (elapsed - 24.0) / 4.5)
        chase_offset = int(elapsed * 15.0) % 3
        for index in range(chase_offset, num_leds, 3):
            add_frame_color(frame, index, scale_color((160, 70, 18), chase_strength))

    if elapsed < 10.0:
        wave_interval = 0.95 - (elapsed * 0.03)
        burst_interval = 1.25 - (elapsed * 0.035)
        comet_interval = 1.8
        while elapsed >= st["next_wave"]:
            spawn_death_wave(center + random.uniform(-8.0, 8.0), random.uniform(26.0, 42.0), 3.4, (255, 150, 40), 1.0)
            st["next_wave"] += max(0.45, wave_interval)
        while elapsed >= st["next_burst"]:
            spawn_death_burst(center + random.uniform(-22.0, 22.0), 1.0)
            st["next_burst"] += max(0.55, burst_interval)
        while elapsed >= st["next_comet"]:
            spawn_death_comet(num_leds)
            st["next_comet"] += comet_interval
    elif elapsed < 20.0:
        while elapsed >= st["next_wave"]:
            origin = 0.0 if int(st["next_wave"] * 10) % 2 == 0 else (num_leds - 1.0)
            spawn_death_wave(origin, random.uniform(30.0, 48.0), 2.9, (255, 235, 175), 0.95)
            spawn_death_wave(center, random.uniform(20.0, 32.0), 2.5, (255, 70, 20), 0.8)
            st["next_wave"] += 0.72
        while elapsed >= st["next_burst"]:
            spawn_death_burst(random.uniform(0.16, 0.84) * (num_leds - 1), 0.95)
            st["next_burst"] += 0.88
        while elapsed >= st["next_comet"]:
            spawn_death_comet(num_leds, direction=(int(st["next_comet"] * 5) % 2 == 0))
            st["next_comet"] += 0.58
    else:
        while elapsed >= st["next_wave"]:
            spawn_death_wave(center, random.uniform(38.0, 58.0), 3.6, (255, 245, 210), 1.0)
            spawn_death_wave((num_leds - 1) * 0.24, random.uniform(26.0, 44.0), 2.6, (255, 90, 22), 0.75)
            spawn_death_wave((num_leds - 1) * 0.76, random.uniform(26.0, 44.0), 2.6, (255, 90, 22), 0.75)
            st["next_wave"] += 0.46
        while elapsed >= st["next_burst"]:
            cluster_center = random.uniform(0.08, 0.92) * (num_leds - 1)
            spawn_death_burst(cluster_center, 1.15)
            if random.random() < 0.7:
                spawn_death_burst(cluster_center + random.uniform(-18.0, 18.0), 0.8)
            st["next_burst"] += 0.53
        while elapsed >= st["next_comet"]:
            spawn_death_comet(num_leds)
            spawn_death_comet(num_leds)
            st["next_comet"] += 0.38
        if elapsed >= 29.15 and not st["finale_flash"]:
            spawn_death_burst(center, 1.7)
            spawn_death_wave(center, 64.0, 4.6, (255, 255, 235), 1.25)
            st["finale_flash"] = True

    active_waves = []
    max_distance = num_leds + 8.0
    for wave in st["waves"]:
        wave["radius"] += wave["speed"] * dt
        wave["strength"] *= 0.994
        if wave["radius"] - wave["width"] <= max_distance and wave["strength"] > 0.03:
            draw_death_wave(frame, wave)
            active_waves.append(wave)
    st["waves"] = active_waves

    active_bursts = []
    for burst in st["bursts"]:
        burst["age"] += dt
        if burst["age"] <= burst["duration"]:
            draw_death_burst(frame, burst)
            active_bursts.append(burst)
    st["bursts"] = active_bursts

    active_embers = []
    for ember in st["embers"]:
        ember["age"] += dt
        ember["pos"] += ember["vel"] * dt
        ember["vel"] *= 0.989
        if 0.0 <= ember["pos"] < num_leds and ember["age"] <= ember["life"]:
            draw_death_ember(frame, ember)
            active_embers.append(ember)
    st["embers"] = active_embers

    active_comets = []
    for comet in st["comets"]:
        comet["pos"] += comet["speed"] * dt
        if -comet["length"] <= comet["pos"] <= (num_leds - 1 + comet["length"]):
            draw_death_comet(frame, comet)
            active_comets.append(comet)
    st["comets"] = active_comets

    if elapsed > 27.0:
        full_strip_flash = max(0.0, (elapsed - 27.0) / 3.0)
        pulse = 0.5 + 0.5 * math.sin(elapsed * 18.0)
        flash_color = scale_color((150, 50, 10), full_strip_flash * pulse * 0.6)
        for index in range(num_leds):
            add_frame_color(frame, index, flash_color)

    for index, color in enumerate(frame):
        set_pixel(strip, index, color[0], color[1], color[2])


def initialize_bouncing_balls(strip, ball_count, colors):
    now = time.monotonic()
    st = bouncing_balls_state
    st["ball_count"] = ball_count
    st["positions"] = []
    st["velocities"] = []
    st["launch_times"] = []
    st["colors"] = []
    st["restitution"] = []
    for i in range(ball_count):
        add_bouncing_ball(st, colors[i % len(colors)], now + (i * 0.18))
    st["last_time"] = now
    st["settled_since"] = None
    st["init"] = True


def add_bouncing_ball(st, color, launch_time):
    ball_index = len(st["positions"])
    st["positions"].append(0.0)
    st["velocities"].append(0.0)
    st["launch_times"].append(launch_time)
    st["colors"].append(color)
    restitution = 0.48 + (0.08 * (ball_index % 5)) + random.uniform(-0.02, 0.02)
    st["restitution"].append(max(0.42, min(0.84, restitution)))


def sync_bouncing_ball_count(ball_count, colors):
    st = bouncing_balls_state
    if ball_count == st["ball_count"]:
        return

    now = time.monotonic()
    if ball_count > st["ball_count"]:
        for i in range(st["ball_count"], ball_count):
            add_bouncing_ball(st, colors[i % len(colors)], now + ((i - st["ball_count"]) * 0.16))
    else:
        st["positions"] = st["positions"][:ball_count]
        st["velocities"] = st["velocities"][:ball_count]
        st["launch_times"] = st["launch_times"][:ball_count]
        st["colors"] = st["colors"][:ball_count]
        st["restitution"] = st["restitution"][:ball_count]

    st["ball_count"] = ball_count
    st["settled_since"] = None


def bouncing_colored_balls_step(strip, ball_count, colors, continuous):
    st = bouncing_balls_state
    num_leds = strip.numPixels()
    floor_position = max(1.0, num_leds - 1.0)

    if not st["init"]:
        initialize_bouncing_balls(strip, ball_count, colors)
    else:
        sync_bouncing_ball_count(ball_count, colors)

    now = time.monotonic()
    dt = min(0.05, max(0.0, now - st["last_time"]))
    st["last_time"] = now
    fill_all(strip, 0, 0, 0)

    all_settled = True
    for i in range(ball_count):
        if now < st["launch_times"][i]:
            all_settled = False
            continue

        st["velocities"][i] += st["gravity"] * dt
        st["positions"][i] += st["velocities"][i] * dt

        if st["positions"][i] >= floor_position:
            st["positions"][i] = floor_position
            if abs(st["velocities"][i]) > 35:
                st["velocities"][i] = -st["velocities"][i] * st["restitution"][i]
                all_settled = False
            else:
                st["velocities"][i] = 0.0
        else:
            all_settled = False

        position = int(round(st["positions"][i]))
        color = st["colors"][i]
        set_pixel(strip, position, *color)
        if position > 0:
            set_pixel(strip, position - 1, *scale_color(color, 0.45))

    if all_settled:
        if st["settled_since"] is None:
            st["settled_since"] = now
        elif now - st["settled_since"] > 0.7:
            initialize_bouncing_balls(strip, ball_count, colors)
    else:
        st["settled_since"] = None


def wheel_step(strip, c1=(255, 0, 0), c2=(0, 255, 0), step=500):
    st = wheel_step_state
    num_leds = strip.numPixels()
    pos = st["pos"]
    for i in range(num_leds):
        ratio = ((i + pos) % step) / step
        r = int(c1[0] * (1 - ratio) + c2[0] * ratio)
        g = int(c1[1] * (1 - ratio) + c2[1] * ratio)
        b = int(c1[2] * (1 - ratio) + c2[2] * ratio)
        set_pixel(strip, i, r, g, b)
    st["pos"] += 1
