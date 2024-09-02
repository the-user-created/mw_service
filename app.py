from flask import Flask, render_template, redirect, url_for, request, Response, jsonify, send_from_directory
import log_sensors
import csv
import os
import cv2

app = Flask(__name__)

# Initialize global variables for dynamic log file naming and video file naming
log_file_name = None
video_file_name = None
logging_active = False  # To track if logging is currently active


@app.route('/')
def index():
    data = []
    try:
        if log_file_name:
            with open(log_file_name, newline='') as csvfile:
                reader = csv.reader(csvfile)
                data = list(reader)
    except FileNotFoundError:
        data = []

    return render_template('index.html', data=data)


@app.route('/start', methods=['POST'])
def start_logging():
    global log_file_name, video_file_name, logging_active

    power_setting = request.form['power']
    catalyst = request.form['catalyst']

    # Create unique log file and video file names
    log_file_name = f"{power_setting}_{catalyst}_sensor_log.csv"
    video_file_name = f"{power_setting}_{catalyst}_video.avi"

    # Start logging with the new file name
    logging_active = True
    log_sensors.start_logging(log_file_name)

    return redirect(url_for('index'))


@app.route('/stop', methods=['POST'])
def stop_logging():
    global logging_active

    log_sensors.stop_logging()
    logging_active = False

    # Ensure the camera is fully released
    cap = cv2.VideoCapture(0)
    if cap.isOpened():
        cap.release()
        print("Camera released after logging stopped.")

    return redirect(url_for('index'))


# Video streaming function using GStreamer
def gen_frames():
    print("Attempting to open the camera...")
    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        print("Failed to open camera.")
        return

    print("Camera opened successfully.")
    try:
        while True:
            success, frame = cap.read()
            if not success:
                print("Failed to capture frame.")
                break
            else:
                ret, buffer = cv2.imencode('.jpg', frame)
                frame = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
    except Exception as e:
        print(f"Error while reading camera stream: {e}")
    finally:
        cap.release()
        print("Camera released in gen_frames.")


@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/get_latest_data')
def get_latest_data():
    data = []
    try:
        if log_file_name:
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
    if log_file_name and os.path.exists(log_file_name):
        directory = os.path.dirname(os.path.abspath(log_file_name))
        return send_from_directory(directory=directory, path=os.path.basename(log_file_name), as_attachment=True)
    return "Log file not found", 404


@app.route('/download_video')
def download_video():
    if video_file_name and os.path.exists(video_file_name):
        return send_from_directory(directory=os.getcwd(), filename=video_file_name, as_attachment=True)
    return "Video file not found", 404


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)