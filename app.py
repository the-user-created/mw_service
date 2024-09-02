from flask import Flask, render_template, redirect, url_for, request, Response, jsonify, send_from_directory
import log_sensors
import csv
import os
import cv2
import threading

app = Flask(__name__)

class Logger:
    def __init__(self):
        self.log_file_name = None
        self.video_file_name = None
        self.logging_active = False
        self.providing_frames = True
        self.video_writer = None
        self.cap = cv2.VideoCapture(0)
        self.frame_thread = None

    def start_logging(self, power_setting, catalyst):
        self.log_file_name = f"{power_setting}_{catalyst}_sensor_log.csv"
        self.video_file_name = f"{power_setting}_{catalyst}_video.avi"
        print(f"Log file name: {self.log_file_name}")
        print(f"Video file name: {self.video_file_name}")
        print(f"CWD: {os.getcwd()}")

        self.logging_active = True
        log_sensors.start_logging(self.log_file_name)

        # Start the frame generation in a separate thread
        self.frame_thread = threading.Thread(target=self.gen_frames)
        self.frame_thread.start()

    def stop_logging(self):
        log_sensors.stop_logging()
        self.logging_active = False

        # Ensure the frame thread is properly stopped
        if self.frame_thread is not None:
            self.frame_thread.join()

    def gen_frames(self):
        if not self.cap.isOpened():
            print("Camera is already open.")
            return

        print("Camera opened successfully.")

        has_setup_writer = False

        try:
            while self.providing_frames:
                # Set up video writer if it hasn't been done yet
                if not has_setup_writer and self.logging_active:
                    fourcc = cv2.VideoWriter_fourcc(*'XVID')
                    self.video_writer = cv2.VideoWriter(self.video_file_name, fourcc, 20.0, (640, 480))
                    has_setup_writer = True
                    print(f"Video writer set up with file name: {self.video_file_name}")

                success, frame = self.cap.read()
                if not success:
                    print("Failed to capture frame.")
                    break

                # Write frame to video if recording is active
                if self.logging_active and self.video_writer is not None:
                    print("Writing frame to video.")
                    self.video_writer.write(frame)

                # Send frame as JPEG to the client
                ret, buffer = cv2.imencode('.jpg', frame)
                frame = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        except Exception as e:
            print(f"Error while reading camera stream: {e}")
        finally:
            if self.video_writer is not None:
                self.video_writer.release()

@app.route('/')
def index():
    data = []
    try:
        if logger.log_file_name is not None:
            with open(logger.log_file_name, newline='') as csvfile:
                reader = csv.reader(csvfile)
                data = list(reader)
    except FileNotFoundError:
        data = []

    return render_template('index.html', data=data)

@app.route('/start', methods=['POST'])
def start_logging():
    power_setting = request.form['power']
    catalyst = request.form['catalyst']
    logger.start_logging(power_setting, catalyst)
    return redirect(url_for('index'))

@app.route('/stop', methods=['POST'])
def stop_logging():
    logger.stop_logging()
    return redirect(url_for('index'))

@app.route('/video_feed')
def video_feed():
    return Response(logger.gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/get_latest_data')
def get_latest_data():
    data = []
    try:
        if logger.log_file_name is not None:
            with open(logger.log_file_name, newline='') as csvfile:
                reader = csv.reader(csvfile)
                data = list(reader)
    except FileNotFoundError:
        data = []

    if len(data) > 1:
        data_without_headers = data[1:]
    else:
        data_without_headers = []

    rounded_data = []
    for row in data_without_headers:
        rounded_row = [row[0]] + [f"{float(x):.2f}" for x in row[1:]]
        rounded_data.append(rounded_row)

    return jsonify(rounded_data[-10:])

@app.route('/download_log')
def download_log():
    if logger.log_file_name and os.path.exists(logger.log_file_name):
        directory = os.path.dirname(os.path.abspath(logger.log_file_name))
        return send_from_directory(directory=directory, path=os.path.basename(logger.log_file_name), as_attachment=True)
    return "Log file not found", 404

@app.route('/download_video')
def download_video():
    if logger.video_file_name and os.path.exists(logger.video_file_name):
        return send_from_directory(directory=os.getcwd(), filename=logger.video_file_name, as_attachment=True, mimetype='video/avi', path="./")
    return "Video file not found", 404

if __name__ == '__main__':
    logger = Logger()

    try:
        app.run(host='0.0.0.0', port=5000)
    except KeyboardInterrupt:
        print("Keyboard interrupt detected.")
        logger.stop_logging()
        logger.providing_frames = False
        if logger.cap.isOpened():
            logger.cap.release()
            print("Camera released.")
