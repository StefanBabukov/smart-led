sudo apt-get update && sudo apt-get upgrade -y
sudo apt install git -y
git clone https://github.com/StefanBabukov/smart-led.git
sudo apt-get install python3-pip -y
sudo pip3 uninstall rpi_ws281x --break-system-packages