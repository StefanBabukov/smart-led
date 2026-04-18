#!/bin/bash
# Smart LED Setup Script
# Run once on a fresh Raspberry Pi: sudo bash setup.sh
# Safe to re-run (idempotent).

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_FILE="/etc/systemd/system/smart-led.service"

echo "=== Smart LED Setup ==="

# -------------------------------------------------------
# 1. Install system & Python dependencies
# -------------------------------------------------------
echo "[1/5] Installing dependencies..."
apt-get update -qq
apt-get install -y -qq python3-pip > /dev/null

pip3 install rpi_ws281x --break-system-packages --quiet 2>/dev/null || \
    pip3 install rpi_ws281x --quiet
pip3 install websockets --break-system-packages --quiet 2>/dev/null || \
    pip3 install websockets --quiet

# GPIO 18 uses the Pi's PWM hardware, which conflicts with onboard audio and
# can cause random LED flicker during continuous animation updates.
BOOT_CONFIG=""
if [ -f /boot/firmware/config.txt ]; then
    BOOT_CONFIG="/boot/firmware/config.txt"
elif [ -f /boot/config.txt ]; then
    BOOT_CONFIG="/boot/config.txt"
fi

if [ -n "$BOOT_CONFIG" ]; then
    if grep -q '^dtparam=audio=' "$BOOT_CONFIG"; then
        sed -i 's/^dtparam=audio=.*/dtparam=audio=off/' "$BOOT_CONFIG"
    elif ! grep -q '^dtparam=audio=off' "$BOOT_CONFIG"; then
        echo "dtparam=audio=off" >> "$BOOT_CONFIG"
    fi
fi

if lsmod | grep -q '^snd_bcm2835'; then
    modprobe -r snd_bcm2835 2>/dev/null || true
fi

# -------------------------------------------------------
# 2. SD card protection — reduce writes to near zero
# -------------------------------------------------------
echo "[2/5] Applying SD card protection..."

# 2a. Mount /tmp and /var/log as tmpfs (RAM disks)
if ! grep -q 'tmpfs.*/tmp' /etc/fstab; then
    echo "tmpfs /tmp tmpfs defaults,noatime,nosuid,nodev,size=64M 0 0" >> /etc/fstab
fi
if ! grep -q 'tmpfs.*/var/log' /etc/fstab; then
    echo "tmpfs /var/log tmpfs defaults,noatime,nosuid,nodev,size=32M 0 0" >> /etc/fstab
fi

# 2b. Add noatime to root filesystem to stop access-time writes
if grep -q 'defaults\b' /etc/fstab && ! grep -q 'noatime' /etc/fstab; then
    sed -i 's/defaults/defaults,noatime/' /etc/fstab
fi

# 2c. Set systemd journal to volatile (RAM only, no disk writes)
JOURNALD_CONF="/etc/systemd/journald.conf"
if grep -q '^#\?Storage=' "$JOURNALD_CONF"; then
    sed -i 's/^#\?Storage=.*/Storage=volatile/' "$JOURNALD_CONF"
elif ! grep -q '^Storage=volatile' "$JOURNALD_CONF"; then
    echo "Storage=volatile" >> "$JOURNALD_CONF"
fi
# Cap journal RAM usage
if grep -q '^#\?RuntimeMaxUse=' "$JOURNALD_CONF"; then
    sed -i 's/^#\?RuntimeMaxUse=.*/RuntimeMaxUse=16M/' "$JOURNALD_CONF"
elif ! grep -q '^RuntimeMaxUse=' "$JOURNALD_CONF"; then
    echo "RuntimeMaxUse=16M" >> "$JOURNALD_CONF"
fi

# 2d. Disable swap entirely
if command -v dphys-swapfile &> /dev/null; then
    dphys-swapfile swapoff 2>/dev/null || true
    dphys-swapfile uninstall 2>/dev/null || true
    systemctl disable dphys-swapfile 2>/dev/null || true
fi
swapoff -a 2>/dev/null || true

# -------------------------------------------------------
# 3. Create systemd service
# -------------------------------------------------------
echo "[3/5] Creating systemd service..."

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Smart LED WebSocket Server
After=network.target

[Service]
ExecStart=/usr/bin/python3 ${SCRIPT_DIR}/server.py
WorkingDirectory=${SCRIPT_DIR}
StandardOutput=null
StandardError=null
Restart=always
RestartSec=5
User=root
Environment=PYTHONDONTWRITEBYTECODE=1

[Install]
WantedBy=multi-user.target
EOF

# -------------------------------------------------------
# 4. Enable and start service
# -------------------------------------------------------
echo "[4/5] Enabling service..."
systemctl daemon-reload
systemctl enable smart-led.service
systemctl restart smart-led.service

# -------------------------------------------------------
# 5. Open firewall port if ufw is active
# -------------------------------------------------------
echo "[5/5] Checking firewall..."
if command -v ufw &> /dev/null && ufw status | grep -q "active"; then
    ufw allow 8765/tcp > /dev/null
    echo "  Opened port 8765 in ufw"
fi

# -------------------------------------------------------
# Done
# -------------------------------------------------------
echo ""
echo "=== Setup complete ==="
echo ""
echo "SD card protection applied (takes effect after reboot):"
echo "  - /tmp and /var/log mounted as RAM disks"
echo "  - systemd journal set to volatile (RAM only)"
echo "  - Swap disabled"
echo "  - noatime added to root filesystem"
echo "  - No logging from the LED service"
echo "  - Onboard audio disabled to prevent PWM LED flicker on GPIO 18"
echo ""
echo "The smart-led service is now running and will auto-start on boot."
echo ""
IP=$(hostname -I | awk '{print $1}')
echo "Connect your phone app to: ${IP}:8765"
echo ""
echo "A reboot is recommended to activate all SD card protections:"
echo "  sudo reboot"
