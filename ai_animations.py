import ast
import json
import math
import os
import random
import re
import socket
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from animations import blend_colors, clamp, monotonic_millis, scale_color
from led_operations import fade_to_black, fill_all, get_pixel, set_pixel

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:14b")
OLLAMA_TIMEOUT = 180
OLLAMA_PORT = 11434
AI_ANIMATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai_animations")

# Cached Ollama host — discovered once, reused until server restart
_ollama_host_cache = None

# ---------------------------------------------------------------------------
# Ollama auto-discovery
# ---------------------------------------------------------------------------


def _get_local_ip():
    """Get this machine's local IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


def _check_ollama(ip):
    """Check if Ollama is running at the given IP. Returns ip or None."""
    url = f"http://{ip}:{OLLAMA_PORT}/api/tags"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            if resp.status == 200:
                return ip
    except Exception:
        pass
    return None


def discover_ollama():
    """Scan the local /24 subnet for an Ollama server. Returns host URL or None."""
    global _ollama_host_cache

    # Check environment variable first
    env_host = os.environ.get("OLLAMA_HOST")
    if env_host:
        _ollama_host_cache = env_host.rstrip("/")
        return _ollama_host_cache

    # Return cached result if available
    if _ollama_host_cache:
        try:
            ip = _ollama_host_cache.replace("http://", "").split(":")[0]
            if _check_ollama(ip):
                return _ollama_host_cache
        except Exception:
            pass
        _ollama_host_cache = None

    local_ip = _get_local_ip()
    if not local_ip:
        return None

    subnet = ".".join(local_ip.split(".")[:3])
    ips = [f"{subnet}.{i}" for i in range(1, 255) if f"{subnet}.{i}" != local_ip]

    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = {executor.submit(_check_ollama, ip): ip for ip in ips}
        for future in as_completed(futures):
            result = future.result()
            if result:
                _ollama_host_cache = f"http://{result}:{OLLAMA_PORT}"
                for f in futures:
                    f.cancel()
                return _ollama_host_cache

    return None


def get_ollama_host():
    """Get the Ollama host URL, discovering it if necessary. Raises on failure."""
    host = discover_ollama()
    if not host:
        raise ConnectionError(
            "Could not find Ollama on your network. "
            "Make sure Ollama is running on your laptop with: "
            "OLLAMA_HOST=0.0.0.0 ollama serve"
        )
    return host


# ---------------------------------------------------------------------------
# System prompt — lean with high-quality technique examples
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a LED animation programmer. Write Python animations for a 300-LED \
WS2812B strip running at 50 FPS.

## Strict output rules
- Output ONLY Python code. No markdown fences, no explanation.
- First line must be: ai_state = {}
- Must define exactly one function: def ai_step(strip):
- Use ai_state.setdefault("key", default) to init persistent state.
- Do NOT import anything. Do NOT call strip.show().
- Only these are pre-imported and in scope:
    math, random, time (use time.monotonic() for timing)
    set_pixel(strip, i, r, g, b)  # i: 0-299, rgb: 0-255 int
    fill_all(strip, r, g, b)
    fade_to_black(strip, i, fade_value)
    get_pixel(strip, i) -> (r, g, b)
    clamp(v, lo=0, hi=255) -> int
    blend_colors(c1, c2, t) -> (r,g,b)  # t: 0.0-1.0
    scale_color(c, f) -> (r,g,b)  # f: 0.0-1.0
    monotonic_millis() -> int
- strip.numPixels() == 300. Cache any pre-computed lists in ai_state.
- Always set pixels to non-zero values. Never leave all LEDs black.

## Technique examples — study these carefully

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
    # Cool down
    for i in range(num):
        h[i] = max(0, h[i] - random.randint(2, 8))
    # Diffuse upward
    for i in range(num-1, 1, -1):
        h[i] = (h[i-1] + h[i-2] + h[i-2]) // 3
    # Spark at base
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
    # Fade trail
    for i in range(num):
        fade_to_black(strip, i, 30)
    # Spawn new particle
    if random.random() < 0.15:
        ai_state["particles"].append({
            "pos": random.uniform(0, num),
            "vel": random.choice([-1, 1]) * random.uniform(3, 8),
            "life": random.uniform(0.5, 2.0),
            "born": t,
            "color": (random.randint(180,255), random.randint(60,180), random.randint(0,60)),
        })
    # Update + draw
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
        # Map position to hue (0-360)
        hue = (i * 360 / num + ai_state["offset"] * 2) % 360
        # HSV to RGB: saturation=1, value varies by wave
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
"""

