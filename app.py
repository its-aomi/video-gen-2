import eventlet
eventlet.monkey_patch()

from flask import Flask, request, render_template, jsonify
from flask_socketio import SocketIO, emit
from moviepy.editor import VideoFileClip, ImageClip, concatenate_videoclips
from moviepy.video.io.ffmpeg_tools import ffmpeg_extract_subclip
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
socketio = SocketIO(app, async_mode='eventlet')

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)

# Cloudinary configuration
cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET')
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

def create_slideshow(video_url, image_urls, output_path, fps=30):
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

        # Load the video clip
        video_clip = VideoFileClip(video_path)
        
        # Create image clips
        image_clips = []
        for idx, img_url in enumerate(image_urls):
            img_data = requests.get(img_url).content
            img = Image.open(BytesIO(img_data))
            img = img.resize(video_clip.size, Image.Resampling.LANCZOS)  # Updated resizing method
            img_clip = ImageClip(np.array(img), duration=3)
            image_clips.append(img_clip.set_duration(3))

            progress = 50 + ((idx + 1) / len(image_urls)) * 45
            socketio.emit('progress', {'progress': progress, 'task': 'Adding images'})

        # Concatenate the video clip with image clips
        final_clip = concatenate_videoclips([video_clip] + image_clips)
        
        # Write the final video
        final_clip.write_videofile(output_path, codec="libx264", fps=fps)
        
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
        transparent_overlay_url = 'https://res.cloudinary.com/dkaxmhco0/image/upload/v1720154742/pqwfwc3r1y4djvnqqdyt.png'
        
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