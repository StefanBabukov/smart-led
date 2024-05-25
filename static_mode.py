import colorsys
from rpi_ws281x import PixelStrip, Color

class StaticMode:
    def __init__(self, strip):
        self.strip = strip
        self.hue = 0.0
        self.brightness = 1.0

    def update_color(self):
        rgb = colorsys.hsv_to_rgb(self.hue, 1.0, self.brightness)
        color = Color(int(rgb[0] * 255), int(rgb[1] * 255), int(rgb[2] * 255))
        for i in range(self.strip.numPixels()):
            self.strip.setPixelColor(i, color)
        self.strip.show()

    def increase_hue(self):
        self.hue += 0.01
        if self.hue > 1.0:
            self.hue = 0.0
        self.update_color()

    def decrease_hue(self):
        self.hue -= 0.01
        if self.hue < 0.0:
            self.hue = 1.0
        self.update_color()

    def increase_brightness(self):
        self.brightness += 0.05
        if self.brightness > 1.0:
            self.brightness = 1.0
        self.update_color()

    def decrease_brightness(self):
        self.brightness -= 0.05
        if self.brightness < 0.0:
            self.brightness = 0.0
        self.update_color()
