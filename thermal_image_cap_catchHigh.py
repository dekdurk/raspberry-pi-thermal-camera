import serial
import time
import cv2
import numpy as np
import os
import socket
import sys
from datetime import datetime, timedelta
import signal
import argparse
import rasterio

DEFAULT_SAVE_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "raw_data")

description = '''Script for recording data at regular intervals from an ICI Helios LWIR camera'''

epilog = '''
Example commands:

Record a radiometric TIFF image and temperature data to csv files continuously with minimal delay from a device at the default locations
%(prog)s

Record from non-default locations /dev/video1 and /dev/ttyACM1
%(prog)s --device /dev/video1 --serial_port /dev/ttyACM1

Record every 1 Hour 15 Minutes and 30 Seconds
%(prog)s --hours 1 --minutes 15 --seconds 30

Record images and csv files to child directories within a non-default save_dir
%(prog)s --save_dir ./nondefault_save_dir --img_dir images --csv_dir csv

Record a csv file containing the mean temperatures of each frame
%(prog)s --mean_temps_file mean_temps.csv

Record every 15 minutes for 24 hours
%(prog)s --minutes 15 --duration 24

Record with default settings and display a countdown until the next image capture
%(prog)s --display_countdown

Capture only a single image and save it to the default save directories
%(prog)s --capture_single_image

Save only raw_temp_data csv files and no images
%(prog)s --save_raw_only --no_image_save
'''

parser = argparse.ArgumentParser(description=description, 
                                 epilog=epilog, 
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--device", "-d", type=str, default="/dev/video0",
                    help="Path to the camera")
parser.add_argument("--serial_port", "-p", type=str, default="/dev/ttyACM0",
                    help="Serial port to open for sending commands to the camera")
parser.add_argument("--device_name", "-n", type=str,
                    help="Optional label for this camera/Pi. Defaults to the Raspberry Pi hostname and is used in saved image filenames.")
parser.add_argument("--hours", "-H", type=int, default=0,
                    help="Default: 0. How many hours to wait between capturse")
parser.add_argument("--minutes", "-M", type=int, default=0,
                    help="Default: 0. How many minutes to wait between captures")
parser.add_argument("--seconds", "-S", type=int, default=0,
                    help="Default: 0. How many seconds to wait between captures")
parser.add_argument("--save_dir", type=str, default=DEFAULT_SAVE_DIR,
                    help=f'Default: "{DEFAULT_SAVE_DIR}". Directory to save images and csv files to')
parser.add_argument("--img_dir", type=str,
                    help="Directory within save_dir to save radiometric TIFF images to. If not set, images will be saved into <save_dir>. NOTE: This will be a child directory of <save_dir>")
parser.add_argument("--csv_dir", type=str,
                    help="Directory within save_dir to save csv files to. If not set, files will be saved into <save_dir>. NOTE: This will be a child directory of <save_dir>")
parser.add_argument("--mean_temps_file", type=str,
                    help="File inside save_dir to save mean temperatures to. Mainly for debugging purposes. If not set no mean_temps file will be created")
parser.add_argument("--duration", type=float, default=-1,
                    help="Default: -1. How many hours to capture images for. If negative, the program will run indefinitely")
parser.add_argument("--capture_single_image", action="store_true",
                    help="Runs the program for a single loop before closing. If passed, --minutes, --seconds, --hours, and --duration will be ignored")
parser.add_argument("--display_countdown", action="store_true",
                    help="If passed, will display a countdown until the next image is captured")
parser.add_argument("--print_serial", action="store_true",
                    help="For debugging. If passed, serial commands and returns will be printed to the terminal")
parser.add_argument("--save_raw_only", action="store_true",
                    help="If passed, will not save Celsius or Kelvin data. These files can be converted from raw_temp_data afterwards. Use this to save space")
parser.add_argument("--no_image_save", action="store_true",
                    help="If passed, will not save a radiometric TIFF. Use this to save space.")
args = parser.parse_args()
args.capture_single_image = True

def sanitize_device_name(name):
    cleaned = ''.join(char if char.isalnum() or char in ('-', '_') else '_' for char in name.strip())
    return cleaned or "thermal_camera"

