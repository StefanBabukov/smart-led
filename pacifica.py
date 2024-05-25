import time
import math
from rpi_ws281x import PixelStrip, Color

# Utility functions for calculating beat-based oscillations and scaling
def beatsin16(beats_per_minute, lowest=0, highest=65535, timebase=0, phase_offset=0):
    beat = (time.time() * beats_per_minute / 60.0) + phase_offset
    beat = beat - int(beat)
    beat = math.sin(beat * 2 * math.pi) * 0.5 + 0.5
    return int(lowest + (highest - lowest) * beat)

def beatsin8(beats_per_minute, lowest=0, highest=255, timebase=0, phase_offset=0):
    return beatsin16(beats_per_minute, lowest, highest, timebase, phase_offset) >> 8

def scale16(value, scale):
    return (value * scale) // 65536

def scale8(value, scale):
    return (value * scale) // 256

def qadd8(value1, value2):
    return min(value1 + value2, 255)

def beat16(beats_per_minute, timebase=0):
    return int((time.time() * beats_per_minute * 65536 / 60.0) + timebase) & 0xFFFF

def beat8(beats_per_minute, timebase=0):
    return beat16(beats_per_minute, timebase) >> 8

# Function to set a pixel color on the strip
def set_pixel(strip, pixel, red, green, blue):
    print('strip is ', strip,' setting pixel ', pixel)
    strip.setPixelColor(pixel, Color(red, green, blue))

# Function to retrieve color from palette with optional blending
def color_from_palette(palette, index, brightness, blend):
    index = index >> 8  # Index should be 8-bit for palette lookup
    color = palette[index % len(palette)]
    if blend:
        next_color = palette[(index + 1) % len(palette)]
        frac = (index & 0xFF) / 256.0  # Get fractional part for blending
        color = (
            int((1 - frac) * color[0] + frac * next_color[0]),
            int((1 - frac) * color[1] + frac * next_color[1]),
            int((1 - frac) * color[2] + frac * next_color[2])
        )
    return (
        (color[0] * brightness) >> 8,
        (color[1] * brightness) >> 8,
        (color[2] * brightness) >> 8
    )

# Function to fill the entire strip with a solid color
def fill_solid(strip, count, color):
    for i in range(count):
        strip.setPixelColor(i, color)

# Main function to run the Pacifica effect
def pacifica(strip, effect_stop_event):
    print("Pacifica effect started")

    # Define color palettes for the Pacifica effect
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

    # Function to handle the Pacifica loop
    def pacifica_loop():
        static_sCIStart1 = 0
        static_sCIStart2 = 0
        static_sCIStart3 = 0
        static_sCIStart4 = 0
        static_sLastms = 0

        while not effect_stop_event.is_set():
            ms = int(time.time() * 1000)
            deltams = ms - static_sLastms
            static_sLastms = ms

            # Calculate speed factors for the wave patterns
            speedfactor1 = beatsin16(3, 179, 269)
            speedfactor2 = beatsin16(4, 179, 269)
            deltams1 = (deltams * speedfactor1) // 256
            deltams2 = (deltams * speedfactor2) // 256
            deltams21 = (deltams1 + deltams2) // 2
            static_sCIStart1 += (deltams1 * beatsin8(1011, 10, 13))
            static_sCIStart2 -= (deltams21 * beatsin8(777, 8, 11))
            static_sCIStart3 -= (deltams1 * beatsin8(501, 5, 7))
            static_sCIStart4 -= (deltams2 * beatsin8(257, 4, 6))

            # Fill the strip with a background color
            fill_solid(strip, strip.numPixels(), Color(2, 6, 10))

            # Add layers of wave patterns
            pacifica_one_layer(pacifica_palette_1, static_sCIStart1, beatsin16(3, 11 * 256, 14 * 256), beatsin8(10, 70, 130), 0 - beat16(301))
            pacifica_one_layer(pacifica_palette_2, static_sCIStart2, beatsin16(4, 6 * 256, 9 * 256), beatsin8(17, 40, 80), beat16(401))
            pacifica_one_layer(pacifica_palette_3, static_sCIStart3, 6 * 256, beatsin8(9, 10, 38), 0 - beat16(503))
            pacifica_one_layer(pacifica_palette_3, static_sCIStart4, 5 * 256, beatsin8(8, 10, 28), beat16(601))

            # Add whitecaps to the waves
            pacifica_add_whitecaps()
            # Deepen the colors of the waves
            pacifica_deepen_colors()

            # Show the updated strip
            strip.show()
            time.sleep(0.02)

    # Function to add one layer of waves into the LED array
    def pacifica_one_layer(palette, cistart, wavescale, bri, ioff):
        ci = cistart
        waveangle = ioff
        wavescale_half = (wavescale // 2) + 20
        for i in range(strip.numPixels()):
            waveangle += 250
            s16 = int(math.sin(waveangle / 65536.0 * 2 * math.pi) * 32768)
            cs = scale16(s16, wavescale_half) + wavescale_half
            ci += cs
            sindex16 = int(math.sin(ci / 65536.0 * 2 * math.pi) * 32768)
            sindex8 = scale16(sindex16, 240)
            color = color_from_palette(palette, sindex8, bri, True)
            set_pixel(strip, i, color[0], color[1], color[2])

    # Function to add brighter 'whitecaps' to the waves
    def pacifica_add_whitecaps():
        basethreshold = beatsin8(9, 55, 65)
        wave = beat8(7)
        for i in range(strip.numPixels()):
            threshold = scale8(int(math.sin(wave / 256.0 * 2 * math.pi) * 128 + 128), 20) + basethreshold
            wave += 7
            l = strip.getPixelColor(i)
            r = (l >> 16) & 0xFF
            g = (l >> 8) & 0xFF
            b = l & 0xFF
            if max(r, g, b) > threshold:
                overage = max(r, g, b) - threshold
                overage2 = qadd8(overage, overage)
                set_pixel(strip, i, qadd8(overage, r), qadd8(overage2, g), qadd8(overage2, b))

    # Function to deepen the colors of the waves
    def pacifica_deepen_colors():
        for i in range(strip.numPixels()):
            color = strip.getPixelColor(i)
            r = (color >> 16) & 0xFF
            g = (color >> 8) & 0xFF
            b = color & 0xFF
            set_pixel(strip, i, scale8(r, 145), scale8(g, 200), scale8(b, 255))

    pacifica_loop()
