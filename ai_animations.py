import ast
import json
import math
import os
import random
import re
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime

from animations import blend_colors, clamp, monotonic_millis, scale_color
from led_operations import fade_to_black, fill_all, get_pixel, set_pixel
from config import LED_COUNT

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_TIMEOUT = 300
GEMINI_MAX_OUTPUT_TOKENS = int(os.environ.get("GEMINI_MAX_OUTPUT_TOKENS", "65536"))

AI_ANIMATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai_animations")

_REFERENCE_FILES = ("pacifica.py", "halloween_scene.py", "xmas_scene.py", "fire.py")
_reference_cache = None

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a LED animation programmer. Write Python animations for a __LED_COUNT__-LED \
WS2812B strip running at 50 FPS.

## Strict output rules
- Output ONLY Python code. No markdown fences, no explanation.
- First line must be: ai_state = {}
- Must define exactly one function: def ai_step(strip):
- Use ai_state.setdefault("key", default) to init persistent state.
- Do NOT import anything. Do NOT call strip.show().
- Only these are pre-imported and in scope:
    math, random, time (use time.monotonic() for timing)
    set_pixel(strip, i, r, g, b)  # i: 0-__LED_MAX_IDX__, rgb: 0-255 int
    fill_all(strip, r, g, b)
    fade_to_black(strip, i, fade_value)
    get_pixel(strip, i) -> (r, g, b)
    clamp(v, lo=0, hi=255) -> int
    blend_colors(c1, c2, t) -> (r,g,b)  # t: 0.0-1.0
    scale_color(c, f) -> (r,g,b)  # f: 0.0-1.0
    monotonic_millis() -> int
- strip.numPixels() == __LED_COUNT__. Cache any pre-computed lists in ai_state.
- Always set pixels to non-zero values. Never leave all LEDs black.

## Technique examples — study these carefully, create your own techniques and be a professional light engineer. use complex math to do complex operations.

### Technique 1: Multi-layer sine waves (like ocean, aurora)
ai_state = {}

def ai_step(strip):
    num = strip.numPixels()
    t = time.monotonic()
    for i in range(num):
        # Layer 1: slow green wave
        v1 = (math.sin(i * 0.07 + t * 0.8) + 1) * 0.5
        # Layer 2: fast purple ripple
        v2 = (math.sin(i * 0.13 - t * 1.4) + 1) * 0.5
        # Layer 3: shimmer
        v3 = (math.sin(i * 0.25 + t * 2.2) + 1) * 0.5
        r = clamp(v2 * 120)
        g = clamp(v1 * 200 + v3 * 40)
        b = clamp(v1 * 80 + v2 * 150 + v3 * 30)
        set_pixel(strip, i, r, g, b)

### Technique 2: Heat simulation with color palette
ai_state = {}

HEAT_PALETTE = [
    (0,0,0),(8,0,0),(18,0,0),(40,0,0),(80,0,0),(120,4,0),
    (180,18,0),(220,60,0),(255,100,0),(255,160,0),(255,220,40),(255,255,120),
]

def _palette_color(heat):
    idx = heat * (len(HEAT_PALETTE) - 1) / 255
    lo = int(idx); hi = min(lo + 1, len(HEAT_PALETTE) - 1)
    t = idx - lo
    a, b = HEAT_PALETTE[lo], HEAT_PALETTE[hi]
    return (int(a[0]+(b[0]-a[0])*t), int(a[1]+(b[1]-a[1])*t), int(a[2]+(b[2]-a[2])*t))

def ai_step(strip):
    num = strip.numPixels()
    ai_state.setdefault("heat", [0]*num)
    h = ai_state["heat"]
    for i in range(num):
        h[i] = max(0, h[i] - random.randint(2, 8))
    for i in range(num-1, 1, -1):
        h[i] = (h[i-1] + h[i-2] + h[i-2]) // 3
    if random.randint(0, 255) < 160:
        j = random.randint(0, min(8, num-1))
        h[j] = min(255, h[j] + random.randint(120, 255))
    for i in range(num):
        r, g, b = _palette_color(h[i])
        set_pixel(strip, i, r, g, b)

