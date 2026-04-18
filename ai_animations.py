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
OLLAMA_TIMEOUT = 120
OLLAMA_PORT = 11434
AI_ANIMATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai_animations")
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

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
        # Verify it's still alive
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

    # Build list of IPs to scan (/24 subnet)
    subnet = ".".join(local_ip.split(".")[:3])
    ips = [f"{subnet}.{i}" for i in range(1, 255) if f"{subnet}.{i}" != local_ip]

    # Scan in parallel (50 threads, each with 1.5s timeout)
    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = {executor.submit(_check_ollama, ip): ip for ip in ips}
        for future in as_completed(futures):
            result = future.result()
            if result:
                _ollama_host_cache = f"http://{result}:{OLLAMA_PORT}"
                # Cancel remaining futures
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
# Reference animation loader
# ---------------------------------------------------------------------------

# Animation files to read for reference examples (relative to project dir).
# These are curated for instructiveness — complex enough to teach patterns,
# not so long they blow up the context window.
REFERENCE_FILES = {
    "fire.py": "Fire simulation with heat diffusion and color palette lookup",
    "pacifica.py": "Ocean waves using layered sine waves, BPM timing, color palettes, and whitecap effects",
    "animations.py": "Core animation library with physics, particles, meteors, sparkles, and wave effects",
}

# Only include these functions from animations.py (skip trivial ones)
ANIMATIONS_PY_FUNCTIONS = [
    "sparkle_step",
    "split_cyclones_step",
    "draw_cyclone_eye",
    "meteor_rain_step",
    "meteor_color_for_offset",
    "bouncing_colored_balls_step",
    "death_show_step",
    "draw_frame_glow",
    "add_frame_color",
    "spawn_death_burst",
    "spawn_death_wave",
    "spawn_death_comet",
    "draw_death_wave",
    "draw_death_burst",
    "draw_death_ember",
    "draw_death_comet",
]


def _extract_functions(source, function_names):
    """Extract specific function definitions from Python source code."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ""

    lines = source.splitlines()
    extracted = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in function_names:
            # Get the function source lines
            start = node.lineno - 1
            end = node.end_lineno if hasattr(node, "end_lineno") else start + 1
            func_lines = lines[start:end]
            extracted.append("\n".join(func_lines))

    return "\n\n".join(extracted)


def _extract_top_level_data(source):
    """Extract top-level variable assignments (palettes, state dicts, constants)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ""

    lines = source.splitlines()
    extracted = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            start = node.lineno - 1
            end = node.end_lineno if hasattr(node, "end_lineno") else start + 1
            extracted.append("\n".join(lines[start:end]))

    return "\n".join(extracted)


def _load_reference_animations():
    """Load and format reference animation code for the prompt."""
    sections = []

    for filename, description in REFERENCE_FILES.items():
        filepath = os.path.join(PROJECT_DIR, filename)
        if not os.path.isfile(filepath):
            continue

        try:
            with open(filepath) as f:
                source = f.read()
        except OSError:
            continue

        if filename == "animations.py":
            # Extract only the interesting functions + their supporting data
            data = _extract_top_level_data(source)
            funcs = _extract_functions(source, ANIMATIONS_PY_FUNCTIONS)
            if funcs:
                content = data + "\n\n" + funcs if data else funcs
                sections.append(
                    f"### Reference: {filename}\n"
                    f"# {description}\n"
                    f"# Selected functions showing physics, particles, and complex effects:\n\n"
                    f"{content}"
                )
        else:
            # Include the whole file (fire.py ~1.7KB, pacifica.py ~6.6KB)
            # Strip import lines since the model shouldn't use them
            filtered = "\n".join(
                line for line in source.splitlines()
                if not line.startswith("import ") and not line.startswith("from ")
            )
            sections.append(
                f"### Reference: {filename}\n"
                f"# {description}\n\n"
                f"{filtered}"
            )

    return "\n\n".join(sections)


# Build the reference section once at import time
_REFERENCE_ANIMATIONS = _load_reference_animations()

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a LED animation programmer. You write Python step functions for a \
300-LED WS2812B strip running at 50 FPS.

