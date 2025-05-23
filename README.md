# smart-led

SETUP:

1. run the setup.sh script on the raspberry PI.

<!-- Follow this tutorial to setup the IR sensor on the raspberry https://ignorantofthings.com/receiving-infrared-on-the-raspberry-pi-with-python/ -->
2.  sudo nano /boot/firmware/config.txt 
    add the 'dtoverlay=gpio-ir,gpio_pin=27' line under [all]
    sudo reboot
    sudo apt-get install ir-keytable
    sudo apt install python3-evdev
    sudo apt-get install evtest

    sudo nano /etc/rc.local
    Add these lines:
        #!/bin/sh -e

        sudo ir-keytable -p all

        exit 0
3. Test IR receiver:
    sudo ir-keytable -p all
    sudo evtest



Setup to execute the python script on boot:
    [Unit]
    Description=Smart LED Python Script
    After=network.target

    [Service]
    ExecStart=/usr/bin/sudo /usr/bin/python3 /home/pi/smart-led/main.py
    WorkingDirectory=/home/pi/smart-led
    StandardOutput=inherit
    StandardError=inherit
    Restart=always
    User=root
    Environment=PYTHONUNBUFFERED=1

    [Install]
    WantedBy=multi-user.target