### Technique 3: Particle system (sparks, embers, shooting stars)
ai_state = {}

def ai_step(strip):
    num = strip.numPixels()
    ai_state.setdefault("particles", [])
    t = time.monotonic()
    for i in range(num):
        fade_to_black(strip, i, 30)
    if random.random() < 0.15:
        ai_state["particles"].append({
            "pos": random.uniform(0, num),
            "vel": random.choice([-1, 1]) * random.uniform(3, 8),
            "life": random.uniform(0.5, 2.0),
            "born": t,
            "color": (random.randint(180,255), random.randint(60,180), random.randint(0,60)),
        })
    alive = []
    for p in ai_state["particles"]:
        age = t - p["born"]
        if age > p["life"]: continue
        p["pos"] += p["vel"] * 0.02
        fade = 1.0 - age / p["life"]
        r, g, b = scale_color(p["color"], fade)
        pi = int(p["pos"])
        if 0 <= pi < num:
            set_pixel(strip, pi, r, g, b)
        alive.append(p)
    ai_state["particles"] = alive

### Technique 4: Physics bounce with gravity
ai_state = {}

def ai_step(strip):
    num = strip.numPixels()
    t = time.monotonic()
    ai_state.setdefault("pos", float(num-1))
    ai_state.setdefault("vel", 0.0)
    ai_state.setdefault("last_t", t)
    dt = min(0.05, t - ai_state["last_t"])
    ai_state["last_t"] = t
    ai_state["vel"] += 600.0 * dt
    ai_state["pos"] += ai_state["vel"] * dt
    if ai_state["pos"] >= num - 1:
        ai_state["pos"] = float(num - 1)
        ai_state["vel"] *= -0.75
    for i in range(num):
        fade_to_black(strip, i, 40)
    p = int(ai_state["pos"])
    speed = abs(ai_state["vel"])
    brightness = min(1.0, speed / 400.0)
    r, g, b = scale_color((255, 120, 0), brightness)
    if 0 <= p < num:
        set_pixel(strip, p, r, g, b)
    if p > 0:
        set_pixel(strip, p-1, *scale_color((255,60,0), brightness*0.4))
    if p < num-1:
        set_pixel(strip, p+1, *scale_color((255,60,0), brightness*0.4))

### Technique 5: Traveling wave with color gradient
ai_state = {}

def ai_step(strip):
    num = strip.numPixels()
    ai_state.setdefault("offset", 0.0)
    t = time.monotonic()
    for i in range(num):
        hue = (i * 360 / num + ai_state["offset"] * 2) % 360
        wave = (math.sin(i * 0.08 + ai_state["offset"] * 0.05) + 1) * 0.5
        v = 0.3 + 0.7 * wave
        h = hue / 60
        c = v
        x = c * (1 - abs(h % 2 - 1))
        if h < 1:   rgb = (c, x, 0)
        elif h < 2: rgb = (x, c, 0)
        elif h < 3: rgb = (0, c, x)
        elif h < 4: rgb = (0, x, c)
        elif h < 5: rgb = (x, 0, c)
        else:       rgb = (c, 0, x)
        set_pixel(strip, i, clamp(rgb[0]*255), clamp(rgb[1]*255), clamp(rgb[2]*255))
    ai_state["offset"] += 1.5
