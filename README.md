# smart-led

SETUP:

1. run the setup.sh script on the raspberry PI.

<!-- Follow this tutorial to setup the IR sensor on the raspberry https://ignorantofthings.com/receiving-infrared-on-the-raspberry-pi-with-python/ -->
2.  sudo nano /boot/firmware/config.txt 
    add the 'dtoverlay=gpio-ir,gpio_pin=27' line under [all]
    sudo reboot
    sudo apt-get install ir-keytable
    sudo apt install python3-evdev
    sudo pip3 install rpi_ws281x --break-system-packages
    sudo apt-get install evtest

3. Test IR receiver:
    sudo ir-keytable -p all
    sudo evtest

4. Setup to execute the python script on boot:
    sudo nano /etc/systemd/system/smart-led.service
    add this to the file:
[Unit]
Description=Smart LED Python Script
After=network.target

[Service]
ExecStart=/bin/sh -c "ir-keytable -p all && /usr/bin/python3 /home/pi/smart-led/main.py"
WorkingDirectory=/home/pi/smart-led
StandardOutput=inherit
StandardError=inherit
Restart=always
User=root
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target

5. Start the service
    systemctl enable smart-led.service
