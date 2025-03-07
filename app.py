import os
import json
import subprocess
import yt_dlp
import shutil
import time
from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
import google.generativeai as genai
from google.generativeai import types


app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/videos'
app.config['PROCESSED_FOLDER'] = 'static/processed'
app.config['JSON_FILE'] = 'data/videos.json'
app.config['TEMP_FOLDER'] = 'static/temp'

for directory in [app.config['UPLOAD_FOLDER'], app.config['PROCESSED_FOLDER'], 'data', app.config['TEMP_FOLDER']]:
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



def cut_and_combine_video(input_path, output_path, segments, verbose=False):
    """Cuts multiple segments, combines them."""
    try:
        temp_dir = os.path.join(app.config['PROCESSED_FOLDER'], 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        file_list_path = os.path.join(temp_dir, 'file_list.txt')
        segment_files = []

        for i, segment in enumerate(segments):
            seg_output = os.path.join(temp_dir, f"segment_{i}.mp4")
            segment_files.append(seg_output)
            command = [
                'ffmpeg', '-i', input_path, '-ss', segment['start'],
                '-to', segment['end'], '-c:v', 'libx264', '-c:a', 'aac',
                '-strict', 'experimental', '-y', seg_output
            ]
            if verbose:
                print(f"Cutting segment {i+1}: {' '.join(command)}")
            result = subprocess.run(command, capture_output=True, text=True)
            if result.returncode != 0:
                error_message = (f"FFmpeg failed for segment {i+1}:\n"
                                 f"Return code: {result.returncode}\n"
                                 f"Stdout: {result.stdout}\nStderr: {result.stderr}")
                if verbose:
                    print(error_message)
                for file in segment_files:
                    if os.path.exists(file):
                        os.remove(file)
                return False, error_message

        with open(file_list_path, 'w') as f:
            for file in segment_files:
                f.write(f"file '{os.path.abspath(file)}'\n")

        concat_command = [
            'ffmpeg', '-f', 'concat', '-safe', '0', '-i', file_list_path,
            '-c', 'copy', '-y', output_path
        ]
        if verbose:
            print(f"Combining segments: {' '.join(concat_command)}")
        concat_result = subprocess.run(concat_command, capture_output=True, text=True)

        for file in segment_files:
            if os.path.exists(file):
                os.remove(file)
        if os.path.exists(file_list_path):
            os.remove(file_list_path)

        if concat_result.returncode != 0:
            error_message = (f"FFmpeg concat failed:\n"
                             f"Return code: {concat_result.returncode}\n"
                             f"Stdout: {concat_result.stdout}\nStderr: {concat_result.stderr}")
            if verbose:
                print(error_message)
            return False, error_message

        if verbose:
            print("Successfully cut and combined video segments.")
        return True, "Successfully cut and combined video segments."
    except Exception as e:
        return False, f"An error occurred: {e}"

def upload_video_to_gemini(file_path):
    """Uploads a video file to the Gemini File API and returns the file URI."""
    try:
        genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))
        client = genai.Client()
        print("Uploading file to Gemini...")
        video_file = client.files.upload(file=file_path)
        print(f"Completed upload: {video_file.uri}")

        while video_file.state.name == "PROCESSING":
            print('.', end='')
            time.sleep(1)
            video_file = client.files.get(name=video_file.name)

        if video_file.state.name == "FAILED":
            raise ValueError(video_file.state.name)

        print('Done')
        return video_file
    except Exception as e:
        print(f"Error uploading video to Gemini: {e}")
        return None

def generate_gemini_response(video_0_uri, video_1_uri, prompt):
    """Generates response using Gemini model with file URIs and types."""
    try:
        genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))
        client = genai.Client()
        model = genai.GenerativeModel('gemini-2.0-pro-exp-02-05')

        video_0_file = client.files.get(name=video_0_uri.split('/')[-1])
        video_1_file = client.files.get(name=video_1_uri.split('/')[-1])
      
        contents = [
              types.Content(
                  role="user",
                  parts=[
                      types.Part.from_uri(
                          file_uri=video_0_file.uri,
                          mime_type=video_0_file.mime_type,
                      ),
                      types.Part.from_uri(
                          file_uri=video_1_file.uri,
                          mime_type=video_1_file.mime_type,
                      ),
                  ],
              ),
              types.Content(
                  role="user",
                  parts=[
                    types.Part.from_text(text=prompt)
                  ]
              )

          ]


        response = model.generate_content(contents=contents)
        return response.text
    except Exception as e:
        print(f"Error in Gemini response generation: {e}")
        return f"Error generating response: {e}"


@app.route('/')
def index():
    """Renders the main page of the application."""
    videos = load_json_data()
    return render_template('index.html', videos=videos)

