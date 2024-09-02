from flask import Flask, render_template, redirect, url_for, request, Response, jsonify, send_from_directory, g
import log_sensors
import csv
import os
import cv2
import threading

# TODO: Add user input notes section to CSV columns (recorded data table)
app = Flask(__name__)

# Global variables to hold the threads
logging_thread = None

def get_log_file_name() -> str | None:
    if 'log_file_name' not in g:
        g.log_file_name = None
    return g.log_file_name


def set_log_file_name(value) -> None:
    g.log_file_name = value


def get_video_file_name() -> str | None:
    if 'video_file_name' not in g:
        g.video_file_name = None
    return g.video_file_name


def set_video_file_name(value) -> None:
    g.video_file_name = value


def is_logging_active() -> bool:
    if 'logging_active' not in g:
        g.logging_active = False
    return g.logging_active


def set_logging_active(value) -> None:
    g.logging_active = value


@app.route('/')
def index() -> str:
    data = []
    try:
        if get_log_file_name():
            with open(get_log_file_name(), newline='') as csvfile:
                reader = csv.reader(csvfile)
                data = list(reader)
    except FileNotFoundError:
        data = []

    return render_template('index.html', data=data)


@app.route('/start', methods=['POST'])
def start_logging() -> Response:
    global logging_thread

    power_setting = request.form['power']
    catalyst = request.form['catalyst']

    # Create unique log file and video file names
    set_log_file_name(f"{power_setting}_{catalyst}_sensor_log.csv")
    set_video_file_name(f"{power_setting}_{catalyst}_video.avi")

    # Start logging with the new file name
    set_logging_active(True)

    # Start logging in a separate thread
    #logging_thread = threading.Thread(target=log_sensors.start_logging, args=(get_log_file_name(),))
    #logging_thread.start()
    log_sensors.start_logging(get_log_file_name())

    return redirect(url_for('index'))


@app.route('/stop', methods=['POST'])
def stop_logging() -> Response:
    global logging_thread

    log_sensors.stop_logging()
    set_logging_active(False)

    #if logging_thread:
    #    logging_thread.join()  # Wait for the logging thread to finish

    # Ensure the camera is fully released
    cap = cv2.VideoCapture(0)
    if cap.isOpened():
        cap.release()
        print("Camera released after logging stopped.")

    return redirect(url_for('index'))


# Video streaming function using GStreamer
def gen_frames() -> bytes:
    print("Attempting to open the camera...")

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Failed to open camera. It might be in use or not available.")
        yield (b'--frame\r\n'
               b'Content-Type: text/plain\r\n\r\n'
               b'Camera is not available.\r\n')
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


@app.route('/video_feed')
def video_feed() -> Response:
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/get_latest_data')
def get_latest_data() -> str | Response:
    data = []
    try:
        if get_log_file_name():
            with open(get_log_file_name(), newline='') as csvfile:
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
def download_log() -> Response | tuple[str, int]:
    if get_log_file_name() and os.path.exists(get_log_file_name()):
        directory = os.path.dirname(os.path.abspath(get_log_file_name()))
        return send_from_directory(directory=directory, path=os.path.basename(get_log_file_name()), as_attachment=True)
    return "Log file not found", 404


@app.route('/download_video')
def download_video() -> Response | tuple[str, int]:
    if get_video_file_name() and os.path.exists(get_video_file_name()):
        return send_from_directory(directory=os.getcwd(), filename=get_video_file_name(), as_attachment=True, path=get_video_file_name())
    return "Video file not found", 404


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)