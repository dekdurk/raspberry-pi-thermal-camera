# raspberry-pi-thermal-camera
Workflow and scripts for setting up raspberry pis to use thermal cameras in the field

## packages to download
currently I use sudo apt install python3- to do this, since i typically run into issues using pip where the packages can't be found. But i want to test try again to see if i can set up a requirements.txt to make this easier. However, there are only 2 packages needed, so it's not too bad.

sudo apt install python3-opencv
sudo apt install python3-rasterio

# crontab
in terminal type crontab -e
- You might have to create a new crontab document. I select 1.

Add to very bottom:
*/15 * * * * /usr/bin/python3 /home/tc3b/Desktop/thermal_image_cap_float32.py >> /home/tc3b/Desktop/thermal_capture.log 2>&1

ctrl+O to save
ctrl+X to exit

sudo reboot
