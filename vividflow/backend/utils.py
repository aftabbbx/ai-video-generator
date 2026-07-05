import os
import json
import time
import subprocess
from datetime import datetime
from PIL import Image
import imageio
import imageio_ffmpeg

def save_video(frames, video_path, fps=8):
    """
    Saves a list of PIL images or numpy arrays as an MP4 video using imageio.
    """
    # Convert PIL Images to numpy arrays if necessary
    processed_frames = []
    for f in frames:
        if isinstance(f, Image.Image):
            import numpy as np
            processed_frames.append(np.array(f))
        else:
            processed_frames.append(f)
            
    # Write video using FFMPEG format provided by imageio-ffmpeg
    imageio.mimsave(video_path, processed_frames, fps=fps, format="FFMPEG", codec="libx264")

def save_thumbnail(frames, thumbnail_path):
    """
    Saves the first frame of the generated frames as a PNG thumbnail.
    """
    if not frames:
        return
        
    first_frame = frames[0]
    if not isinstance(first_frame, Image.Image):
        # Convert numpy array to PIL Image
        first_frame = Image.fromarray(first_frame)
        
    # Crop or resize to make a neat thumbnail (e.g., maximum width/height of 320px)
    first_frame.thumbnail((320, 320))
    first_frame.save(thumbnail_path, "PNG")

def save_metadata(metadata_path, metadata):
    """
    Saves metadata about the generation to a JSON file.
    """
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=4)

def get_all_videos(generations_dir):
    """
    Scans the generations directory and returns a sorted list of videos with metadata.
    """
    if not os.path.exists(generations_dir):
        os.makedirs(generations_dir)
        return []
        
    videos = []
    for filename in os.listdir(generations_dir):
        if filename.endswith(".mp4"):
            base_name = os.path.splitext(filename)[0]
            video_path = os.path.join(generations_dir, filename)
            metadata_path = os.path.join(generations_dir, f"{base_name}.json")
            thumbnail_path = os.path.join(generations_dir, f"{base_name}.png")
            
            # Load metadata if exists
            metadata = {}
            if os.path.exists(metadata_path):
                try:
                    with open(metadata_path, 'r') as f:
                        metadata = json.load(f)
                except Exception as e:
                    print(f"Error reading metadata for {filename}: {e}")
            
            # Use file modified time as fallback for creation time
            mtime = os.path.getmtime(video_path)
            created_at = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
            
            videos.append({
                "filename": filename,
                "created_at": metadata.get("timestamp", created_at),
                "prompt": metadata.get("prompt", ""),
                "model": metadata.get("model", "Unknown"),
                "mode": metadata.get("mode", "text-to-video"),
                "steps": metadata.get("steps", 0),
                "frames": metadata.get("frames", 0),
                "fps": metadata.get("fps", 8),
                "guidance_scale": metadata.get("guidance_scale", 7.5),
                "seed": metadata.get("seed", -1),
                "duration": f"{metadata.get('frames', 16) / metadata.get('fps', 8):.1f}s",
                "has_thumbnail": os.path.exists(thumbnail_path),
                "thumbnail_url": f"/api/videos/{base_name}.png",
                "video_url": f"/api/videos/{filename}"
            })
            
    # Sort by creation time descending (newest first)
    videos.sort(key=lambda x: x["created_at"], reverse=True)
    return videos

def merge_video_audio(video_path, audio_path, output_path):
    """
    Merges a silent video and an audio file into a single video.
    Loops the video to match the audio duration.
    """
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    
    # Run FFmpeg command to loop the video input and stitch it with the audio input,
    # stopping when the shortest input (the audio, since the video loops infinitely) finishes.
    cmd = [
        ffmpeg_exe,
        "-stream_loop", "-1",
        "-i", video_path,
        "-i", audio_path,
        "-shortest",
        "-c:v", "libx264",
        "-c:a", "aac",
        "-pix_fmt", "yuv420p",
        "-y",
        output_path
    ]
    
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg merge failed: {result.stderr.decode('utf-8', errors='ignore')}")
