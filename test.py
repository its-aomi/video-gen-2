# app.py
from flask import Flask, render_template, jsonify
import cloudinary
import cloudinary.uploader
import cloudinary.api
from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips
import os
import tempfile
import requests

app = Flask(__name__)

cloudinary.config(
    cloud_name="dkaxmhco0",
    api_key="281129765289341",
    api_secret="gw8IVtCnibFlN0Wso4-ztoWUo9Q"
)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process_video', methods=['POST'])
def process_video():
    initial_video_url = 'https://res.cloudinary.com/dkaxmhco0/video/upload/v1720078520/video_wxrh5b.mp4'
    transparent_image_url = 'https://res.cloudinary.com/dkaxmhco0/image/upload/v1720154742/pqwfwc3r1y4djvnqqdyt.png'
    image_folder = 'vi-image'

    # Download the initial video and transparent image
    initial_video_path = download_from_url(initial_video_url)
    transparent_image_path = download_from_url(transparent_image_url)

    # Get images from the Cloudinary folder
    images = cloudinary.api.resources(type='upload', prefix=image_folder, resource_type='image')
    image_urls = [image['secure_url'] for image in images['resources']]

    # Process video
    final_video_path = process_and_create_video(initial_video_path, transparent_image_path, image_urls)

    # Upload final video to Cloudinary
    response = cloudinary.uploader.upload(final_video_path, resource_type='video', folder='vi-video')
    
    return jsonify({"video_url": response['secure_url']})

def download_from_url(url):
    response = requests.get(url)
    _, temp_path = tempfile.mkstemp()
    with open(temp_path, 'wb') as f:
        f.write(response.content)
    return temp_path

def process_and_create_video(video_path, transparent_image_path, image_urls):
    video_clip = VideoFileClip(video_path)
    transparent_image_clip = ImageClip(transparent_image_path)
    
    # Assume all images are the same dimensions as the video
    final_clips = [video_clip]

    for image_url in image_urls:
        background_image_path = download_from_url(image_url)
        background_clip = ImageClip(background_image_path).set_duration(video_clip.duration)
        transparent_image_clip_resized = transparent_image_clip.set_duration(video_clip.duration).resize(height=background_clip.h)
        final_clip = CompositeVideoClip([background_clip, transparent_image_clip_resized.set_position("center")])
        final_clips.append(final_clip)

    final_video = concatenate_videoclips(final_clips)
    final_video_path = os.path.join(tempfile.gettempdir(), 'final_video.mp4')
    final_video.write_videofile(final_video_path, codec="libx264", fps=24)
    
    return final_video_path

if __name__ == '__main__':
    app.run(debug=True)
