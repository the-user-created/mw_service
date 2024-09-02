import time

from flask import Flask, render_template, redirect, url_for, request, Response, jsonify, send_from_directory, g
import log_sensors
import csv
import os
import cv2
import threading

app = Flask(__name__)

cap = cv2.VideoCapture(0)

# Initialize global variables for dynamic log file naming and video file naming
log_file_name = None
video_file_name = None
logging_active = False

# Global variables to hold the threads
video_thread = None
recording_active = False
video_writer = None

@app.route('/')
def index():
    global log_file_name
    data = []
    try:
        if log_file_name is not None:
            with open(log_file_name, newline='') as csvfile:
                reader = csv.reader(csvfile)
                data = list(reader)
    except FileNotFoundError:
        data = []

    return render_template('index.html', data=data)


@app.route('/start', methods=['POST'])
def start_logging():
    global video_thread, log_file_name, video_file_name, logging_active, recording_active

    power_setting = request.form['power']
    catalyst = request.form['catalyst']

    # Create unique log file and video file names
    log_file_name = f"{power_setting}_{catalyst}_sensor_log.csv"
    video_file_name = f"{power_setting}_{catalyst}_video.avi"
    print(f"Log file name: {log_file_name}")
    print(f"Video file name: {video_file_name}")
    print(f"CWD: {os.getcwd()}")

    # Start video recording
    recording_active = True

    # Start logging with the new file name
    logging_active = True
    log_sensors.start_logging(log_file_name)

    return redirect(url_for('index'))


@app.route('/stop', methods=['POST'])
def stop_logging():
    global logging_active, recording_active
    log_sensors.stop_logging()
    logging_active = False

    # Stop video recording
    recording_active = False

    return redirect(url_for('index'))


def gen_frames():
    global cap, recording_active, video_writer, video_file_name
    print("video file name: ", video_file_name)
    if not cap.isOpened():
        print("Camera is already open.")
        return

    print("Camera opened successfully.")
    fourcc = cv2.VideoWriter_fourcc(*'XVID')
    video_writer = cv2.VideoWriter(video_file_name, fourcc, 20.0, (640, 480))
    print(f"Video writer created: {video_writer}")

    try:
        while True:
            success, frame = cap.read()
            if not success:
                print("Failed to capture frame.")
                break
            if recording_active and video_writer is not None:
                print("Writing frame to video.")
                video_writer.write(frame)
            ret, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
    except Exception as e:
        print(f"Error while reading camera stream: {e}")
    finally:
        if video_writer is not None:
            video_writer.release()


@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/get_latest_data')
def get_latest_data():
    global log_file_name
    data = []
    try:
        if log_file_name is not None:
            with open(log_file_name, newline='') as csvfile:
                reader = csv.reader(csvfile)
                data = list(reader)
    except FileNotFoundError:
        data = []

    # Skip the first row, which contains the headers
    if len(data) > 1:
        data_without_headers = data[1:]  # Skip the first row
    else:
        data_without_headers = []

    # Round thermistor readings to 2 decimal places
    rounded_data = []
    for row in data_without_headers:  # Process data without headers
        rounded_row = [row[0]] + [f"{float(x):.2f}" for x in row[1:]]  # Round thermistor and thermocouple readings
        rounded_data.append(rounded_row)

    return jsonify(rounded_data[-10:])  # Return the last 10 rows of data


@app.route('/download_log')
def download_log():
    global log_file_name
    # Check if the file name is not None and the file exists
    print("Download log request received.")
    print(f"Log file name: {log_file_name}")
    if log_file_name and os.path.exists(log_file_name):
        directory = os.path.dirname(os.path.abspath(log_file_name))
        return send_from_directory(directory=directory, path=os.path.basename(log_file_name), as_attachment=True)
    return "Log file not found", 404


@app.route('/download_video')
def download_video():
    # TODO: fix
    global video_file_name
    print("Download video request received.")
    print(f"Video file name: {video_file_name}")
    if video_file_name and os.path.exists(video_file_name):
        print("Video file found.")
        return send_from_directory(directory=os.getcwd(), filename=video_file_name, as_attachment=True, mimetype='video/avi', path="./")
    return "Video file not found", 404


if __name__ == '__main__':
    try:
        app.run(host='0.0.0.0', port=5000)
    except KeyboardInterrupt:
        print("Keyboard interrupt detected.")
        stop_logging()
        if cap.isOpened():
            cap.release()
            print("Camera released.")


# Camera live feed stops working when logging starts (conflicting control of camera between live feed and recording?)
# Recording seems to work well.