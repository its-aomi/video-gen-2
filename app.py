from flask import Flask, render_template, jsonify, request, send_file
import cloudinary
import cloudinary.uploader
import cloudinary.api
from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips
import os
import tempfile
import requests
from werkzeug.utils import secure_filename
from PIL import Image
import numpy as np
import psutil
import gc
from dotenv import load_dotenv


app = Flask(__name__)

# Load environment variables from .env file
load_dotenv()

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Cloudinary configuration
cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET')
)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload_images', methods=['POST'])
def upload_images():
    if 'files[]' not in request.files:
        return jsonify({"error": "No file part"})
    
    files = request.files.getlist('files[]')
    
    if not files or files[0].filename == '':
        return jsonify({"error": "No selected file"})
    
    for file in files:
        if file and allowed_file(file.filename):
            # Upload file to Cloudinary
            result = cloudinary.uploader.upload(file, folder="vi-image")
            print(f"File uploaded to Cloudinary: {result['secure_url']}")
    
    # Process video after uploading images
    return process_video()

@app.route('/process_video', methods=['POST'])
def process_video():
    initial_video_url = 'https://res.cloudinary.com/dkaxmhco0/video/upload/v1720078520/video_wxrh5b.mp4'
    transparent_image_url = 'https://res.cloudinary.com/dkaxmhco0/image/upload/v1720154742/pqwfwc3r1y4djvnqqdyt.png'
    image_folder = 'vi-image'

    # Download the initial video and transparent image
    initial_video_path = download_from_url(initial_video_url)
    transparent_image_path = download_from_url(transparent_image_url)

    # Get all images from the Cloudinary folder
    images = cloudinary.api.resources(type='upload', prefix=image_folder, resource_type='image', max_results=500)
    image_urls = [image['secure_url'] for image in images['resources']]

    # Process video
    final_video_path = process_and_create_video(initial_video_path, transparent_image_path, image_urls)

    return jsonify({"video_url": f"/get_video/{os.path.basename(final_video_path)}"})

@app.route('/get_video/<filename>')
def get_video(filename):
    return send_file(os.path.join(tempfile.gettempdir(), filename), mimetype='video/mp4')

def download_from_url(url):
    response = requests.get(url)
    _, temp_path = tempfile.mkstemp()
    with open(temp_path, 'wb') as f:
        f.write(response.content)
    return temp_path

def process_and_create_video(video_path, transparent_image_path, image_urls):
    video_clip = VideoFileClip(video_path)
    transparent_image_clip = ImageClip(transparent_image_path)
    
    # Get video dimensions
    video_width, video_height = video_clip.w, video_clip.h
    
    final_clips = [video_clip]

    def resize_image(image_path, width, height):
        with Image.open(image_path) as img:
            img_resized = img.resize((width, height), Image.LANCZOS)
            img_array = np.array(img_resized)
            return ImageClip(img_array)

    # Process images in batches
    batch_size = 5
    for i in range(0, len(image_urls), batch_size):
        batch = image_urls[i:i+batch_size]
        batch_clips = []
        
        for image_url in batch:
            if check_memory_usage():
                background_image_path = download_from_url(image_url)
                background_clip = resize_image(background_image_path, video_width, video_height).set_duration(video_clip.duration)
                transparent_image_clip_resized = transparent_image_clip.resize(height=video_height).set_duration(video_clip.duration)
                final_clip = CompositeVideoClip([background_clip, transparent_image_clip_resized.set_position("center")])
                batch_clips.append(final_clip)
                os.remove(background_image_path)  # Remove temporary file
            else:
                print("Memory usage too high. Skipping image.")
        
        final_clips.extend(batch_clips)
        gc.collect()  # Force garbage collection after each batch

    final_video = concatenate_videoclips(final_clips)
    final_video_path = os.path.join(tempfile.gettempdir(), 'final_video.mp4')
    final_video.write_videofile(final_video_path, codec="libx264", fps=24)
    
    return final_video_path

def check_memory_usage():
    memory_usage = psutil.virtual_memory().percent
    return memory_usage < MAX_MEMORY_PERCENT

if __name__ == '__main__':
    app.run(debug=True)