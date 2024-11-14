import time
import math
from rpi_ws281x import PixelStrip, Color
from led_operations import set_pixel, get_pixel

# Define the palettes
pacifica_palette_1 = [
    (0x00, 0x05, 0x07), (0x00, 0x04, 0x09), (0x00, 0x03, 0x0B), (0x00, 0x03, 0x0D),
    (0x00, 0x02, 0x10), (0x00, 0x02, 0x12), (0x00, 0x01, 0x14), (0x00, 0x01, 0x17),
    (0x00, 0x00, 0x19), (0x00, 0x00, 0x1C), (0x00, 0x00, 0x26), (0x00, 0x00, 0x31),
    (0x00, 0x00, 0x3B), (0x00, 0x00, 0x46), (0x14, 0x55, 0x4B), (0x28, 0xAA, 0x50)
]

pacifica_palette_2 = [
    (0x00, 0x05, 0x07), (0x00, 0x04, 0x09), (0x00, 0x03, 0x0B), (0x00, 0x03, 0x0D),
    (0x00, 0x02, 0x10), (0x00, 0x02, 0x12), (0x00, 0x01, 0x14), (0x00, 0x01, 0x17),
    (0x00, 0x00, 0x19), (0x00, 0x00, 0x1C), (0x00, 0x00, 0x26), (0x00, 0x00, 0x31),
    (0x00, 0x00, 0x3B), (0x00, 0x00, 0x46), (0x0C, 0x5F, 0x52), (0x19, 0xBE, 0x5F)
]

pacifica_palette_3 = [
    (0x00, 0x02, 0x08), (0x00, 0x03, 0x0E), (0x00, 0x05, 0x14), (0x00, 0x06, 0x1A),
    (0x00, 0x08, 0x20), (0x00, 0x09, 0x27), (0x00, 0x0B, 0x2D), (0x00, 0x0C, 0x33),
    (0x00, 0x0E, 0x39), (0x00, 0x10, 0x40), (0x00, 0x14, 0x50), (0x00, 0x18, 0x60),
    (0x00, 0x1C, 0x70), (0x00, 0x20, 0x80), (0x10, 0x40, 0xBF), (0x20, 0x60, 0xFF)
]

# Helper functions
def millis():
    return int(round(time.time() * 1000))

def beat16(bpm, time_base=0):
    ms = millis() - time_base
    beat = (ms * bpm * 65536) // 60000
    return beat % 65536

def beatsin16(bpm, minimum=0, maximum=65535, time_base=0, phase_offset=0):
    beat = beat16(bpm, time_base)
    beat = (beat + phase_offset) % 65536
    sine = sin16(beat)
    amplitude = (maximum - minimum) // 2
    value = minimum + amplitude + ((sine * amplitude) >> 15)
    return value

def beat8(bpm, time_base=0):
    ms = millis() - time_base
    beat = (ms * bpm * 256) // 60000
    return beat % 256

def beatsin8(bpm, minimum=0, maximum=255, time_base=0, phase_offset=0):
    beat = beat8(bpm, time_base)
    beat = (beat + phase_offset) % 256
    sine = sin8(beat)
    amplitude = (maximum - minimum) // 2
    value = minimum + amplitude + ((sine - 128) * amplitude) // 127
    return value

def sin16(x):
    angle = x * (2 * math.pi) / 65536.0
    return int(math.sin(angle) * 32767)

def sin8(x):
    angle = x * (2 * math.pi) / 256.0
    return int(math.sin(angle) * 127) + 128

def scale16(value, scale):
    return (value * scale) >> 16

def scale8(value, scale):
    return (value * scale) >> 8

def qadd8(a, b):
    return min(a + b, 255)

def color_from_palette(palette, index, brightness, blending=True):
    palette_size = len(palette)
    # Map index from 0-255 to 0-palette_size
    index = index * (palette_size - 1) / 255.0
    index_low = int(math.floor(index))
    index_high = (index_low + 1) % palette_size
    blend = index - index_low
    color1 = palette[index_low]
    color2 = palette[index_high]
    if blending:
        r = int((1 - blend) * color1[0] + blend * color2[0])
        g = int((1 - blend) * color1[1] + blend * color2[1])
        b = int((1 - blend) * color1[2] + blend * color2[2])
    else:
        r, g, b = color1
    r = (r * brightness) // 255
    g = (g * brightness) // 255
    b = (b * brightness) // 255
    return (r, g, b)

