# smart-led

SETUP:

run the setup.sh script on the raspberry PI.

Follow this tutorial to setup the IR sensor on the raspberry https://ignorantofthings.com/receiving-infrared-on-the-raspberry-pi-with-python/



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
