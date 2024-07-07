from flask import Flask, render_template, jsonify, request, send_file
import cloudinary
import cloudinary.uploader
import cloudinary.api
import os
import tempfile
import requests
from werkzeug.utils import secure_filename
from PIL import Image
import ffmpeg
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


def download_from_url(url):
    response = requests.get(url)
    _, temp_path = tempfile.mkstemp()
    with open(temp_path, 'wb') as f:
        f.write(response.content)
    return temp_path


def process_and_create_video(video_path, transparent_image_path, image_urls):
    video_file_name = 'initial_video.mp4'
    overlay_file_name = 'transparent_overlay.png'

    # Download and save images
    image_paths = []
    for image_url in image_urls:
        image_path = download_from_url(image_url)
        image_paths.append(image_path)
    
    # Generate the final video using ffmpeg
    final_video_path = os.path.join(tempfile.gettempdir(), 'final_video.mp4')
    overlay_image = Image.open(transparent_image_path)
    overlay_width, overlay_height = overlay_image.size

    # Prepare FFmpeg filter commands
    filter_cmd = []

    for i, image_path in enumerate(image_paths):
        filter_cmd.append(
            f"[0][{i+1}]overlay=W-w:H-h:shortest=1[v{i+1}];"
            f"[v{i+1}][{i+1}]overlay=(W-w)/2:(H-h)/2:shortest=1"
        )

    filter_cmd = ";".join(filter_cmd)

    # Build FFmpeg input command
    input_cmd = [
        ffmpeg.input(video_path).video,
        *[
            ffmpeg.input(img_path).filter("scale", overlay_width, overlay_height).video
            for img_path in image_paths
        ]
    ]

    # Run FFmpeg process
    (
        ffmpeg
        .concat(*input_cmd, v=1, a=1)
        .output(final_video_path, vcodec='libx264', pix_fmt='yuv420p')
        .run()
    )

    return final_video_path



if __name__ == '__main__':
    app.run(debug=True)
