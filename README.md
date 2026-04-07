# smart-led

Control WS2812B LED strip (300 LEDs) on a Raspberry Pi via a smartphone app over WiFi.

## Quick Setup (Raspberry Pi)

1. Clone/copy this repo to the Pi
2. Run the setup script:
   ```
   sudo bash setup.sh
   ```
3. Reboot to activate SD card protections:
   ```
   sudo reboot
   ```
4. Note the Pi's IP address (printed at end of setup, or run `hostname -I`)

That's it. The LED server starts automatically on every boot.

## Phone App (APK)

The `SmartLED/` folder contains a React Native Expo app.

### Build the APK

On any computer with Node.js installed:

```bash
cd SmartLED
npm install
npm install -g eas-cli
eas login          # create a free Expo account at expo.dev
eas build --platform android --profile preview
```

This builds the APK in the cloud (no Android SDK needed). When done, download the APK from the link provided.

### Install on Phone

1. Transfer the APK to your Android phone
2. Enable "Install from unknown sources" in Android settings
3. Open and install the APK

### Use

1. Make sure your phone is on the same WiFi as the Pi
2. Open the app, enter the Pi's IP address, tap Connect
3. Controls:
   - **UP / DOWN** = brightness
   - **LEFT / RIGHT** = previous / next animation (or hue in static mode)
   - **ANIMATION** = switch to animation mode
   - **STATIC** = switch to static color mode
   - **ON/OFF** = toggle LEDs

The IP is saved automatically - you only enter it once.

## What setup.sh Does

- Installs Python dependencies (`rpi_ws281x`, `websockets`)
- Applies SD card protections to extend card lifespan:
  - Mounts `/tmp` and `/var/log` as RAM disks (tmpfs)
  - Sets systemd journal to volatile (RAM only)
  - Disables swap
  - Adds `noatime` to prevent access-time writes
- Creates a systemd service that auto-starts on boot
- Opens firewall port 8765 if ufw is active

## Manual Commands

```bash
# Check service status
sudo systemctl status smart-led

# View live logs (from RAM, not disk)
sudo journalctl -u smart-led -f

# Restart service
sudo systemctl restart smart-led

# Stop service
sudo systemctl stop smart-led
```

## Files

| File | Purpose |
|------|---------|
| `server.py` | WebSocket server - controls LEDs, serves phone app |
| `setup.sh` | One-time Pi setup (deps, SD protection, systemd) |
| `main.py` | Original IR remote version (kept as fallback) |
| `animations.py` | Animation effects library |
| `pacifica.py` | Ocean wave effect |
| `fire.py` | Fire effect |
| `color_bounce.py` | Bouncing dots effect |
| `halloween_scene.py` | Halloween animation |
| `xmas_scene.py` | Christmas animation |
| `static_mode.py` | Static color mode |
| `led_operations.py` | Low-level LED helpers |
| `SmartLED/` | Phone app (React Native Expo) |

## Hardware

- Raspberry Pi (any model with WiFi)
- WS2812B LED strip, 300 LEDs
- Data pin: GPIO 18
