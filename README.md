# Misinformation Video Editor Demo

This web application allows you to download, process, and cut videos from external sources on your local machine. The app runs on a Flask server and provides a simple interface for working with videos.

Part of an ongoing project by [Yoo-Yeon Song](https://yysung.github.io/) and [Atrey Desai](https://atreydesai.github.io/) at the University of Maryland.

## Features

- Load video metadata from JSON files
- Download videos from external sources using yt-dlp
- Add narrative descriptions to videos
- Cut videos to specific time ranges
- Preview original and cut videos

## Requirements

- Python 3.6+
- Flask
- yt-dlp
- ffmpeg

## Installation

1. Clone this repository or download the files

2. Install the required Python packages:
```bash
pip install flask yt-dlp
```

3. Install ffmpeg:
   - On macOS: `brew install ffmpeg` or if in conda environment `conda install -c conda-forge ffmpeg`
   - On Ubuntu/Debian: `sudo apt-get install ffmpeg` ***Current Not Valided :(***
   - On Windows: Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to PATH ***Current Not Valided :(***

## Usage

1. Start the server:
```bash
python app.py
```
*Note: If you get an error and server fails to start, it may be because of existing processes using port 5000. Go to ***Notes*** below for solution*

2. Open your browser and navigate to `http://localhost:5000`

3. Upload a JSON file with video information in the format:
```json
[
  {
    "Headline": "Video Title",
    "Shareable_Video_Link": "https://example.com/video-url"
  }
]
```

4. For each video:
   - Download the video by clicking the "Download Video" button
   - Add a narrative in the text box
   - Specify start and end times in the format HH:MM:SS or MM:SS
   - Click "Cut Video" to process the video
   - View the cut video in the preview section

## Directory Structure

- `/static/videos` - Original downloaded videos
- `/static/processed` - Cut video segments
- `/data` - JSON files with video metadata
- `/templates` - HTML templates

## Error Handling

The application provides feedback for various error conditions:
- Invalid time formats
- Failed downloads
- Failed video cutting
- Missing ffmpeg installation

## Notes

- Videos with a duration longer than 10 minutes will not be downloaded
- The application supports many video hosting platforms through yt-dlp, though some videos may fail to download (particularly those from Facebook Videos and Instagram Reels)
- Port 5000 may be occupied by current processes on Macs due to Universal Control. Go to *System Settings > General > AirDrop & Handoff > Turn off ***Allow Handoff between this Mac and your iCloud devices*** and  ***AirPlay Receiver****
- You can also check if Port 5000 is empty using `lsof -i :5000` on Mac/Linux and `netstat -ano | findstr :5000` on Windows

## Known Issues

- Although all videos in a JSON can be loaded in at the same time, downloading multiple videos concurrently will lead to only the most recent downloaded video having a local path. This can cause issues when creating clips from source videos. This can be mitigated by downloading one source video at a time, or reloading the page and clicking download on the source video again. 