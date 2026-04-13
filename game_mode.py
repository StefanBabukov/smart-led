import math
import random
import time
from threading import Lock

from led_operations import fill_all, set_pixel


def clamp(value, minimum=0, maximum=255):
    return max(minimum, min(maximum, int(value)))


class ZombieGameMode:
    def __init__(self, led_count):
        self.led_count = led_count
        self.lock = Lock()
        self.reset()

    def reset(self):
        with self.lock:
            self._reset_locked()

    def _reset_locked(self):
        self.player_pos = self.led_count // 2
        self.bullets = []
        self.zombies = []
        self.explosions = []
        self.score = 0
        self.wave = 1
        self.elapsed = 0.0
        self.spawn_timer = 0.0
        self.shot_cooldown = 0.0
        self.game_over = False
        self.game_over_timer = 0.0
        self.game_over_origin = float(self.player_pos)
        self.last_time = time.monotonic()

    def snapshot(self):
        with self.lock:
            return {
                "score": self.score,
                "wave": self.wave,
                "game_over": self.game_over,
                "player_pos": self.player_pos,
                "zombie_count": len(self.zombies),
            }

    def move_left(self):
        with self.lock:
            if self.game_over:
                return
            self.player_pos = max(1, self.player_pos - 1)
            self._check_player_collision_locked()

    def move_right(self):
        with self.lock:
            if self.game_over:
                return
            self.player_pos = min(self.led_count - 2, self.player_pos + 1)
            self._check_player_collision_locked()

    def shoot_left(self):
        self._shoot(-1)

    def shoot_right(self):
        self._shoot(1)

    def _shoot(self, direction):
        with self.lock:
            if self.game_over or self.shot_cooldown > 0:
                return

            start_position = float(self.player_pos + direction)
            if 0 <= start_position < self.led_count:
                self.bullets.append(
                    {
                        "pos": start_position,
                        "dir": direction,
                        "speed": 115.0 + random.uniform(-10.0, 12.0),
                    }
                )
                self.shot_cooldown = 0.11

    def step(self, strip):
        with self.lock:
            now = time.monotonic()
            dt = max(0.0, min(0.05, now - self.last_time))
            self.last_time = now

            if self.game_over:
                self.game_over_timer += dt
                self._update_explosions_locked(dt)
                self._render_game_over(strip)
                if self.game_over_timer >= 1.9:
                    self._reset_locked()
                return

            self.elapsed += dt
            self.wave = 1 + int(self.elapsed // 12)
            self.spawn_timer += dt
            self.shot_cooldown = max(0.0, self.shot_cooldown - dt)

            spawn_interval = max(0.18, 1.15 - min(0.9, self.elapsed * 0.018))
            while self.spawn_timer >= spawn_interval:
                self.spawn_timer -= spawn_interval
                self._spawn_zombie_locked()
                overflow_chance = min(0.6, max(0.0, (self.elapsed - 18.0) * 0.02))
                if random.random() < overflow_chance:
                    self._spawn_zombie_locked()

            for bullet in self.bullets:
                bullet["pos"] += bullet["dir"] * bullet["speed"] * dt
            self.bullets = [bullet for bullet in self.bullets if 0 <= bullet["pos"] < self.led_count]

            for zombie in self.zombies:
                zombie["pos"] += zombie["dir"] * zombie["speed"] * dt

            self._resolve_hits_locked()
            self._update_explosions_locked(dt)
            self._check_player_collision_locked()
            self._render_playfield(strip)

    def _spawn_zombie_locked(self):
        from_left = random.random() < 0.5
        direction = 1 if from_left else -1
        position = 0.0 if from_left else float(self.led_count - 1)
        speed = random.uniform(7.0, 16.0) + min(14.0, self.elapsed * 0.16)
        self.zombies.append(
            {
                "pos": position,
                "dir": direction,
                "speed": speed,
                "tone": random.uniform(0.0, 1.0),
            }
        )

    def _resolve_hits_locked(self):
        if not self.bullets or not self.zombies:
            return

        remaining_bullets = []
        hit_indices = set()

        for bullet in self.bullets:
            hit_index = None
            for zombie_index, zombie in enumerate(self.zombies):
                if zombie_index in hit_indices:
                    continue
                if abs(bullet["pos"] - zombie["pos"]) <= 1.15:
                    hit_index = zombie_index
                    break

            if hit_index is None:
                remaining_bullets.append(bullet)
                continue

            zombie = self.zombies[hit_index]
            hit_indices.add(hit_index)
            self.score += 1
            self.explosions.append(
                {
                    "pos": (bullet["pos"] + zombie["pos"]) / 2.0,
                    "age": 0.0,
                }
            )

        self.bullets = remaining_bullets
        if hit_indices:
            self.zombies = [zombie for index, zombie in enumerate(self.zombies) if index not in hit_indices]

    def _update_explosions_locked(self, dt):
        for explosion in self.explosions:
            explosion["age"] += dt
        self.explosions = [explosion for explosion in self.explosions if explosion["age"] < 0.35]

    def _check_player_collision_locked(self):
        if self.game_over:
            return

        for zombie in self.zombies:
            if abs(zombie["pos"] - self.player_pos) <= 0.8:
                self.game_over = True
                self.game_over_timer = 0.0
                self.game_over_origin = float(self.player_pos)
                self.bullets = []
                self.explosions.append({"pos": float(self.player_pos), "age": 0.0})
                return

    def _draw_zombie(self, strip, position, speed, tone):
        center = int(round(position))
        if not (0 <= center < self.led_count):
            return

        speed_ratio = min(1.0, max(0.0, (speed - 7.0) / 20.0))
        body_color = (
            clamp(165 + 70 * speed_ratio),
            clamp(12 + 30 * tone),
            clamp(8 + 10 * tone),
        )
        glow_color = (
            clamp(body_color[0] * 0.3),
            clamp(body_color[1] * 0.18),
            0,
        )

        set_pixel(strip, center, *body_color)
        if center > 0:
            set_pixel(strip, center - 1, *glow_color)
        if center < self.led_count - 1:
            set_pixel(strip, center + 1, *glow_color)

    def _draw_bullet(self, strip, bullet):
        position = int(round(bullet["pos"]))
        if not (0 <= position < self.led_count):
            return

        set_pixel(strip, position, 255, 255, 220)
        trail_position = position - bullet["dir"]
        if 0 <= trail_position < self.led_count:
            set_pixel(strip, trail_position, 80, 80, 60)

    def _draw_explosion(self, strip, explosion):
        center = int(round(explosion["pos"]))
        age_ratio = min(1.0, max(0.0, explosion["age"] / 0.35))
        radius = 1 + int(age_ratio * 2.5)
        core = (
            clamp(255),
            clamp(220 - 80 * age_ratio),
            clamp(80 - 60 * age_ratio),
        )
        halo = (
            clamp(160 - 90 * age_ratio),
            clamp(70 - 50 * age_ratio),
            0,
        )

        for offset in range(-radius, radius + 1):
            pixel = center + offset
            if not (0 <= pixel < self.led_count):
                continue
            if offset == 0:
                set_pixel(strip, pixel, *core)
            else:
                distance_ratio = 1.0 - (abs(offset) / (radius + 0.5))
                set_pixel(
                    strip,
                    pixel,
                    clamp(halo[0] * distance_ratio),
                    clamp(halo[1] * distance_ratio),
                    0,
                )

    def _render_playfield(self, strip):
        fill_all(strip, 0, 0, 0)

        for zombie in self.zombies:
            self._draw_zombie(strip, zombie["pos"], zombie["speed"], zombie["tone"])

        for bullet in self.bullets:
            self._draw_bullet(strip, bullet)

        for explosion in self.explosions:
            self._draw_explosion(strip, explosion)

        player_pos = self.player_pos
        set_pixel(strip, player_pos, 255, 255, 255)
        if player_pos > 0:
            set_pixel(strip, player_pos - 1, 70, 70, 70)
        if player_pos < self.led_count - 1:
            set_pixel(strip, player_pos + 1, 70, 70, 70)

    def _render_game_over(self, strip):
        fill_all(strip, 0, 0, 0)

        pulse = 0.55 + 0.45 * math.sin(self.game_over_timer * 14.0)
        ring_radius = min(self.led_count / 2.0, self.game_over_timer * 58.0)
        fade = 1.0
        if self.game_over_timer > 1.15:
            fade = max(0.0, 1.0 - ((self.game_over_timer - 1.15) / 0.75))

        for index in range(self.led_count):
            distance = abs(index - self.game_over_origin)
            ring_strength = max(0.0, 1.0 - abs(distance - ring_radius) / 2.6)
            ember_strength = max(0.0, 1.0 - distance / (ring_radius + 9.0))

            red = clamp((35 + 210 * max(ember_strength * 0.45, ring_strength * pulse)) * fade)
            green = clamp((8 + 90 * ring_strength * pulse) * fade)
            blue = clamp((20 * ring_strength * 0.3) * fade)
            if red or green or blue:
                set_pixel(strip, index, red, green, blue)

        center = int(round(self.game_over_origin))
        if 0 <= center < self.led_count:
            flash = clamp(255 * fade)
            set_pixel(strip, center, flash, clamp(220 * fade), clamp(170 * fade))

        for explosion in self.explosions:
            self._draw_explosion(strip, explosion)
