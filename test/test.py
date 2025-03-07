from google import genai
import time
from . import config

client = genai.Client(api_key=config.GOOGLE_API_KEY)

print("Uploading file...")
video_file = client.files.upload(file="GreatRedSpot.mp4")
video_file2 = client.files.upload(file="testfile.mp4")

print(f"Completed upload: {video_file.uri}")


# Check whether the file is ready to be used.
while video_file.state.name == "PROCESSING":
    print('.', end='')
    time.sleep(1)
    video_file = client.files.get(name=video_file.name)

if video_file.state.name == "FAILED":
  raise ValueError(video_file.state.name)

print('Done')

while video_file2.state.name == "PROCESSING":
    print('.', end='')
    time.sleep(1)
    video_file2 = client.files.get(name=video_file2.name)

if video_file2.state.name == "FAILED":
  raise ValueError(video_file2.state.name)

print('Done')


response = client.models.generate_content(
    model="gemini-1.5-pro",
    contents=[
        video_file, video_file2,
        "are these two videos the same?"])

print(response.text)