""".replace("__LED_COUNT__", str(LED_COUNT)).replace("__LED_MAX_IDX__", str(LED_COUNT - 1))

# ---------------------------------------------------------------------------
# Reference animations — loaded once, injected into every prompt
# ---------------------------------------------------------------------------


def _load_reference_animations():
    global _reference_cache
    if _reference_cache is not None:
        return _reference_cache

    here = os.path.dirname(os.path.abspath(__file__))
    sections = []
    for fname in _REFERENCE_FILES:
        path = os.path.join(here, fname)
        try:
            with open(path) as f:
                source = f.read()
        except OSError:
            continue
        sections.append(f"### Reference: {fname}\n```python\n{source}\n```")

    if not sections:
        _reference_cache = ""
        return _reference_cache

    _reference_cache = (
        "\n\n## Reference animations — study technique, do NOT copy verbatim\n\n"
        "The files below are hand-tuned production animations from this project. "
        "They use module-level `import` statements and direct `rpi_ws281x` calls "
        "that are NOT available in your sandbox. DO NOT copy imports or module-level "
        "state. Instead, study the *techniques* — palette gradients, layered sine "
        "waves with different bpms/phases, particle physics, multi-stage scene "
        "composition — and translate them into the required `ai_state = {}` + "
        "`def ai_step(strip):` form using only the helpers listed above.\n\n"
        + "\n\n".join(sections)
    )
    return _reference_cache


# ---------------------------------------------------------------------------
# Gemini HTTP client (Google AI Studio)
# ---------------------------------------------------------------------------


def _gemini_stream(user_prompt, temperature=0.7, on_token=None):
    if not GEMINI_API_KEY:
        raise ConnectionError(
            "GEMINI_API_KEY is not set. "
            "Get a free key at https://aistudio.google.com/apikey "
            "and add it to your service environment."
        )

    system_text = SYSTEM_PROMPT + _load_reference_animations()
    payload = json.dumps({
        "system_instruction": {"parts": [{"text": system_text}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": GEMINI_MAX_OUTPUT_TOKENS,
        },
    }).encode()

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:streamGenerateContent?alt=sse&key={GEMINI_API_KEY}"
    )
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    chunks = []
    token_count = 0
    try:
        with urllib.request.urlopen(req, timeout=GEMINI_TIMEOUT) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue
                for cand in obj.get("candidates", []):
                    for part in cand.get("content", {}).get("parts", []):
                        text = part.get("text", "")
                        if text:
                            chunks.append(text)
                            token_count += 1
                            if on_token and token_count % 10 == 0:
                                on_token(token_count, "".join(chunks[-50:]))
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            pass
        hint = " (rate limit — try again in 60s, or switch to gemini-2.0-flash)" if exc.code == 429 else ""
        raise ConnectionError(f"Gemini API error {exc.code}: {exc.reason}{hint}. {body}") from exc
    except urllib.error.URLError as exc:
        raise ConnectionError(f"Gemini unreachable: {exc.reason}") from exc
    except TimeoutError as exc:
        raise TimeoutError("Gemini generation timed out.") from exc

    return "".join(chunks)


# ---------------------------------------------------------------------------
# Public generation API
# ---------------------------------------------------------------------------


def generate_animation(user_prompt, on_token=None):
    return _gemini_stream(f"Create an LED animation: {user_prompt}", temperature=0.7, on_token=on_token)


def edit_animation(existing_code, edit_prompt, on_token=None):
    prompt = (
        f"Here is the current LED animation code:\n\n{existing_code}\n\n"
        f"Modify it to: {edit_prompt}\n\n"
        "Output ONLY the modified Python code. "
        "Preserve the ai_state = {} and def ai_step(strip): structure exactly."
    )
    return _gemini_stream(prompt, temperature=0.5, on_token=on_token)


# ---------------------------------------------------------------------------
# Code extraction
# ---------------------------------------------------------------------------


def extract_code(response_text):
    match = re.search(r"```(?:python)?\s*\n(.*?)```", response_text, re.DOTALL)
    if match:
        return match.group(1).strip()

    lines = response_text.strip().splitlines()
    code_lines = []
    capturing = False
    for line in lines:
        if not capturing and ("ai_state" in line or "def ai_step" in line):
            capturing = True
        if capturing:
            code_lines.append(line)
    if code_lines:
        return "\n".join(code_lines)

    stripped = response_text.strip()
    if "def ai_step" in stripped:
        return stripped

    return ""


# ---------------------------------------------------------------------------
# AST-based validation
# ---------------------------------------------------------------------------

FORBIDDEN_NAMES = frozenset({
    "open", "exec", "eval", "__import__", "compile",
    "globals", "locals", "getattr", "setattr", "delattr",
    "vars", "dir", "type", "breakpoint", "input",
    "memoryview", "bytearray", "classmethod", "staticmethod",
    "property", "super", "object", "__build_class__",
})

FORBIDDEN_MODULES = frozenset({
    "os", "sys", "subprocess", "shutil", "pathlib",
    "socket", "http", "urllib", "importlib", "ctypes",
    "signal", "threading", "multiprocessing", "pickle",
    "shelve", "sqlite3", "io", "builtins", "code",
})


def validate_code(code):
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return False, f"Syntax error: {exc}"

    has_ai_step = False
    has_ai_state = False

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return False, "Import statements are not allowed"

        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in FORBIDDEN_NAMES:
                return False, f"Forbidden call: {func.id}()"
            if isinstance(func, ast.Attribute) and func.attr in FORBIDDEN_NAMES:
                return False, f"Forbidden call: .{func.attr}()"

        if isinstance(node, ast.Attribute):
            if node.attr.startswith("__") and node.attr.endswith("__") and node.attr != "__init__":
                return False, f"Forbidden attribute: {node.attr}"

        if isinstance(node, ast.Name) and node.id in FORBIDDEN_MODULES:
            return False, f"Forbidden reference: {node.id}"

        if isinstance(node, ast.FunctionDef) and node.name == "ai_step":
            has_ai_step = True

        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "ai_state":
                    has_ai_state = True

    if not has_ai_step:
        return False, "Missing required function: def ai_step(strip)"
    if not has_ai_state:
        return False, "Missing required variable: ai_state = {}"

    return True, ""


# ---------------------------------------------------------------------------
# Mock strip for sandbox validation
# ---------------------------------------------------------------------------


class _MockStrip:
    def __init__(self, n=LED_COUNT):
        self._n = n
        self._pixels = [(0, 0, 0)] * n
        self._any_nonblack = False

    def numPixels(self):
        return self._n

    def setPixelColor(self, i, color):
        if 0 <= i < self._n:
            r = (color >> 16) & 0xFF
            g = (color >> 8) & 0xFF
            b = color & 0xFF
            self._pixels[i] = (r, g, b)
            if r or g or b:
                self._any_nonblack = True

    def getPixelColor(self, i):
        if 0 <= i < self._n:
            r, g, b = self._pixels[i]
            return (r << 16) | (g << 8) | b
        return 0

    def show(self):
        pass


def _mock_set_pixel(strip, i, r, g, b):
    r2, g2, b2 = int(max(0, min(255, r))), int(max(0, min(255, g))), int(max(0, min(255, b)))
    if 0 <= i < strip._n:
        strip._pixels[i] = (r2, g2, b2)
        if r2 or g2 or b2:
            strip._any_nonblack = True


def _mock_fill_all(strip, r, g, b):
    r2, g2, b2 = int(max(0, min(255, r))), int(max(0, min(255, g))), int(max(0, min(255, b)))
    strip._pixels = [(r2, g2, b2)] * strip._n
    if r2 or g2 or b2:
        strip._any_nonblack = True


def _mock_fade_to_black(strip, i, fade):
    if 0 <= i < strip._n:
        r, g, b = strip._pixels[i]
        strip._pixels[i] = (max(0, r - fade), max(0, g - fade), max(0, b - fade))


def _mock_get_pixel(strip, i):
    if 0 <= i < strip._n:
        return strip._pixels[i]
    return (0, 0, 0)


# ---------------------------------------------------------------------------
# Sandboxed execution
# ---------------------------------------------------------------------------


class _RestrictedTime:
    @staticmethod
    def monotonic():
        return time.monotonic()


def create_sandbox_globals():
    allowed_builtins = {
        "range": range, "len": len, "int": int, "float": float,
        "abs": abs, "min": min, "max": max, "round": round,
        "True": True, "False": False, "None": None,
        "list": list, "dict": dict, "tuple": tuple,
        "enumerate": enumerate, "zip": zip, "isinstance": isinstance,
        "bool": bool, "str": str, "sorted": sorted, "reversed": reversed,
        "sum": sum, "map": map, "filter": filter,
    }
    return {
        "__builtins__": allowed_builtins,
        "math": math,
        "random": random,
        "time": _RestrictedTime(),
        "set_pixel": set_pixel,
        "fill_all": fill_all,
        "fade_to_black": fade_to_black,
        "get_pixel": get_pixel,
        "clamp": clamp,
        "blend_colors": blend_colors,
        "scale_color": scale_color,
        "monotonic_millis": monotonic_millis,
    }


def compile_ai_animation(code):
    sandbox = create_sandbox_globals()
    try:
        exec(compile(code, "<ai_animation>", "exec"), sandbox)
    except Exception as exc:
        raise ValueError(f"Compilation error: {exc}") from exc

    step_fn = sandbox.get("ai_step")
    if not callable(step_fn):
        raise ValueError("ai_step function not found after execution")

    mock = _MockStrip()
    mock_sandbox = create_sandbox_globals()
    mock_sandbox["set_pixel"] = _mock_set_pixel
    mock_sandbox["fill_all"] = _mock_fill_all
    mock_sandbox["fade_to_black"] = _mock_fade_to_black
    mock_sandbox["get_pixel"] = _mock_get_pixel
    try:
        exec(compile(code, "<ai_animation_test>", "exec"), mock_sandbox)
        test_fn = mock_sandbox.get("ai_step")
        if callable(test_fn):
            for _ in range(15):
                test_fn(mock)
            if not mock._any_nonblack:
                raise ValueError("Animation produced no visible light after 15 frames")
    except ValueError:
        raise
    except Exception:
        pass

    return step_fn, sandbox.get("ai_state", {})


def make_safe_step(step_fn, error_callback):
    error_count = [0]

    def safe_step(strip):
        try:
            step_fn(strip)
            error_count[0] = 0
        except Exception as exc:
            error_count[0] += 1
            fill_all(strip, 0, 0, 0)
            if error_count[0] >= 3:
                error_callback(str(exc))

    return safe_step


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def _sanitize_filename(name):
    return re.sub(r"[^a-z0-9_]", "", name.lower().replace(" ", "_"))[:30]


_MAX_SAVED_ANIMATIONS = 100


def save_ai_animation(name, prompt, code):
    os.makedirs(AI_ANIMATIONS_DIR, exist_ok=True)
    animation_id = uuid.uuid4().hex[:8]
    metadata = {
        "id": animation_id,
        "name": name,
        "prompt": prompt,
        "code": code,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    safe_name = _sanitize_filename(name)
    filename = f"{safe_name}_{animation_id}.json"
    with open(os.path.join(AI_ANIMATIONS_DIR, filename), "w") as f:
        json.dump(metadata, f, indent=2)

    # Prune oldest if over the cap so the SD card doesn't accumulate forever
    existing = load_all_ai_animations()
    if len(existing) > _MAX_SAVED_ANIMATIONS:
        for old in existing[:len(existing) - _MAX_SAVED_ANIMATIONS]:
            delete_ai_animation(old["id"])
    return metadata


def load_all_ai_animations():
    if not os.path.isdir(AI_ANIMATIONS_DIR):
        return []
    animations = []
    for filename in os.listdir(AI_ANIMATIONS_DIR):
        if not filename.endswith(".json"):
            continue
        filepath = os.path.join(AI_ANIMATIONS_DIR, filename)
        try:
            with open(filepath) as f:
                data = json.load(f)
            if "id" in data and "code" in data:
                animations.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    animations.sort(key=lambda a: a.get("created_at", ""))
    return animations


def delete_ai_animation(animation_id):
    if not os.path.isdir(AI_ANIMATIONS_DIR):
        return False
    for filename in os.listdir(AI_ANIMATIONS_DIR):
        if not filename.endswith(".json"):
            continue
        if animation_id in filename:
            filepath = os.path.join(AI_ANIMATIONS_DIR, filename)
            try:
                with open(filepath) as f:
                    data = json.load(f)
                if data.get("id") == animation_id:
                    os.remove(filepath)
                    return True
            except (json.JSONDecodeError, OSError):
                continue
    return False


def prompt_to_name(prompt):
    words = prompt.strip().split()[:5]
    name = " ".join(words).title()
    return name[:27] + "..." if len(name) > 30 else name
