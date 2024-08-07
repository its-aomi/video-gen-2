from flask import Flask, render_template, jsonify, request, send_file, url_for, Response
import cloudinary
import cloudinary.uploader
import cloudinary.api
from moviepy.editor import VideoFileClip, ImageClip, concatenate_videoclips
import os
import tempfile
import requests
from werkzeug.utils import secure_filename
from PIL import Image
import numpy as np
from dotenv import load_dotenv
import threading

app = Flask(__name__)

# Load environment variables from .env file
load_dotenv()

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'avif', 'hevc', 'heic'}

# Cloudinary configuration
cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET')
)

sse_flag = False

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    existing_images = get_existing_images()
    return render_template('index.html', existing_images=existing_images)

def get_existing_images():
    image_folder = 'vi-image'
    images = cloudinary.api.resources(type='upload', prefix=image_folder, resource_type='image', max_results=500)
    return [image['secure_url'] for image in images['resources']]

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
    
    # Start video processing in a separate thread
    threading.Thread(target=process_video).start()

    # Return a response immediately after uploading images
    return jsonify({"status": "Images uploaded, processing video... This will take a while, you can check back later."})

def process_video():
    global sse_flag
    initial_video_url = 'https://res.cloudinary.com/dkaxmhco0/video/upload/q_auto/v1721140698/dec_3_eeu0t3.mp4'
    transparent_image_url = 'https://res.cloudinary.com/dkaxmhco0/image/upload/q_auto/v1721140723/tc4qypmax5eeuzi1gy8e.png'
    image_folder = 'vi-image'

    # Download the initial video and transparent image
    initial_video_path = download_from_url(initial_video_url)
    transparent_image_path = download_from_url(transparent_image_url)

    # Get all images from the Cloudinary folder
    images = cloudinary.api.resources(type='upload', prefix=image_folder, resource_type='image', max_results=500)
    image_urls = [image['secure_url'] for image in images['resources']]

    # Process video
    final_video_path = process_and_create_video(initial_video_path, transparent_image_path, image_urls)

    print(f"Video processing complete. Final video available at: /get_video/{os.path.basename(final_video_path)}")

    # Notify the frontend that the video processing is complete
    sse_flag = True

@app.route('/video_processing_status')
def video_processing_status():
    def generate():
        global sse_flag
        if sse_flag:
            yield 'data: video_processed\n\n'
            sse_flag = False

    return app.response_class(generate(), mimetype='text/event-stream')

@app.route('/show_video/<filename>')
def show_video(filename):
    video_url = url_for('get_video', filename=filename)
    return render_template('video.html', video_url=video_url)

@app.route('/get_video/<filename>')
def get_video(filename):
    return send_file(os.path.join(tempfile.gettempdir(), filename), mimetype='video/mp4')

def download_from_url(url):
    response = requests.get(url)
    _, temp_path = tempfile.mkstemp()
    with open(temp_path, 'wb') as f:
        f.write(response.content)
    return temp_path

def process_and_create_video(video_path, transparent_image_path, image_urls, image_duration=2):
    video_clip = VideoFileClip(video_path)
    
    # Get video dimensions
    video_width, video_height = video_clip.w, video_clip.h
    
    final_clips = [video_clip]

    def overlay_transparent_image(background_path, overlay_path, target_size):
        with Image.open(background_path) as bg_img:
            with Image.open(overlay_path) as overlay_img:
                # Resize background image to match video dimensions
                bg_img = bg_img.resize(target_size, Image.LANCZOS)
                bg_img = bg_img.convert("RGBA")
                
                # Resize overlay image to match video dimensions
                overlay_img = overlay_img.resize(target_size, Image.LANCZOS)
                overlay_img = overlay_img.convert("RGBA")
                
                combined_img = Image.alpha_composite(bg_img, overlay_img)
                return np.array(combined_img)

    for image_url in image_urls:
        background_image_path = download_from_url(image_url)
        combined_image_array = overlay_transparent_image(background_image_path, transparent_image_path, (video_width, video_height))
        combined_image_clip = ImageClip(combined_image_array).set_duration(image_duration)
        final_clips.append(combined_image_clip)

    final_video = concatenate_videoclips(final_clips)
    final_video_path = os.path.join(tempfile.gettempdir(), 'final_video.mp4')
    final_video.write_videofile(final_video_path, codec="libx264", fps=24)
    
    return final_video_path

if __name__ == '__main__':
    app.run(debug=True)
