import os
import time
import asyncio
import random
import threading
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks, Form, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import json

from backend.generator import VideoGenerator
from backend.utils import save_video, save_thumbnail, save_metadata, get_all_videos, merge_video_audio

# Initialize FastAPI app
app = FastAPI(title="VividFlow API")

# Add CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup directories relative to the workspace
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATIONS_DIR = os.path.join(BASE_DIR, "generations")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")

os.makedirs(GENERATIONS_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)

# Initialize global generator lazily when first needed to speed up API start
generator_instance = None
generator_lock = threading.Lock()

def get_generator():
    global generator_instance
    with generator_lock:
        if generator_instance is None:
            generator_instance = VideoGenerator()
        return generator_instance

# Global progress state
progress_state = {
    "status": "idle",  # idle, loading_model, generating, saving, done, error
    "step": 0,
    "total_steps": 0,
    "progress": 0,
    "error": None,
    "elapsed": 0.0,
    "eta": 0.0,
    "filename": None
}

state_lock = threading.RLock()

def update_state(**kwargs):
    with state_lock:
        for k, v in kwargs.items():
            progress_state[k] = v

def run_generation(params):
    try:
        update_state(
            status="loading_model",
            step=0,
            total_steps=params["steps"],
            progress=0,
            error=None,
            filename=None,
            elapsed=0.0,
            eta=0.0
        )
        
        # Instantiate/get generator
        gen = get_generator()
        
        # Generate seed if random
        actual_seed = params["seed"]
        if actual_seed is None or actual_seed < 0:
            actual_seed = random.randint(0, 2**30)
            params["seed"] = actual_seed

        start_time = time.time()
        
        def progress_cb(step, total):
            elapsed = time.time() - start_time
            # Keep progress in 0-99 range during generation, 100 on completion
            progress_percent = min(int((step / total) * 98), 99)
            eta = (elapsed / step) * (total - step) if step > 0 else 0.0
            
            update_state(
                status="generating",
                step=step,
                total_steps=total,
                progress=progress_percent,
                elapsed=round(elapsed, 1),
                eta=round(eta, 1)
            )

        if params["mode"] == "text-to-video":
            frames = gen.generate_text_to_video(
                prompt=params["prompt"],
                model_id=params["model_id"],
                num_frames=params["num_frames"],
                steps=params["steps"],
                guidance_scale=params["guidance_scale"],
                seed=params["seed"],
                progress_callback=progress_cb
            )
        else:  # image-to-video
            frames = gen.generate_image_to_video(
                image_path=params["image_path"],
                num_frames=params["num_frames"],
                steps=params["steps"],
                guidance_scale=params["guidance_scale"],
                seed=params["seed"],
                progress_callback=progress_cb
            )
            
        update_state(status="saving", progress=99)
        
        # Save video file
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_filename = f"vividflow_{timestamp_str}"
        video_filename = f"{base_filename}.mp4"
        video_path = os.path.join(GENERATIONS_DIR, video_filename)
        thumbnail_path = os.path.join(GENERATIONS_DIR, f"{base_filename}.png")
        metadata_path = os.path.join(GENERATIONS_DIR, f"{base_filename}.json")
        
        # Save static thumbnail
        save_thumbnail(frames, thumbnail_path)

        # Write frames to video mp4 (and merge audio if provided)
        audio_path = params.get("audio_path")
        if audio_path and os.path.exists(audio_path):
            temp_video_filename = f"temp_{video_filename}"
            temp_video_path = os.path.join(GENERATIONS_DIR, temp_video_filename)
            try:
                # Write silent video first
                save_video(frames, temp_video_path, fps=params["fps"])
                # Merge with audio, looping the video to match audio length
                merge_video_audio(temp_video_path, audio_path, video_path)
            finally:
                if os.path.exists(temp_video_path):
                    os.remove(temp_video_path)
        else:
            save_video(frames, video_path, fps=params["fps"])
        
        # Save generation settings
        metadata = {
            "prompt": params.get("prompt", ""),
            "model": params.get("model_name", "Stable Video Diffusion" if params["mode"] == "image-to-video" else params["model_id"]),
            "mode": params["mode"],
            "steps": params["steps"],
            "frames": params["num_frames"],
            "fps": params["fps"],
            "guidance_scale": params["guidance_scale"],
            "seed": params["seed"],
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        save_metadata(metadata_path, metadata)
        
        update_state(
            status="done",
            filename=video_filename,
            progress=100,
            elapsed=round(time.time() - start_time, 1)
        )
        print(f"[*] Successfully generated and saved {video_filename}")
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        update_state(status="error", error=str(e))

# API Routes

@app.post("/api/generate")
async def generate_video(
    background_tasks: BackgroundTasks,
    mode: str = Form(...),
    prompt: Optional[str] = Form(None),
    model_id: Optional[str] = Form("frankjoshua/toonyou_beta6"),
    model_name: Optional[str] = Form("ToonYou (SD 1.5)"),
    num_frames: int = Form(16),
    steps: int = Form(20),
    guidance_scale: float = Form(7.5),
    fps: int = Form(8),
    seed: int = Form(-1),
    image: Optional[UploadFile] = File(None),
    audio: Optional[UploadFile] = File(None)
):
    global progress_state
    
    with state_lock:
        if progress_state["status"] in ["loading_model", "generating", "saving"]:
            raise HTTPException(status_code=400, detail="A video is already generating. Please wait.")
            
    params = {
        "mode": mode,
        "prompt": prompt,
        "model_id": model_id,
        "model_name": model_name,
        "num_frames": num_frames,
        "steps": steps,
        "guidance_scale": guidance_scale,
        "fps": fps,
        "seed": seed,
    }
    
    # Save uploaded voiceover audio file if present
    if audio and audio.filename:
        audio_filename = f"audio_{int(time.time())}_{audio.filename}"
        audio_path = os.path.join(UPLOADS_DIR, audio_filename)
        with open(audio_path, "wb") as f:
            content = await audio.read()
            f.write(content)
        params["audio_path"] = audio_path
    else:
        params["audio_path"] = None

    if mode == "image-to-video":
        if not image:
            raise HTTPException(status_code=400, detail="An image is required for Image-to-Video mode.")
        
        # Save uploaded image locally
        upload_filename = f"upload_{int(time.time())}_{image.filename}"
        image_path = os.path.join(UPLOADS_DIR, upload_filename)
        with open(image_path, "wb") as f:
            content = await image.read()
            f.write(content)
        params["image_path"] = image_path
    else:
        if not prompt or not prompt.strip():
            raise HTTPException(status_code=400, detail="A prompt is required for Text-to-Video mode.")
            
    # Trigger background thread for GPU generation
    threading.Thread(target=run_generation, args=(params,), daemon=True).start()
    
    return {"message": "Generation started", "status": "started"}

@app.get("/api/progress")
async def get_progress():
    """
    Streams the generation progress using Server-Sent Events (SSE).
    """
    async def event_generator():
        last_yield_state = None
        while True:
            # Safe copy of state
            with state_lock:
                current = dict(progress_state)
            
            # Format SSE payload
            payload = json.dumps(current)
            yield f"data: {payload}\n\n"
            
            # If the job has completed, errored out, or returned to idle, stop sending
            if current["status"] in ["done", "error", "idle"]:
                break
                
            await asyncio.sleep(0.5)
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/api/reset-state")
def reset_state():
    """
    Resets the progress state to idle.
    """
    with state_lock:
        if progress_state["status"] not in ["loading_model", "generating", "saving"]:
            for k, v in {
                "status": "idle", "step": 0, "total_steps": 0, "progress": 0, 
                "error": None, "filename": None, "elapsed": 0.0, "eta": 0.0
            }.items():
                progress_state[k] = v
            return {"status": "reset"}
        else:
            raise HTTPException(status_code=400, detail="Cannot reset while generating.")

@app.get("/api/videos")
def list_videos():
    """
    List all generated videos with their metadata.
    """
    return get_all_videos(GENERATIONS_DIR)

@app.delete("/api/videos/{filename}")
def delete_video(filename: str):
    """
    Deletes the video, thumbnail, and metadata json file.
    """
    base_name = os.path.splitext(filename)[0]
    
    video_path = os.path.join(GENERATIONS_DIR, filename)
    thumbnail_path = os.path.join(GENERATIONS_DIR, f"{base_name}.png")
    metadata_path = os.path.join(GENERATIONS_DIR, f"{base_name}.json")
    
    deleted_any = False
    for path in [video_path, thumbnail_path, metadata_path]:
        if os.path.exists(path):
            os.remove(path)
            deleted_any = True
            
    if not deleted_any:
        raise HTTPException(status_code=404, detail="Video files not found.")
        
    return {"message": f"Successfully deleted {filename}"}

# Serve static folders
# Serve generations (videos & thumbnails) under /api/videos
app.mount("/api/videos", StaticFiles(directory=GENERATIONS_DIR), name="generations_static")

# Mount frontend directory for index.html / css / js at the root
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
os.makedirs(FRONTEND_DIR, exist_ok=True)
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend_static")