## Rules
1. Write EXACTLY ONE function named `ai_step(strip)` that renders one frame.
2. Declare a module-level dict `ai_state = {}` BEFORE the function.
   Inside ai_step, use `ai_state.setdefault("key", default)` to initialise \
persistent state on the first frame.
3. Available functions (already in scope — do NOT import them):
   - set_pixel(strip, pixel_index, red, green, blue)   # index 0-299, RGB 0-255
   - fill_all(strip, red, green, blue)                  # fill every LED
   - fade_to_black(strip, led_no, fade_value)           # dim one pixel
   - get_pixel(strip, led_no) -> (r, g, b)             # read a pixel
   - clamp(value, minimum=0, maximum=255) -> int
   - blend_colors(color_a, color_b, amount) -> (r,g,b)  # amount 0.0-1.0
   - scale_color(color, factor) -> (r,g,b)              # factor 0.0-1.0
   - monotonic_millis() -> int                           # ms since boot
4. math, random, and time are already imported. Use time.monotonic() for \
timing, math for trigonometry and noise, random for randomness.
5. strip.numPixels() returns 300.
6. ai_step is called ~50 times per second. Keep it fast:
   - Avoid allocating large lists every frame — cache them in ai_state.
   - Prefer simple loops over nested O(n^2) logic.
7. Do NOT import anything. Do NOT use print, open, os, sys, subprocess, \
eval, exec, __import__, or any I/O.
8. Do NOT call strip.show() — the caller handles that.
9. Output ONLY the Python code. No explanations, no markdown fences.
10. do not just use the available functions, when required create your own functions for controlling the leds.
11. Study the reference animations below carefully. They show advanced \
techniques: heat diffusion (fire), layered sine waves with BPM timing \
(pacifica/ocean), physics simulation with gravity and restitution (bouncing \
balls), particle systems with spawn/decay (death show), recursive fractal \
patterns (split cyclones), and color palette interpolation. Use these \
techniques and patterns to create rich, complex animations.

## Simple examples (showing the required ai_state + ai_step format)

### Example 1: Breathing red glow

ai_state = {}

def ai_step(strip):
    ai_state.setdefault("phase", 0.0)
    brightness = (math.sin(ai_state["phase"]) + 1) * 127.5
    r = int(brightness)
    fill_all(strip, r, 0, 0)
    ai_state["phase"] += 0.05

### Example 2: Blue meteor with trail

ai_state = {}

def ai_step(strip):
    ai_state.setdefault("pos", 0)
    num = strip.numPixels()
    for i in range(num):
        fade_to_black(strip, i, 40)
    head = ai_state["pos"] % num
    set_pixel(strip, head, 200, 220, 255)
    if head > 0:
        set_pixel(strip, head - 1, 80, 120, 255)
    if head > 1:
        set_pixel(strip, head - 2, 30, 50, 180)
    ai_state["pos"] += 2

### Example 3: Rainbow sparkle

ai_state = {}

