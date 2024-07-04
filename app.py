from flask import Flask, request, send_file, render_template
from PIL import Image
import os
import cv2
import numpy as np
from werkzeug.utils import secure_filename

app = Flask(__name__)

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
    while True:
        ret, frame = video.read()
        if not ret:
            break
        out.write(frame)
    
    # Add images to the video
    for img_path in image_paths:
        img = cv2.imread(img_path)
        img = cv2.resize(img, (width, height))
        
        # Write the image for 3 seconds (3 * fps frames)
        for _ in range(int(3 * fps)):
            out.write(img)
    
    # Release everything
    video.release()
    out.release()

@app.route('/', methods=['GET', 'POST'])
def upload_files():
    if request.method == 'POST':
        if 'files[]' not in request.files:
            return render_template('upload.html', error='No file part')
        
        files = request.files.getlist('files[]')
        
        if not files or files[0].filename == '':
            return render_template('upload.html', error='No selected files')
        
        merged_paths = []
        transparent_overlay = 'uploads/main.png'  # This is your main transparent image
        
        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                
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
            return render_template('upload.html', error='No valid files uploaded')
        
        # Create slideshow
        default_video = 'uploads/video.mp4'
        output_video = 'output/video.mp4'
        try:
            create_slideshow(default_video, merged_paths, output_video)
        except Exception as e:
            return render_template('upload.html', error=f'Error creating slideshow: {str(e)}')
        
        return send_file(output_video, as_attachment=True)
    
    return render_template('upload.html')

if __name__ == '__main__':
    app.run(debug=True)