# CHANGE PER DEVICE
device_name = sanitize_device_name("TC3")


######## Parse command line arguments
# Directory to save images and data
save_dir = args.save_dir

# This is so that we can keep track of when issues did happen in the log file
# -DK
print(f"[START] capture at {datetime.now().isoformat()}", flush=True)
        
print(f"save_dir : {save_dir}")
print(f"device_name : {device_name}")

if not os.path.exists(save_dir):
    os.makedirs(save_dir)
    
if args.img_dir is not None:
    #child directory of save_dir to save images in
    img_dir = os.path.join(save_dir, args.img_dir)
    os.makedirs(img_dir, exist_ok=True)
    print(f"img_dir  : {img_dir}")
else:
    #save images directly to save_dir
    img_dir = save_dir
    
if args.csv_dir is not None:
    #child directory of save_dir to save csv files in
    csv_dir = os.path.join(save_dir, args.csv_dir)
    os.makedirs(csv_dir, exist_ok=True)
    print(f"csv_dir  : {csv_dir}")
else:
    #save csv files directly to save_dir
    csv_dir = save_dir
    
#create mean_temps_file if --mean_temps_file is set
if args.mean_temps_file is not None:
    import csv
    mean_temps_filename = os.path.join(save_dir, args.mean_temps_file)
    print(f"saving mean temps to {mean_temps_filename}")
    if not os.path.exists(mean_temps_filename):
        #create header for mean_temps file
        with open(mean_temps_filename, 'a+') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(["timestamp", "raw", "kelvin", "celsius"])
    
delay_timedelta = timedelta(hours = args.hours, 
                            minutes = args.minutes, 
                            seconds = args.seconds)
delay_timedelta = timedelta(hours = 0, 
                            minutes = 15, 
                            seconds = 0) #DK
msg = "Recording data "
if not args.capture_single_image:
    msg += "every"
    if args.hours: msg += f" {args.hours} hours"
    if args.minutes: msg += f" {args.minutes} minutes"
    if args.seconds: msg += f" {args.seconds} seconds"
    
else:
    msg += "once"
    
#define time to end program if --duration is positive
if args.duration > 0 and not args.capture_single_image:
    end_time = datetime.now() + timedelta(hours = args.duration)
    msg += f" until  {end_time.strftime('%H:%M:%S on %d %b %Y')}"
else:
    #If --duration is negative, end the program after 10 years, anyway. I hope that's enough time to gather all the data needed
    end_time = datetime.now() + timedelta(weeks=520)
    
print(msg)
    
#####################################
    
#define object to hold QUIT signal
def QUIT():
    QUIT.signal = False
#initialize object to hold QUIT signal
QUIT()
    
#serial defs

#Serial commands follow format: PROCESS_START, BYTE_COUNT, COMMAND, MOD256_CHECKSUM, PROCESS_END
#BYTE_COUNT and MOD256_CHECKSUM are calculated in send_command() function

PROCESS_START = bytearray([0xAA])
PROCESS_END = bytearray([0xEB, 0xAA])

MANUAL_NUC_CMD = bytearray([0x00, 0x16, 0x01, 0x00])
SET_HIGH_GAIN_CMD = bytearray([0x07, 0x01, 0x01, 0x00])
Y16_TEMP_CMD = bytearray([0x01, 0x5D, 0x02, 0x02, 0x00])
TURN_OFF_AUTO_NUC_CMD = bytearray([0x00, 0x15, 0x01, 0x00])
TURN_ON_AUTO_NUC_CMD = bytearray([0x00, 0x15, 0x01, 0x01])

Y16_FOURCC = cv2.VideoWriter_fourcc('Y', '1', '6', ' ')
POST_NUC_FLUSH_FRAMES = 4
MAX_REASONABLE_RAW_MEDIAN = 15000
MAX_REASONABLE_RAW_P95 = 20000
YUV_LIKE_HIGH_BYTE_MIN = 120
YUV_LIKE_HIGH_BYTE_MAX = 136
YUV_LIKE_HIGH_BYTE_STD_MAX = 5.0
###########

