---
editor_options: 
  markdown: 
    wrap: 72
---

# raspberry-pi-thermal-camera

Workflow and scripts for setting up Raspberry Pis to run thermal cameras
for field deployments (MPJ site).

This setup:

-   captures thermal images every 15 minutes

-   saves them locally with timestamps

-   logs output for debugging

cd \~/Desktop

git clone <https://github.com/dekdurk/raspberry-pi-thermal-camera.git>

# packages to download

Currently I use `sudo apt install python3-` to do this, since i
typically run into issues using `pip` where the packages can't be found.

Only two required packages:

-   `sudo apt install python3-opencv`

-   `sudo apt install python3-rasterio`

**Note:** In the future, we may switch to a requirements.txt, but for
now `apt` is more reliable on fresh Pi installs.

# Scripts

Place the capture script somewhere accessible, for example:

`/home/tc3b/Desktop/thermal_image_cap_float32.py`

Make sure the script:

-   connects to the camera

-   captures an image when called

-   saves images to a known directory

-   prints a timestamp (for logging/debugging)

# Set Up Automatic Capture (crontab)

1.  Open crontab: `crontab -e`

2.  If prompted, select **option 1** (nano editor).

3.  Add this line to the bottom of the file:

    `*/15* \* \* \* /usr/bin/python3 /home/tc3b/Desktop/thermal_image_cap_float32.py \>\> /home/tc3b/Desktop/thermal_capture.log 2\>&1`

    -   **What this does:**

        -   runs the script every 15 minutes

        -   logs all output to `thermal_capture.log`

4.  Save and exit:

    -   `Ctrl + O` to save

    -   `Enter`

    -   `Ctrl + X` to exit

    -   `sudo reboot`

5.  Test That It Works

    1.  After reboot wait till you pass the next 15-min mark of the hour
        ( :00, :15, :30, :45)

    2.  Check log file `cat /home/tc3b/Desktop/thermal_capture.log`

        -   You should see timestamps or output from your script.

    3.  Check images directory.

        -   Make sure new images are being created every 15 minutes.

## Notes & Tips

If the script doesn’t run:

-   check log file

-   confirm file path is correct

-   confirm Python path is `/usr/bin/python3`

If camera isn’t detected:

-   make sure OpenCV installed correctly

-   test script manually:
    `python3 /home/tc3b/Desktop/thermal_image_cap_float32.py`

# Set Up Real Time Clock (RTC)

Previously, we used Raspberry Pi 5s, which have RTCs pre-installed, but
needed an watch battery attachment to provide constant power.

The Raspberry Pi 3bs do not have pre-installed RTCs, so we have to
install them on the pins and set it up.

## 1. Install DS3231 RTC

Here we use DS3231 RTCs.

![*Example of DS3231 RTC for Raspberry Pi
3b*](images/rtc_DS3231.jpg){width="128"}

Each Pi uses a DS3231 RTC module so it keeps correct time in the field
without WiFi.

[![*Raspberry Pi 3b Pinout
Diagram*](images/GPIO-Pinout-Diagram-2.png "Raspberry Pi 3b Pinout Diagram"){width="490"}](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html)

Connect the DS3231 to pins 1,3,5, 7, & 9

Here is what is should look like when installed:

![Top-down view of properly installed
DS3231](images/rtc_installed_top.jpg){width="245"} ![Angled view of
properly installed DS3231](images/rtc_installed_side.jpeg){width="308"}

## 2. Enable I2C

Open config tool: `sudo raspi-config`

Navigate to: `Interface Options → I2C → Enable`

Reboot if prompted.

## 3. Confirm RTC is detected

Run: `sudo i2cdetect -y 1`

You should see address: `68`

If you do not see `68`, check wiring.

## 4. Enable RTC overlay

Edit config file: `sudo nano /boot/firmware/config.txt`

-   **Note:** Was previously
    `/boot/firmware/config.txt` and might be recomended by forums online, but you'll be prompted to go to `/boot/firmware/config.txt`

Add this line at the bottom:`dtoverlay=i2c-rtc,ds3231`

Save and exit:

    -   `Ctrl + O` to save

    -   `Enter`

    -   `Ctrl + X` to exit

    -   `sudo reboot`
    

## 5. Disable the fake hardware clock

The internet claims that the Pi uses a fake clock by default, but every
time I try this on the Pi 3bs it shows that the module doesn't exist. So
you can try the following code, but I think it's useless.

1.  `sudo apt remove fake-hwclock`

2.  `sudo update-rc.d -f fake-hwclock remove`

3.  `sudo systemctl disable fake-hwclock`

## 6. Sync RTC

**NOPE**
    While the Pi has correct time (via WiFi or manual set), run:
    `sudo hwclock -w`

    This writes system time to the RTC.

## 7. Verify time

`timedatectl`

Make sure:

-   correct local time
-   timezone set correctly
    -   I use America/Phoenix (aka MST) to avoid daylight savings issues
        and since the tower data is on MST

**NOPE** To set timezone: `sudo timedatectl set-timezone America/Phoenix`

## 8. Test RTC (IMPORTANT before field deployment)

1.  Turn off WiFi

    -   Insert Image here

2.  Unplug Pi from power

3.  Wait \~5–10 minutes

4.  Power Pi back on (no internet)

5.  Check Time

The time should still be correct. If not, the RTC is not configured
correctly.

# Set up Ethernet

## Set static IP (desktop method)

Click network icon (top right)

```         
- Insert Image here
```

Go to Wired Connection Settings: IPv4 method → Manual

Enter: Address: 10.42.0.158 (change per Pi)

Netmask: 255.255.255.0

Gateway: 10.42.0.1

DNS: 10.42.0.1

Save and reconnect.

# Future Improvements

-   [ ] convert to `requirements.txt`
-   [ ] add info on PiConnect
-   [ ] Add rasppi imager info

Required edits: thermal_image_cap_float32.py line 87 save_dir = "/home/tc2/Desktop/raw_data/"
