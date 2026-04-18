# smart-led

Control WS2812B LED strip (300 LEDs) on a Raspberry Pi via a smartphone app over WiFi.

## Quick Setup (Raspberry Pi)

1. Clone/copy this repo to the Pi
2. Run the setup script:
   ```
   sudo bash setup.sh
   ```
3. Reboot to activate SD card protections and the PWM/audio flicker fix:
   ```
   sudo reboot
   ```
4. Note the Pi's IP address (printed at end of setup, or run `hostname -I`)

That's it. The LED server starts automatically on every boot.

## Phone App (APK)

The `SmartLED/` folder contains a React Native Expo app. The `android/` source is committed with all required fixes already applied.

### Prerequisites

Install these on any Linux/Mac machine (not the Pi):

1. **Node.js 18+**
   ```bash
   node --version   # check if already installed
   ```

2. **JDK 17**
   ```bash
   sudo apt install openjdk-17-jdk
   ```

3. **Android SDK**
   ```bash
   mkdir -p ~/android-sdk/cmdline-tools
   cd ~/android-sdk/cmdline-tools
   wget https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip
   unzip commandlinetools-linux-11076708_latest.zip
   mv cmdline-tools latest

   echo 'export ANDROID_HOME=~/android-sdk' >> ~/.bashrc
   echo 'export PATH=$PATH:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools' >> ~/.bashrc
   source ~/.bashrc

   yes | sdkmanager --licenses
   sdkmanager "platforms;android-35" "build-tools;35.0.0" "platform-tools"
   ```

### Run on emulator (for development/testing)

1. Start an Android emulator (or connect a device via USB with `adb devices`)
2. Build and install the app:
   ```bash
   cd SmartLED
   npm install
   npx expo run:android
   ```
   This compiles the native app and installs it directly on the emulator/device. No Expo Go needed.

3. If you only changed JS code and want to rebuild faster:
   ```bash
   npx expo run:android
   ```
   It will reuse the native build and just rebundle the JS.

4. Set `ANDROID_HOME` if the build can't find the SDK:
   ```bash
   export ANDROID_HOME=~/android-sdk
   ```

### Build the APK

```bash
cd SmartLED
npm install
cd android
./gradlew assembleRelease
```

The APK is at: `SmartLED/android/app/build/outputs/apk/release/app-release.apk`

### Transfer APK to phone

From the build machine:
```bash
cd SmartLED/android/app/build/outputs/apk/release
python3 -m http.server 8080
```

On your phone browser, go to `http://<build-machine-ip>:8080/app-release.apk`.
Enable "Install from unknown sources" in Android settings if prompted.

Find your build machine IP with: `hostname -I`

### Use the app

1. Make sure your phone is on the same WiFi as the Pi
2. Open the app, enter the Pi's IP address, tap Connect
3. Controls:
   - **ANIMATION / STATIC** = switch mode
   - **ON/OFF** = toggle LEDs
   - **Brightness slider** = drag to adjust brightness
   - **Color wheel** = tap/drag to pick a color (static mode). Tap Expand for a larger wheel.
   - **Solid Color / Free Paint** = in static mode, toggle between setting all LEDs to one color or painting individual LEDs
   - **Free Paint** = select a color from the wheel, then drag along the LED strip to paint. Tap Reset Strip to clear.
   - **LEFT / RIGHT arrows** = previous / next animation
4. Tap **SHOW LOGS** at the bottom for debug info if something isn't working

The IP is saved automatically - you only enter it once.

## What setup.sh Does

- Installs Python dependencies (`rpi_ws281x`, `websockets`)
- Applies SD card protections to extend card lifespan:
  - Mounts `/tmp` and `/var/log` as RAM disks (tmpfs)
  - Sets systemd journal to volatile (RAM only)
  - Disables swap
  - Adds `noatime` to prevent access-time writes
  - No disk logging from the LED service
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

## Troubleshooting

- **App can't connect:** Check the Pi IP is correct, phone and Pi are on the same WiFi, and port 8765 isn't blocked. Use SHOW LOGS in the app for details.
- **LEDs not responding:** SSH into the Pi and run `sudo systemctl status smart-led` to check if the service is running.
- **LEDs flicker bright colors only during animations:** This project drives the strip from GPIO 18, which uses PWM. On Raspberry Pi, onboard audio can conflict with PWM and cause random render glitches. Run `sudo bash setup.sh`, then reboot so `dtparam=audio=off` takes effect.
- **Rebuilding android/ from scratch:** If you delete the `android/` folder, regenerate it with `npx expo prebuild --platform android`, then re-apply the cleartext traffic fix in `AndroidManifest.xml` (add `android:networkSecurityConfig="@xml/network_security_config" android:usesCleartextTraffic="true"` to the `<application>` tag) and create `android/app/src/main/res/xml/network_security_config.xml` with `<base-config cleartextTrafficPermitted="true" />`.

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
- Data pin: GPIO 18 (PWM, so onboard audio must stay disabled)