# initalize serial communication
#ser = serial.Serial(args.serial_port, baudrate=115200, timeout = 1)
# Try to open serial port
try:
    ser = serial.Serial(args.serial_port, baudrate=115200, timeout=1)
except serial.SerialException as e:
    print(f"Error opening serial port {args.serial_port}: {e}")
    print("Serial port not found. Rebooting in 5 seconds...")
    time.sleep(5)
    os.system("sudo reboot")
    sys.exit(1)
    
def keyboard_interrupt_signal_handler(sig, frame):
    print("KeyboardInterrupt received. Initiating graceful shutdown", flush=True)
    QUIT.signal = True

def send_command(
    ser:serial.Serial,
    command:bytearray,
    command_name:str="camera command",
    require_response:bool=True,
):
    if not ser.is_open:
        ser.open()
    
    s = bytearray([])
    s.clear()
    if hasattr(ser, "reset_input_buffer"):
        ser.reset_input_buffer()
    if hasattr(ser, "reset_output_buffer"):
        ser.reset_output_buffer()
    ser.flush()
    
    byte_count = bytearray([len(PROCESS_START) + len(command)])
    s += PROCESS_START #0xAA, first byte to send
    s += byte_count    #Second byte to send
    s += command
    checksum = sum(s)%256 #third to last byte to send
    s += bytearray([checksum])
    s += PROCESS_END #0xEB, 0xAA, last two bytes
    
    ser.write(s)
    ser.flush()
    ret = ser.read_until(PROCESS_END)
    #for debugging purposes
    if args.print_serial:
        
        print("send ", s.hex())
        print("recv ", ret.hex())
    ######################

    if require_response:
        if not ret:
            raise RuntimeError(f"No serial response received after {command_name}.")
        if not ret.endswith(PROCESS_END):
            raise RuntimeError(f"Incomplete serial response after {command_name}: {ret.hex()}")
    
    return ret

