from rpi_ws281x import Color

class StaticMode:
    def __init__(self, strip):
        self.strip = strip
        self.hue = 0
        self.current_rgb = (255, 0, 0)
        self.use_rgb = False
        self.show_color()

    def show_color(self):
        if self.use_rgb:
            r, g, b = self.current_rgb
        else:
            r, g, b = self.hue_to_rgb(self.hue)
            self.current_rgb = (r, g, b)
        for i in range(self.strip.numPixels()):
            self.strip.setPixelColor(i, Color(r, g, b))
        self.strip.show()

    def hue_to_rgb(self, hue):
        c = 255
        x = int((1 - abs((hue/60)%2 -1))*c)
        if 0 <= hue < 60:
            r, g, b = c, x, 0
        elif 60 <= hue <120:
            r, g, b = x, c, 0
        elif 120 <= hue <180:
            r, g, b = 0, c, x
        elif 180 <= hue <240:
            r, g, b = 0, x, c
        elif 240 <= hue <300:
            r, g, b = x, 0, c
        else:
            r, g, b = c, 0, x
        return (r, g, b)

    def set_rgb(self, r, g, b):
        self.current_rgb = (r, g, b)
        self.use_rgb = True
        self.show_color()

    def get_rgb(self):
        return self.current_rgb

    def increase_hue(self):
        self.use_rgb = False
        self.hue = (self.hue + 10) % 360
        self.show_color()

    def decrease_hue(self):
        self.use_rgb = False
        self.hue = (self.hue - 10) % 360
        self.show_color()

    def increase_brightness(self):
        self.brightness = min(self.brightness+10, 255)
        self.show_color()

    def decrease_brightness(self):
        self.brightness = max(self.brightness-10, 0)
        self.show_color()