@app.route('/download', methods=['POST'])
def download_video_route():
    """API endpoint to download a video."""
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
    segments = data.get('segments', [])
    narrative = data.get('narrative')

    if 'startTime' in data and 'endTime' in data:
        segments.append({
            'start': data.get('startTime'),
            'end': data.get('endTime')
        })

    if not segments:
        return jsonify({'success': False, 'message': 'No time segments provided'})

    for segment in segments:
        if not validate_time_format(segment['start']) or not validate_time_format(segment['end']):
            return jsonify({'success': False, 'message': 'Invalid time format. Use HH:MM:SS or MM:SS'})

    videos = load_json_data()
    video = next((v for v in videos if v.get('id') == video_id), None)

    if not video or not video.get('local_path'):
        return jsonify({'success': False, 'message': 'Video not found or not downloaded'})

    input_path = video.get('local_path')
    output_filename = f"cut_{video_id}_{segments[0]['start'].replace(':', '')}_{segments[-1]['end'].replace(':', '')}.mp4"
    if len(segments) > 1:
        output_filename = f"combined_{video_id}_{len(segments)}_segments.mp4"
    output_path = os.path.join(app.config['PROCESSED_FOLDER'], output_filename)

    if len(segments) == 1:
        success, message = cut_video(input_path, output_path, segments[0]['start'], segments[0]['end'], verbose=True)
    else:
        success, message = cut_and_combine_video(input_path, output_path, segments, verbose=True)

    if success:
        if 'cuts' not in video:
            video['cuts'] = []

        video['cuts'].append({
            'id': len(video.get('cuts', [])) + 1,
            'segments': segments,
            'narrative': narrative,
            'output_path': output_path,
            'filename': output_filename,
            'out_of_context_prompt': '',
            'out_of_context_answer': '',
            'in_context_prompt': '',
            'in_context_answer': ''
        })

        save_json_data(videos)
        return jsonify({'success': True, 'message': message, 'filename': output_filename})
    else:
        return jsonify({'success': False, 'message': message})



@app.route('/process_context', methods=['POST'])
def process_context():
    """Processes a cut for context using Gemini."""
    data = request.get_json()
    video_id = data.get('video_id')
    cut_id = data.get('cut_id')
    context_type = data.get('context_type')

    videos = load_json_data()
    video = next((v for v in videos if v.get('id') == video_id), None)
    if not video:
        return jsonify({'success': False, 'message': 'Video not found'})

    cut = next((c for c in video.get('cuts', []) if c.get('id') == cut_id), None)
    if not cut:
        return jsonify({'success': False, 'message': 'Cut not found'})

    cut_video_path = cut['output_path']
    original_video_path = video['local_path']
    temp_video_0_path = os.path.join(app.config['TEMP_FOLDER'], "video_0.mp4")
    temp_video_1_path = os.path.join(app.config['TEMP_FOLDER'], "video_1.mp4")

    shutil.copy(cut_video_path, temp_video_0_path)
    shutil.copy(original_video_path, temp_video_1_path)

    narrative = cut['narrative']
    if context_type == 'out':
        prompt = (f"video_1.mp4: context\n"
                  f"The message of video_0.mp4 is \"{narrative}\"\n"
                  f"Is video_0.mp4 out-of-context?")
    elif context_type == 'in':
        prompt = (f"video_1.mp4: context\n"
                  f"The message of video_0.mp4 is \"{narrative}\"\n"
                  f"Is video_0.mp4 in-context?")
    else:
        return jsonify({'success': False, 'message': 'Invalid context_type'})

    # Upload videos to Gemini File API and get URIs
    video_0_file = upload_video_to_gemini(temp_video_0_path)
    video_1_file = upload_video_to_gemini(temp_video_1_path)

    if not video_0_file or not video_1_file:
        return jsonify({'success': False, 'message': 'Failed to upload videos to Gemini'})

    video_0_uri = video_0_file.uri
    video_1_uri = video_1_file.uri

    response_text = generate_gemini_response(video_0_uri, video_1_uri, prompt)

    for v in videos:
        if v.get('id') == video_id:
            for c in v.get('cuts', []):
                if c.get('id') == cut_id:
                    if context_type == 'out':
                        c['out_of_context_prompt'] = prompt
                        c['out_of_context_answer'] = response_text
                    else:
                        c['in_context_prompt'] = prompt
                        c['in_context_answer'] = response_text
                    break  
            break 
    save_json_data(videos)


    return jsonify({'success': True, 'message': 'Context processed', 'response': response_text})

@app.route('/static/<path:path>')
def serve_static(path):
    """Serves static files."""
    return send_from_directory('static', path)

@app.route('/load_videos', methods=['POST'])
def load_videos():
    """API endpoint to load videos from a JSON."""
    try:
        file = request.files.get('json_file')
        if not file:
            return jsonify({'success': False, 'message': 'No file provided'})

        filename = secure_filename(file.filename)
        if not filename.endswith('.json'):
            return jsonify({'success': False, 'message': 'Must be a JSON file'})

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
        return jsonify({'success': False, 'message': f'Error loading: {str(e)}'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)