def fourcc_to_string(value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return "UNKNOWN"

    chars = ''.join(chr((value >> (8 * i)) & 0xFF) for i in range(4))
    if all(32 <= ord(char) <= 126 for char in chars):
        return chars
    return f"0x{value:08x}"

def describe_frame(frame):
    if frame is None:
        return "None"
    return f"dtype={frame.dtype}, shape={frame.shape}, ndim={frame.ndim}"

def flush_stale_frames(cap, frames=POST_NUC_FLUSH_FRAMES, delay_seconds=0.05):
    for _ in range(frames):
        if not cap.grab():
            break
        time.sleep(delay_seconds)

def read_frame(cap, max_attempts=10):
    for attempt in range(1, max_attempts + 1):
        ret, frame = cap.read()
        if ret and frame is not None:
            return frame
        time.sleep(1)
    raise RuntimeError(f"Error: Failed to capture image after {max_attempts} attempts.")

def normalize_y16_frame(frame):
    if frame is None:
        raise RuntimeError("Camera returned an empty frame.")

    if frame.dtype == np.uint16 and frame.ndim == 2:
        return np.ascontiguousarray(frame), "uint16 2D"

    if frame.dtype == np.uint16 and frame.ndim == 3 and frame.shape[2] == 1:
        return np.ascontiguousarray(frame[:, :, 0]), "uint16 single-channel"

    if frame.dtype == np.uint8 and frame.ndim == 3 and frame.shape[2] == 2:
        contiguous = np.ascontiguousarray(frame)
        y16_image = contiguous.view(np.uint16).reshape(contiguous.shape[0], contiguous.shape[1])
        return y16_image, "uint8 2-channel reinterpreted as Y16"

    raise RuntimeError(
        "Unexpected frame layout from camera "
        f"({describe_frame(frame)}); expected a Y16 temperature frame."
    )

def raw_count_to_kelvin_value(raw_value):
    raw_value = float(raw_value)
    if raw_value <= 7300:
        return (raw_value + 7000.0) / 30.0
    return (raw_value - 3300.0) / 15.0

def raw_count_to_celsius_value(raw_value):
    return raw_count_to_kelvin_value(raw_value) - 273.15

def validate_temperature_frame(y16_image, frame_layout):
    celsius_data = convert_to_celsius(convert_to_kelvin(y16_image))
    stats = {
        "min": int(np.min(y16_image)),
        "max": int(np.max(y16_image)),
        "mean": float(np.mean(y16_image)),
        "median": float(np.median(y16_image)),
        "p95": float(np.percentile(y16_image, 95)),
        "celsius_min": float(np.min(celsius_data)),
        "celsius_mean": float(np.mean(celsius_data)),
        "celsius_max": float(np.max(celsius_data)),
    }

    if stats["median"] > MAX_REASONABLE_RAW_MEDIAN or stats["p95"] > MAX_REASONABLE_RAW_P95:
        high_bytes = (y16_image >> 8).astype(np.uint8)
        high_byte_mean = float(np.mean(high_bytes))
        high_byte_std = float(np.std(high_bytes))
        failure_reason = (
            "Frame raw counts are implausibly high for temperature mode "
            f"(layout={frame_layout}, min={stats['min']}, "
            f"median={stats['median']:.2f} raw / {raw_count_to_celsius_value(stats['median']):.2f} C, "
            f"p95={stats['p95']:.2f} raw / {raw_count_to_celsius_value(stats['p95']):.2f} C, "
            f"max={stats['max']} raw / {raw_count_to_celsius_value(stats['max']):.2f} C)."
        )
        if YUV_LIKE_HIGH_BYTE_MIN <= high_byte_mean <= YUV_LIKE_HIGH_BYTE_MAX and high_byte_std <= YUV_LIKE_HIGH_BYTE_STD_MAX:
            failure_reason += (
                " High-byte pattern looks like packed YUV/video data rather than Y16 temperature data."
            )
        raise RuntimeError(failure_reason)

    return stats

# Initialize camera
def initialize_camera(video_device, is_temp_camera=False):
    print("Initializing camera")
    
    #Set NUC behavior to manual only (this will be reverted if the camera is unplugged)
    print("Disabling auto-NUC")
    send_command(ser, TURN_OFF_AUTO_NUC_CMD, "disable auto-NUC")
    #wait 0.5 seconds to give the camera enough time to see and process command
    time.sleep(0.5)
    
    #Set camera to return images in y16 format
    #This prevents the issue of the camera returning extremely high temperature readings (>1700K)
    print("Sending y16 temp image command")
    send_command(ser, Y16_TEMP_CMD, "enable Y16 temperature mode")
    #wait 0.5 seconds to give the camera enough time to see and process command
    time.sleep(0.5)
    
    #Set camera gain setting to "high".
    #This prevents the issue of the camera returning extremely low temperature readings (Raw < 400)
    print("Setting camera to high sensitivity mode")
    send_command(ser, SET_HIGH_GAIN_CMD, "set high sensitivity mode")
    #wait 0.5 seconds to give the camera enough time to see and process command
    time.sleep(0.5)
    
    print("Opening video device")
    cap = cv2.VideoCapture(video_device, cv2.CAP_V4L2)
    if not cap.isOpened():
        raise RuntimeError("Error: could not open video device.")
        
    if is_temp_camera:
        # Set the desired frame format to Y16
        cap.set(cv2.CAP_PROP_CONVERT_RGB, 0)
        cap.set(cv2.CAP_PROP_FOURCC, Y16_FOURCC)
        time.sleep(0.2)
        reported_fourcc = fourcc_to_string(cap.get(cv2.CAP_PROP_FOURCC))
        reported_format = cap.get(cv2.CAP_PROP_FORMAT)
        print(f"Requested Y16 stream. Camera reports FOURCC={reported_fourcc!r}, FORMAT={reported_format}")
        
    #Silently capture an initial image so NUC'ing happens before the first data collection
    try:
        capture_image(cap, silent=True)
    except RuntimeError:
        cap.release()
        raise
    
    return cap

# Capture image from camera
def capture_image(cap, max_attempts=10, silent=False):
    #send manual NUC command
    if not silent:
        print("Sending NUC command")
    send_command(ser, MANUAL_NUC_CMD, "manual NUC", require_response=False)
    #wait 5 seconds to make sure NUC'ing is finished
    time.sleep(5)
    flush_stale_frames(cap)
    if not silent:
        print("Capturing image from camera")
    frame = read_frame(cap, max_attempts=max_attempts)
    y16_image, frame_layout = normalize_y16_frame(frame)
    stats = validate_temperature_frame(y16_image, frame_layout)
    if not silent:
        print(
            "Validated Y16 frame "
            f"({frame_layout}; raw min={stats['min']}, mean={stats['mean']:.2f}, max={stats['max']}; "
            f"C min={stats['celsius_min']:.2f}, mean={stats['celsius_mean']:.2f}, max={stats['celsius_max']:.2f})"
        )
    return y16_image

# Save image
def save_image(image, filename, normalize_to_8bit:bool=False):
    if normalize_to_8bit:
        #normalize the image to 8 bit range and convert to uint8
        image_to_save = cv2.normalize(image, None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)
    else:
        image_to_save = image.copy()
        
    cv2.imwrite(filename, image_to_save)

# Save image as float32 too - MRD 3/10/2025
def save_image_as_float32(image, filename):
    """Save the image directly as float 32 to avoid precision loss"""
    profile={
        'driver': 'GTiff',
        'dtype': 'float32',
        'width': image.shape[1],
        'height': image.shape[0],
        'count': 1,
        'compress': 'NONE', # disable compression
        'tiled': False, #ensure single strip
        'blockysize': image.shape[0], # full image as a single strip
        'interleave': 'band'
    }

    with rasterio.open(filename, 'w', **profile) as dst:
        dst.write(image.astype(np.float32),1)

# Save raw, kelvin, and celsius temp data to csv
def save_temp_data(raw_data, kelvin_data, celsius_data, raw_filename, kelvin_filename, celsius_filename):
    np.savetxt(raw_filename, raw_data, delimiter=',', fmt='%d')
    np.savetxt(kelvin_filename, kelvin_data, delimiter=',', fmt='%.2f')
    np.savetxt(celsius_filename, celsius_data, delimiter=',', fmt='%.2f')
    
def save_raw_temp_data(raw_data, raw_filename):
    np.savetxt(raw_filename, raw_data, delimiter=',', fmt='%d')
    
def save_celsius_data(celsius_data, celsius_filename):
    np.savetxt(celsius_filename, celsius_data, delimiter=',', fmt='%.2f')
    
def save_kelvin_data(kelvin_data, kelvin_filename):
    np.savetxt(kelvin_filename, kelvin_data, delimiter=',', fmt='%.2f')

# Convert raw counts to temperature in Kelvin
def convert_to_kelvin(raw_data):
    temp_data = np.zeros_like(raw_data, dtype=np.float32)
    mask = raw_data <= 7300
    temp_data[mask] = (raw_data[mask] + 7000.0) / 30.0
    temp_data[~mask] = (raw_data[~mask] - 3300.0) / 15.0
    return temp_data

# Convert Kelvin to Celsius
def convert_to_celsius(kelvin_data):
    return kelvin_data - 273.15

def acquire_temperature_frame(cap, video_device, max_camera_attempts=3):
    last_error = None
    for attempt in range(1, max_camera_attempts + 1):
        try:
            if cap is None or not cap.isOpened():
                cap = initialize_camera(video_device, is_temp_camera=True)
            y16_image = capture_image(cap)
            return cap, y16_image
        except RuntimeError as exc:
            last_error = exc
            print(f"[WARN] Capture attempt {attempt} failed: {exc}", flush=True)
            if cap is not None and cap.isOpened():
                cap.release()
            cap = None
            time.sleep(1)

    raise RuntimeError(
        "Failed to capture a valid Y16 temperature frame after "
        f"{max_camera_attempts} attempts. Last error: {last_error}"
    )

def main():

    #Define behavior for pressing Ctrl+C to allow for gracefully exiting the program
    #This prevents the program from exiting without releasing the camera, which can
    #cause issues the next time the program is run
    signal.signal(signal.SIGINT, keyboard_interrupt_signal_handler)
    
    temp_device = args.device
            
    #open the camera on-demand so failed captures can fully reinitialize it
    temp_cap = None
    
    while True and not QUIT.signal:
        # Capture current time
        now = datetime.now()

        #schedule the next capture
        next_capture_time = now + delay_timedelta

        # Capture raw temperature data
        temp_cap, y16_image = acquire_temperature_frame(temp_cap, temp_device)
        current_time = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Define image filename
        image_filename = os.path.join(img_dir, f'{device_name}_thermal_image_{current_time}.tif')
        
        # Save image
        #if not args.no_image_save:
        #    save_image(y16_image, image_filename)
        #    print(f'Saved temperature image {image_filename}')

        # Convert raw counts to temperature in Kelvin
        kelvin_data = convert_to_kelvin(y16_image)

        # Convert Kelvin to Celsius
        celsius_data = convert_to_celsius(kelvin_data)

        # Save teh float 32 data -mrd 3/10/25
        celsius_image_filename = os.path.join(img_dir, f'{device_name}_{current_time}.tiff')
        save_image_as_float32(celsius_data, celsius_image_filename)
        print(f"Saved Celsius image {celsius_image_filename}")

        if args.mean_temps_file is not None:
            print(f"Mean Temps - Raw Counts ({y16_image.mean():.2f}), Kelvin ({kelvin_data.mean():.2f}), Celsius ({celsius_data.mean():.2f})")
            #save mean temps to file with timestamp
            with open(mean_temps_filename, 'a+') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow([current_time, y16_image.mean(), kelvin_data.mean(), celsius_data.mean()])

        # Define filenames for raw, kelvin, and celsius data
        raw_data_filename = os.path.join(csv_dir, f'raw_temp_data_{current_time}.csv')
        kelvin_data_filename = os.path.join(csv_dir, f'temp_data_kelvin_{current_time}.csv')
        celsius_data_filename = os.path.join(csv_dir, f'temp_data_celsius_{current_time}.csv')

        # Save raw, kelvin, and celsius data
        save_raw_temp_data(y16_image, raw_data_filename)
        print(f'Saved raw temp data {raw_data_filename}', flush=True)
        if not args.save_raw_only:
            #save_kelvin_data(kelvin_data, kelvin_data_filename)
            save_celsius_data(celsius_data, celsius_data_filename)
            #print(f'Saved temperature data in Kelvin {kelvin_data_filename}')
            print(f'Saved temperature data in Celsius {celsius_data_filename}')
        
        #replaced with individual functions to allow more flexibility.
        # save_temp_data(y16_image, kelvin_data, celsius_data, raw_data_filename, kelvin_data_filename, celsius_data_filename)
        # print(f'Saved raw temp data {raw_data_filename}', flush=True)
        # print(f'Saved temperature data in Kelvin {kelvin_data_filename}')
        # print(f'Saved temperature data in Celsius {celsius_data_filename}')
        

        #end program if --capture_single_image is passed
        if args.capture_single_image:
            QUIT.signal = True

        #wait until next_capture_time
        while (datetime.now() < next_capture_time):
            
            #check if end_time has passed
            if datetime.now() > end_time:
                QUIT.signal = True
        
                    
            #display countdown if --display_countdown is passed
            if args.display_countdown and not args.capture_single_image:
                countdown = next_capture_time.replace(microsecond=0) - datetime.now().replace(microsecond=0)
                
                msg = f"next capture in {countdown}"
                print(msg, end='\r')
                time.sleep(0.5)
                print(' ' * len(msg), end='\r')
            if QUIT.signal:break
            
        if QUIT.signal:break
            
    #re-enable auto-NUC
    print("Re-Enabling auto-NUC")
    send_command(ser, TURN_ON_AUTO_NUC_CMD, "re-enable auto-NUC")
    time.sleep(1)
    
    #release camera
    print("Releasing capture device")
    if temp_cap is not None and temp_cap.isOpened():
        temp_cap.release()
    
    #close serial port
    print("Closing serial port")
    ser.close()
    
    return 1


if __name__ == "__main__":
    main()