# Main effect functions
def pacifica_one_layer(strip, palette, cistart, wavescale, bri, ioff):
    num_leds = strip.numPixels()
    ci = cistart
    waveangle = ioff
    wavescale_half = (wavescale // 2) + 20
    for i in range(num_leds):
        waveangle = (waveangle + 250) % 65536
        s16 = sin16(waveangle) + 32768
        cs = scale16(s16, wavescale_half) + wavescale_half
        ci = (ci + cs) % 65536
        sindex16 = sin16(ci) + 32768
        sindex8 = sindex16 >> 8  # Convert from 16-bit to 8-bit (0-255)
        c = color_from_palette(palette, sindex8, bri)
        r1, g1, b1 = get_pixel(strip, i)
        r2, g2, b2 = c
        r = min(r1 + r2, 255)
        g = min(g1 + g2, 255)
        b = min(b1 + b2, 255)
        set_pixel(strip, i, r, g, b)

def pacifica_add_whitecaps(strip):
    num_leds = strip.numPixels()
    basethreshold = beatsin8(9, 55, 65)
    wave = beat8(7)
    for i in range(num_leds):
        threshold = scale8(sin8(wave), 20) + basethreshold
        wave = (wave + 7) % 256
        r, g, b = get_pixel(strip, i)
        l = (r + g + b) // 3  # get average light
        if l > threshold:
            overage = l - threshold
            overage2 = qadd8(overage, overage)
            r = min(r + overage, 255)
            g = min(g + overage2, 255)
            b = min(b + qadd8(overage2, overage2), 255)
            set_pixel(strip, i, r, g, b)

def pacifica_deepen_colors(strip):
    num_leds = strip.numPixels()
    for i in range(num_leds):
        r, g, b = get_pixel(strip, i)
        b = scale8(b, 145)
        g = scale8(g, 200)
        r = min(r + 2, 255)
        g = min(g + 5, 255)
        b = min(b + 7, 255)
        set_pixel(strip, i, r, g, b)

def pacifica(strip):
    num_leds = strip.numPixels()
    sCIStart1 = 0
    sCIStart2 = 0
    sCIStart3 = 0
    sCIStart4 = 0
    sLastms = millis()

    while True:
        ms = millis()
        deltams = ms - sLastms
        sLastms = ms

        # Adjusted speed factors to slow down the wave movement
        speedfactor1 = beatsin16(1, 179, 269)
        speedfactor2 = beatsin16(1, 179, 269)
        deltams1 = (deltams * speedfactor1) // 256
        deltams2 = (deltams * speedfactor2) // 256
        deltams21 = (deltams1 + deltams2) // 2

        # Adjusted BPM values to slow down color index changes
        sCIStart1 = (sCIStart1 + ((deltams1 * beatsin16(20, 10, 13)) >> 16)) % 65536
        sCIStart2 = (sCIStart2 - ((deltams21 * beatsin16(15, 8, 11)) >> 16)) % 65536
        sCIStart3 = (sCIStart3 - ((deltams1 * beatsin16(10, 5, 7)) >> 16)) % 65536
        sCIStart4 = (sCIStart4 - ((deltams2 * beatsin16(5, 4, 6)) >> 16)) % 65536

        # Create a dynamic background color that changes over time
        background_r = beatsin8(2, 2, 5)
        background_g = beatsin8(2, 6, 10)
        background_b = beatsin8(2, 8, 12)

        # Apply the dynamic background color
        for i in range(num_leds):
            set_pixel(strip, i, background_r, background_g, background_b)

        # Render each of four layers with adjusted parameters for smoother transitions
        pacifica_one_layer(strip, pacifica_palette_1, sCIStart1,
                           beatsin16(1, 11*256, 14*256), beatsin8(1, 70, 130),
                           (0 - beat16(3)) % 65536)
        pacifica_one_layer(strip, pacifica_palette_2, sCIStart2,
                           beatsin16(1, 6*256, 9*256), beatsin8(1, 40, 80),
                           beat16(4))
        pacifica_one_layer(strip, pacifica_palette_3, sCIStart3,
                           6*256, beatsin8(1, 10, 38),
                           (0 - beat16(5)) % 65536)
        pacifica_one_layer(strip, pacifica_palette_3, sCIStart4,
                           5*256, beatsin8(1, 10, 28),
                           beat16(6))
            

        # Add brighter 'whitecaps'
        pacifica_add_whitecaps(strip)

        # Deepen the blues and greens
        pacifica_deepen_colors(strip)

        strip.show()
        time.sleep(0.005)  # Slightly increased sleep time for smoother transitions
