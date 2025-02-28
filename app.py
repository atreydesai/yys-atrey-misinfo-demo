import os
import json
import subprocess
import yt_dlp
from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/videos'
app.config['PROCESSED_FOLDER'] = 'static/processed'
app.config['JSON_FILE'] = 'data/videos.json'

for directory in [app.config['UPLOAD_FOLDER'], app.config['PROCESSED_FOLDER'], 'data']:
    os.makedirs(directory, exist_ok=True)

def download_video(url, output_dir, output_filename="downloaded_video.mp4", verbose=False):
    """Downloads a video and saves it to the specified directory."""
    try:
        output_path = os.path.join(output_dir, output_filename)
        ydl_opts = {
            'format': 'best',
            'outtmpl': os.path.join(output_dir, 'temp_download.%(ext)s'),
            'quiet': not verbose,
            'no_warnings': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            duration = info_dict.get('duration')
            if duration is None:
                return False, "Could not determine video duration.", None
            if duration > 600:
                return False, "Video exceeds 10-minute limit.", duration
            info_dict = ydl.extract_info(url, download=True)
            downloaded_filename = ydl.prepare_filename(info_dict)
        
        filename, ext = os.path.splitext(downloaded_filename)
        if ext.lower() == '.mp4':
            os.rename(downloaded_filename, output_path)
            return True, "Successfully downloaded and renamed to MP4.", duration
        
        command = [
            'ffmpeg',
            '-i', downloaded_filename,
            '-c:v', 'libx264',
            '-c:a', 'aac',
            '-strict', 'experimental',
            '-y',
            output_path
        ]
        if verbose:
            print(f"Running ffmpeg command: {' '.join(command)}")
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            error_message = f"FFmpeg conversion failed:\nReturn code: {result.returncode}\nStdout: {result.stdout}\nStderr: {result.stderr}"
            if verbose:
                print(error_message)
            os.remove(downloaded_filename)
            return False, error_message, None
        else:
            if verbose:
                print("FFmpeg conversion successful.")
            os.remove(downloaded_filename)
            return True, "Successfully downloaded and converted to MP4.", duration
    except yt_dlp.utils.DownloadError as e:
        return False, f"yt-dlp download error: {e}", None
    except FileNotFoundError:
        return False, "ffmpeg not found. Please make sure ffmpeg is installed and in your system's PATH.", None
    except Exception as e:
        return False, f"An unexpected error occurred: {e}", None

def cut_video(input_path, output_path, start_time, end_time, verbose=False):
    """Cuts a video based on start and end times."""
    try:
        command = [
            'ffmpeg',
            '-i', input_path,
            '-ss', start_time,
            '-to', end_time,
            '-c:v', 'libx264',
            '-c:a', 'aac',
            '-strict', 'experimental',
            '-y',
            output_path
        ]
        if verbose:
            print(f"Running ffmpeg cut command: {' '.join(command)}")
        
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            error_message = f"FFmpeg cutting failed:\nReturn code: {result.returncode}\nStdout: {result.stdout}\nStderr: {result.stderr}"
            if verbose:
                print(error_message)
            return False, error_message
        else:
            if verbose:
                print("FFmpeg cutting successful.")
            return True, "Successfully cut video."
    except Exception as e:
        return False, f"An error occurred during video cutting: {e}"

def validate_time_format(time_str):
    """Validates that a time string is in the format HH:MM:SS or MM:SS"""
    parts = time_str.split(':')
    if len(parts) not in [2, 3]:
        return False
    
    try:
        if len(parts) == 2:
            minutes, seconds = map(int, parts)
            return 0 <= minutes < 60 and 0 <= seconds < 60
        else:
            hours, minutes, seconds = map(int, parts)
            return 0 <= hours < 24 and 0 <= minutes < 60 and 0 <= seconds < 60
    except ValueError:
        return False

def load_json_data():
    """Loads the video data from the JSON file."""
    try:
        if os.path.exists(app.config['JSON_FILE']):
            with open(app.config['JSON_FILE'], 'r') as f:
                return json.load(f)
        return []
    except Exception as e:
        print(f"Error loading JSON data: {e}")
        return []

def save_json_data(data):
    """Saves the video data to the JSON file."""
    try:
        with open(app.config['JSON_FILE'], 'w') as f:
            json.dump(data, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving JSON data: {e}")
        return False

@app.route('/')
def index():
    """Renders the main page of the application."""
    videos = load_json_data()
    return render_template('index.html', videos=videos)

@app.route('/download', methods=['POST'])
def download_video_route():
    """API endpoint to download a video from the JSON data."""
    data = request.get_json()
    video_id = data.get('id')
    
    videos = load_json_data()
    video = next((v for v in videos if v.get('id') == video_id), None)
    
    if not video:
        return jsonify({'success': False, 'message': 'Video not found'})
    
    url = video.get('Shareable_Video_Link')
    filename = f"video_{video_id}.mp4"
    
    success, message, duration = download_video(
        url, 
        app.config['UPLOAD_FOLDER'], 
        filename, 
        verbose=True
    )
    
    if success:
        video['local_path'] = f"{app.config['UPLOAD_FOLDER']}/{filename}"
        video['duration'] = duration
        save_json_data(videos)
        return jsonify({'success': True, 'message': message, 'filename': filename})
    else:
        return jsonify({'success': False, 'message': message})

@app.route('/cut', methods=['POST'])
def cut_video_route():
    """API endpoint to cut a video."""
    data = request.get_json()
    video_id = data.get('id')
    start_time = data.get('startTime')
    end_time = data.get('endTime')
    narrative = data.get('narrative')
    
    # Validate time formats
    if not validate_time_format(start_time) or not validate_time_format(end_time):
        return jsonify({'success': False, 'message': 'Invalid time format. Use HH:MM:SS or MM:SS'})
    
    videos = load_json_data()
    video = next((v for v in videos if v.get('id') == video_id), None)
    
    if not video or not video.get('local_path'):
        return jsonify({'success': False, 'message': 'Video not found or not downloaded'})
    
    input_path = video.get('local_path')
    output_filename = f"cut_{video_id}_{start_time.replace(':', '')}_{end_time.replace(':', '')}.mp4"
    output_path = os.path.join(app.config['PROCESSED_FOLDER'], output_filename)
    
    success, message = cut_video(input_path, output_path, start_time, end_time, verbose=True)
    
    if success:
        # Update video data with cut information
        if 'cuts' not in video:
            video['cuts'] = []
        
        video['cuts'].append({
            'id': len(video.get('cuts', [])) + 1,
            'start_time': start_time,
            'end_time': end_time,
            'narrative': narrative,
            'output_path': output_path,
            'filename': output_filename
        })
        
        save_json_data(videos)
        return jsonify({'success': True, 'message': message, 'filename': output_filename})
    else:
        return jsonify({'success': False, 'message': message})

@app.route('/static/<path:path>')
def serve_static(path):
    """Serves static files."""
    return send_from_directory('static', path)

@app.route('/load_videos', methods=['POST'])
def load_videos():
    """API endpoint to load videos from a JSON file and append to existing data."""
    try:
        file = request.files.get('json_file')
        if not file:
            return jsonify({'success': False, 'message': 'No file provided'})
        
        filename = secure_filename(file.filename)
        if not filename.endswith('.json'):
            return jsonify({'success': False, 'message': 'File must be a JSON file'})
        
        file_path = os.path.join('data', filename)
        file.save(file_path)
        with open(file_path, 'r') as f:
            new_videos = json.load(f)
        
        existing_videos = load_json_data()
        max_id = 0
        if existing_videos:
            max_id = max([v.get('id', 0) for v in existing_videos])
        
        processed_videos = []
        existing_urls = [v.get('Shareable_Video_Link') for v in existing_videos]
        
        for video in new_videos:
            if video.get('Shareable_Video_Link') in existing_urls:
                continue
                
            if 'id' not in video:
                max_id += 1
                video['id'] = max_id
            
            processed_videos.append(video)
            existing_urls.append(video.get('Shareable_Video_Link'))
        
        combined_videos = existing_videos + processed_videos
        
        save_json_data(combined_videos)
        
        return jsonify({
            'success': True, 
            'message': f'Added {len(processed_videos)} new videos', 
            'total_videos': len(combined_videos),
            'videos': combined_videos
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error loading videos: {str(e)}'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)