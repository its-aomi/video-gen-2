from flask import Flask, request, send_file, render_template, jsonify
from flask_socketio import SocketIO, emit
from PIL import Image
import os
import cv2
import numpy as np
from werkzeug.utils import secure_filename
import time

app = Flask(__name__)
socketio = SocketIO(app)

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB limit

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def overlay_images(background, overlay):
    background = Image.open(background).convert("RGBA")
    overlay = Image.open(overlay).convert("RGBA")
    
    # Resize background to match overlay size
    background = background.resize(overlay.size)
    
    # Create a new image blending the background with the overlay
    result = Image.alpha_composite(background, overlay)
    return result

def create_slideshow(video_path, image_paths, output_path, fps=30.0):
    # Open the video
    video = cv2.VideoCapture(video_path)
    
    # Get video properties
    width = int(video.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(video.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    # Create VideoWriter object
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
    
    # Write original video frames
    total_frames = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
    current_frame = 0
    while True:
        ret, frame = video.read()
        if not ret:
            break
        out.write(frame)
        current_frame += 1
        progress = (current_frame / total_frames) * 50  # 50% for video
        socketio.emit('progress', {'progress': progress, 'task': 'Processing'})
    
    # Add images to the video
    for idx, img_path in enumerate(image_paths):
        img = cv2.imread(img_path)
        img = cv2.resize(img, (width, height))
        
        # Write the image for 3 seconds (3 * fps frames)
        for _ in range(int(3 * fps)):
            out.write(img)
        
        progress = 50 + ((idx + 1) / len(image_paths)) * 50  # Remaining 50% for images
        socketio.emit('progress', {'progress': progress, 'task': 'Processing'})
    
    # Release everything
    video.release()
    out.release()
    socketio.emit('progress', {'progress': 100, 'task': 'Processing'})

@app.route('/', methods=['GET', 'POST'])
def upload_files():
    if request.method == 'POST':
        if 'files[]' not in request.files:
            return jsonify({'error': 'No file part'}), 400
        
        files = request.files.getlist('files[]')
        
        if not files or files[0].filename == '':
            return jsonify({'error': 'No selected files'}), 400
        
        merged_paths = []
        transparent_overlay = 'uploads/main.png'  # This is your main transparent image
        
        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                
                # Emit progress for upload
                socketio.emit('progress', {'progress': 0, 'task': 'Uploading'})
                
                # Overlay the transparent image on top of the uploaded image
                result = overlay_images(file_path, transparent_overlay)
                result_path = os.path.join(app.config['UPLOAD_FOLDER'], f'overlaid_{filename}')
                
                # Save the result. If it's a JPG, convert to RGB first.
                if filename.lower().endswith(('.jpg', '.jpeg')):
                    result = result.convert('RGB')
                    result.save(result_path, 'JPEG')
                else:
                    result.save(result_path)
                
                merged_paths.append(result_path)
        
        if not merged_paths:
            return jsonify({'error': 'No valid files uploaded'}), 400
        
        # Create slideshow in a separate thread
        default_video = 'uploads/video.mp4'
        output_video = 'output/video.mp4'
        socketio.start_background_task(target=create_slideshow, video_path=default_video, image_paths=merged_paths, output_path=output_video)
        
        return jsonify({'message': 'Files uploaded successfully, processing video.'}), 202  # Accepted
    
    return render_template('upload.html')

@app.route('/download', methods=['GET'])
def download_video():
    output_video = 'output/video.mp4'
    return send_file(output_video, as_attachment=True)

@socketio.on('connect')
def handle_connect():
    emit('connected', {'data': 'Connected'})

if __name__ == '__main__':
    socketio.run(app, debug=True)