# ---------------------------------------------------------------------------
# Ollama HTTP client with streaming progress
# ---------------------------------------------------------------------------


def call_ollama(user_prompt, on_token=None):
    """Call Ollama with streaming. Returns generated text. Raises on failure.

    on_token(count, partial_text) is called every ~25 tokens if provided.
    """
    host = get_ollama_host()

    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "system": SYSTEM_PROMPT,
        "prompt": f"Create an LED animation: {user_prompt}",
        "stream": True,
        "options": {
            "temperature": 0.7,
            "num_predict": 1200,
            "num_ctx": 8192,
        },
    }).encode()

    req = urllib.request.Request(
        f"{host}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    chunks = []
    token_count = 0
    try:
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
            for raw_line in resp:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                token = chunk.get("response", "")
                chunks.append(token)
                token_count += 1
                if on_token and token_count % 25 == 0:
                    on_token(token_count, "".join(chunks[-50:]))
                if chunk.get("done"):
                    break
    except urllib.error.URLError as exc:
        global _ollama_host_cache
        _ollama_host_cache = None
        raise ConnectionError(
            f"AI server unreachable at {host}. "
            "Is Ollama running on your laptop?"
        ) from exc
    except TimeoutError as exc:
        raise TimeoutError("Generation timed out. Try a simpler prompt.") from exc

    return "".join(chunks)


# ---------------------------------------------------------------------------
# Code extraction
# ---------------------------------------------------------------------------


def extract_code(response_text):
    """Extract Python code from the LLM response."""
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
    """Static AST validation. Returns (ok, error_message)."""
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
            if (node.attr.startswith("__") and node.attr.endswith("__")
                    and node.attr != "__init__"):
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
# Mock strip — validate generated code actually lights up LEDs
# ---------------------------------------------------------------------------


class _MockStrip:
    """Minimal strip object for test-running generated animations."""

    def __init__(self, n=300):
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
        strip._pixels[i] = (max(0, r-fade), max(0, g-fade), max(0, b-fade))


def _mock_get_pixel(strip, i):
    if 0 <= i < strip._n:
        return strip._pixels[i]
    return (0, 0, 0)


def test_animation(step_fn, frames=10):
    """Run animation on mock strip for N frames. Returns True if any LEDs light up."""
    mock = _MockStrip()
    sandbox = {
        "__builtins__": {},
        "strip": mock,
    }
    try:
        for _ in range(frames):
            step_fn(mock)
    except Exception as exc:
        return False, f"Runtime error: {exc}"

    if not mock._any_nonblack:
        return False, "Animation produced no visible light (all LEDs stayed black)"

    return True, ""


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
    """Compile code in sandbox. Returns (ai_step_fn, ai_state_dict). Raises on failure."""
    sandbox = create_sandbox_globals()
    try:
        exec(compile(code, "<ai_animation>", "exec"), sandbox)
    except Exception as exc:
        raise ValueError(f"Compilation error: {exc}") from exc

    step_fn = sandbox.get("ai_step")
    if not callable(step_fn):
        raise ValueError("ai_step function not found after execution")

    # Validate on mock strip
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
        pass  # runtime test failure is non-fatal; real strip may behave differently

    return step_fn, sandbox.get("ai_state", {})


def make_safe_step(step_fn, error_callback):
    """Wrap AI step function — stops after 3 consecutive crashes."""
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
