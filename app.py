from flask import Flask, request, render_template, jsonify
from flask_socketio import SocketIO, emit
import cloudinary
import cloudinary.uploader
import cloudinary.api
import os
import cv2
import numpy as np
from PIL import Image
import time
from io import BytesIO
import requests
import logging

app = Flask(__name__)
socketio = SocketIO(app)

# Configure logging
logging.basicConfig(level=logging.INFO)

# Cloudinary configuration
cloudinary.config(
    cloud_name='dkaxmhco0',
    api_key='281129765289341',
    api_secret='gw8IVtCnibFlN0Wso4-ztoWUo9Q'
)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}

def overlay_images(background_url, overlay_url):
    background = Image.open(BytesIO(requests.get(background_url).content)).convert("RGBA")
    overlay = Image.open(BytesIO(requests.get(overlay_url).content)).convert("RGBA")
    
    # Resize background to match overlay size
    background = background.resize(overlay.size)
    
    # Create a new image blending the background with the overlay
    result = Image.alpha_composite(background, overlay)
    return result

def create_slideshow(video_url, image_urls, output_path, fps=30.0):
    try:
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Download the video
        video_path = 'uploads/video.mp4'
        os.makedirs(os.path.dirname(video_path), exist_ok=True)
        with requests.get(video_url, stream=True) as r:
            r.raise_for_status()
            with open(video_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        
        # Process video and images
        video = cv2.VideoCapture(video_path)
        width = int(video.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(video.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        # Use mp4v codec for wider compatibility
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
            progress = (current_frame / total_frames) * 50
            socketio.emit('progress', {'progress': progress, 'task': 'Processing video'})
        
        # Add images to the video
        for idx, img_url in enumerate(image_urls):
            img_data = requests.get(img_url).content
            img = cv2.imdecode(np.frombuffer(img_data, np.uint8), cv2.IMREAD_COLOR)
            img = cv2.resize(img, (width, height))
            
            for _ in range(int(3 * fps)):
                out.write(img)
            
            progress = 50 + ((idx + 1) / len(image_urls)) * 45
            socketio.emit('progress', {'progress': progress, 'task': 'Adding images'})
        
        video.release()
        out.release()
        
        # Clean up temporary files
        os.remove(video_path)
        
        # Upload processed video to Cloudinary
        logging.info(f"Uploading processed video to Cloudinary: {output_path}")
        upload_result = cloudinary.uploader.upload(output_path, 
                                                   folder="vi-video", 
                                                   resource_type="video")
        video_url = upload_result['secure_url']
        
        socketio.emit('processing_complete', {'video_url': video_url})
        socketio.emit('progress', {'progress': 100, 'task': 'Processing complete'})
        
        # Clean up output video
        os.remove(output_path)
        
        return video_url
    except Exception as e:
        logging.error(f"Error in create_slideshow: {str(e)}")
        socketio.emit('processing_error', {'error': f'Failed to create slideshow: {str(e)}'})
        return None

@app.route('/', methods=['GET', 'POST'])
def upload_files():
    if request.method == 'POST':
        if 'files[]' not in request.files:
            return jsonify({'error': 'No file part'}), 400
        
        files = request.files.getlist('files[]')
        
        if not files or files[0].filename == '':
            return jsonify({'error': 'No selected files'}), 400
        
        merged_paths = []
        transparent_overlay_url = 'https://res.cloudinary.com/dkaxmhco0/image/upload/v1720078449/zqxthg3pzfqodbx96kbo.png'
        
        for file in files:
            if file and allowed_file(file.filename):
                try:
                    upload_result = cloudinary.uploader.upload(file, folder="vi-image")
                    file_url = upload_result['secure_url']
                    
                    socketio.emit('progress', {'progress': 0, 'task': 'Uploading'})
                    
                    result = overlay_images(file_url, transparent_overlay_url)
                    
                    result_io = BytesIO()
                    if file.filename.lower().endswith(('.jpg', '.jpeg')):
                        result = result.convert('RGB')
                        result.save(result_io, 'JPEG')
                    else:
                        result.save(result_io, 'PNG')
                    result_io.seek(0)
                    
                    overlaid_result = cloudinary.uploader.upload(result_io, folder="vi-image")
                    merged_paths.append(overlaid_result['secure_url'])
                except Exception as e:
                    logging.error(f"Error processing file {file.filename}: {str(e)}")
                    return jsonify({'error': f'Error processing file {file.filename}'}), 500
        
        if not merged_paths:
            return jsonify({'error': 'No valid files uploaded'}), 400
        
        default_video_url = 'https://res.cloudinary.com/dkaxmhco0/video/upload/v1720078520/video_wxrh5b.mp4'
        output_video = 'output/video.mp4'
        socketio.start_background_task(target=create_slideshow, video_url=default_video_url, image_urls=merged_paths, output_path=output_video)
        
        return jsonify({'message': 'Files uploaded successfully, processing video.'}), 202
    
    return render_template('upload.html')

@app.route('/download', methods=['GET'])
def download_video():
    return jsonify({'message': 'Video processing in progress. Please wait for the processing_complete event.'})

@socketio.on('connect')
def handle_connect():
    emit('connected', {'data': 'Connected'})

if __name__ == '__main__':
    socketio.run(app, debug=True)