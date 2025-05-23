from rpi_ws281x import Color

def set_pixel(strip, pixel, red, green, blue):
    strip.setPixelColor(pixel, Color(red, green, blue))

def set_all(strip, red, green, blue):
    for i in range(strip.numPixels()):
        strip.setPixelColor(i, Color(red, green, blue))
    strip.show()

def fade_to_black(strip, led_no, fade_value):
    color = strip.getPixelColor(led_no)
    r = (color >> 16) & 0xFF
    g = (color >> 8) & 0xFF
    b = color & 0xFF
    r = max(r - fade_value, 0)
    g = max(g - fade_value, 0)
    b = max(b - fade_value, 0)
    strip.setPixelColor(led_no, Color(r, g, b))

def get_pixel(strip, led_no):
    color = strip.getPixelColor(led_no)
    r = (color >> 16) & 0xFF
    g = (color >> 8) & 0xFF
    b = color & 0xFF
    return (r, g, b)
