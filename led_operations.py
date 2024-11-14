from rpi_ws281x import PixelStrip, Color


def blend_colors(color1, color2):
    r = (color1[0] + color2[0]) // 2
    g = (color1[1] + color2[1]) // 2
    b = (color1[2] + color2[2]) // 2
    return (r, g, b)

def set_pixel(strip, pixel, red, green, blue):
    strip.setPixelColor(pixel, Color(red, green, blue))

def set_all(strip, red, green, blue):
    for i in range(strip.numPixels()):
        set_pixel(strip, i, red, green, blue)
    strip.show()

def fade_to_black(strip, led_no, fade_value):
    color = strip.getPixelColor(led_no)
    r = max((color >> 16) - fade_value, 0)
    g = max((color >> 8 & 0xFF) - fade_value, 0)
    b = max((color & 0xFF) - fade_value, 0)
    set_pixel(strip, led_no, r, g, b)

def get_pixel(strip, led_no):
    """Retrieve the RGB color of a specified LED."""
    color = strip.getPixelColor(led_no)
    r = (color >> 16) & 0xFF
    g = (color >> 8) & 0xFF
    b = color & 0xFF
    return (r, g, b)