def ai_step(strip):
    ai_state.setdefault("hue_offset", 0)
    num = strip.numPixels()
    for i in range(num):
        hue = ((i * 256 // num) + ai_state["hue_offset"]) % 256
        if hue < 85:
            r, g, b = hue * 3, 255 - hue * 3, 0
        elif hue < 170:
            h = hue - 85
            r, g, b = 255 - h * 3, 0, h * 3
        else:
            h = hue - 170
            r, g, b = 0, h * 3, 255 - h * 3
        if random.random() < 0.03:
            r, g, b = 255, 255, 255
        set_pixel(strip, i, r, g, b)
    ai_state["hue_offset"] += 1

## Reference animations from the existing codebase
These are REAL working animations. Study them to understand how to build \
complex effects. Note: they use a different function signature and state \
pattern than what you should output — adapt the TECHNIQUES, not the format. \
Your output must always use ai_state = {} and def ai_step(strip):.

"""

# Append reference animations to system prompt
SYSTEM_PROMPT += _REFERENCE_ANIMATIONS

# ---------------------------------------------------------------------------
# Ollama HTTP client
# ---------------------------------------------------------------------------


def call_ollama(user_prompt):
    """Call Ollama and return the raw response text. Raises on failure."""
    host = get_ollama_host()

    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "system": SYSTEM_PROMPT,
        "prompt": f"Create an LED animation: {user_prompt}",
        "stream": False,
        "options": {"temperature": 0.7, "num_predict": 2048},
    }).encode()

    req = urllib.request.Request(
        f"{host}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
            body = json.loads(resp.read().decode())
            return body.get("response", "")
    except urllib.error.URLError as exc:
        # Clear cache so next attempt re-discovers
        global _ollama_host_cache
        _ollama_host_cache = None
        raise ConnectionError(
            f"AI server unreachable at {host}. "
            "Is Ollama running on your laptop?"
        ) from exc
    except TimeoutError as exc:
        raise TimeoutError(
            "Generation timed out. Try a simpler prompt."
        ) from exc


# ---------------------------------------------------------------------------
# Code extraction
# ---------------------------------------------------------------------------


def extract_code(response_text):
    """Extract Python code from the LLM response."""
    # Try markdown fences first
    match = re.search(r"```(?:python)?\s*\n(.*?)```", response_text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # If no fences, look for ai_state and def ai_step markers
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

    # Last resort: return the whole thing if it looks like Python
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
        # Reject imports
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return False, "Import statements are not allowed"

        # Reject forbidden function calls
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in FORBIDDEN_NAMES:
                return False, f"Forbidden call: {func.id}()"
            if isinstance(func, ast.Attribute) and func.attr in FORBIDDEN_NAMES:
                return False, f"Forbidden call: .{func.attr}()"

        # Reject dunder attribute access (except __init__)
        if isinstance(node, ast.Attribute):
            if (node.attr.startswith("__") and node.attr.endswith("__")
                    and node.attr != "__init__"):
                return False, f"Forbidden attribute: {node.attr}"

        # Reject forbidden module references
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_MODULES:
            return False, f"Forbidden reference: {node.id}"

        # Check for ai_step function
        if isinstance(node, ast.FunctionDef) and node.name == "ai_step":
            has_ai_step = True

        # Check for ai_state assignment
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
# Sandboxed execution
# ---------------------------------------------------------------------------


class _RestrictedTime:
    """Only expose time.monotonic."""

    @staticmethod
    def monotonic():
        return time.monotonic()


def create_sandbox_globals():
    """Create the restricted globals dict for exec()."""
    allowed_builtins = {
        "range": range,
        "len": len,
        "int": int,
        "float": float,
        "abs": abs,
        "min": min,
        "max": max,
        "round": round,
        "True": True,
        "False": False,
        "None": None,
        "list": list,
        "dict": dict,
        "tuple": tuple,
        "enumerate": enumerate,
        "zip": zip,
        "isinstance": isinstance,
        "bool": bool,
        "str": str,
        "sorted": sorted,
        "reversed": reversed,
        "sum": sum,
        "map": map,
        "filter": filter,
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
    """Compile code in a sandbox and return (ai_step_fn, ai_state_dict).

    Raises ValueError on failure.
    """
    sandbox = create_sandbox_globals()
    try:
        exec(compile(code, "<ai_animation>", "exec"), sandbox)
    except Exception as exc:
        raise ValueError(f"Compilation error: {exc}") from exc

    step_fn = sandbox.get("ai_step")
    if not callable(step_fn):
        raise ValueError("ai_step function not found after execution")

    state = sandbox.get("ai_state", {})
    return step_fn, state


def make_safe_step(step_fn, error_callback):
    """Wrap an AI step function with runtime error handling.

    After 3 consecutive errors the animation is stopped via error_callback.
    """
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
    """Save a generated animation to disk. Returns the metadata dict."""
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
    filepath = os.path.join(AI_ANIMATIONS_DIR, filename)
    with open(filepath, "w") as f:
        json.dump(metadata, f, indent=2)
    return metadata


def load_all_ai_animations():
    """Load all saved AI animations from disk, sorted by creation time."""
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
    """Delete a saved animation by ID. Returns True if found and deleted."""
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


# ---------------------------------------------------------------------------
# Name heuristic
# ---------------------------------------------------------------------------


def prompt_to_name(prompt):
    """Derive a display name from the user's prompt."""
    words = prompt.strip().split()[:5]
    name = " ".join(words).title()
    if len(name) > 30:
        name = name[:27] + "..."
    return name
