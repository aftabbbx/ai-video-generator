import os
import sys
import torch
import inspect
from PIL import Image
from diffusers import (
    AnimateDiffPipeline, 
    MotionAdapter, 
    DDIMScheduler,
    StableVideoDiffusionPipeline
)

class VideoGenerator:
    def __init__(self):
        self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        # If MPS is not available, check if CUDA is (for portability, though this is mac-first)
        if self.device == "cpu" and torch.cuda.is_available():
            self.device = "cuda"
        
        print(f"[*] VividFlow Generator initialized. Using device: {self.device}")
        
        # Keep track of loaded models to avoid reloading
        self.current_t2v_model_id = None
        self.current_t2v_pipe = None
        
        self.current_svd_pipe = None

    def _setup_progress_callback(self, pipe, steps, progress_callback, kwargs):
        """
        Dynamically inspects the pipeline signature and adds the appropriate progress callback.
        """
        if not progress_callback:
            return kwargs
            
        sig = inspect.signature(pipe.__call__)
        
        if "callback_on_step_end" in sig.parameters:
            def step_end_callback(pipeline, step, timestep, callback_kwargs):
                progress_callback(step + 1, steps)
                return callback_kwargs
            kwargs["callback_on_step_end"] = step_end_callback
        elif "callback" in sig.parameters:
            def step_callback(step, timestep, latents):
                progress_callback(step + 1, steps)
            kwargs["callback"] = step_callback
            kwargs["callback_steps"] = 1
            
        return kwargs

    def get_text_to_video_pipeline(self, model_id):
        """
        Loads and caches the AnimateDiff pipeline with the requested base model.
        """
        # If model is already loaded, reuse it
        if self.current_t2v_model_id == model_id and self.current_t2v_pipe is not None:
            return self.current_t2v_pipe

        print(f"[*] Loading Text-to-Video Pipeline (AnimateDiff) with base model: {model_id}...")
        
        # Load motion adapter
        motion_adapter_id = "guoyww/animatediff-motion-adapter-v1-5-2"
        print(f"[*] Loading Motion Adapter: {motion_adapter_id}...")
        adapter = MotionAdapter.from_pretrained(
            motion_adapter_id, 
            torch_dtype=torch.float16 if self.device != "cpu" else torch.float32
        )
        
        # Load pipeline
        print(f"[*] Loading Base Model: {model_id}...")
        pipe = AnimateDiffPipeline.from_pretrained(
            model_id,
            motion_adapter=adapter,
            torch_dtype=torch.float16 if self.device != "cpu" else torch.float32
        )
        
        # Setup scheduler
        pipe.scheduler = DDIMScheduler.from_config(
            pipe.scheduler.config,
            beta_schedule="linear",
            clip_sample=False,
            timestep_spacing="linspace",
            steps_offset=1
        )
        
        # Move to device
        pipe = pipe.to(self.device)
        
        # Disable SDPA on MPS to prevent Metal 4GB allocation crashes
        # if self.device == "mps":
        #     try:
        #         pipe.unet.set_default_attn_processor()
        #     except Exception as e:
        #         print(f"[!] Failed to set default attention processor: {e}")
        
        # Memory-saving optimizations for M2 8GB Mac
        pipe.enable_attention_slicing()
        pipe.enable_vae_slicing()
        
        # Optional: enable CPU offload to save even more memory (can be slower)
        try:
            if self.device == "cuda":
                pipe.enable_model_cpu_offload()
        except Exception as e:
            print(f"[!] CPU offload failed to enable: {e}")

        self.current_t2v_model_id = model_id
        self.current_t2v_pipe = pipe
        
        # Clear SVD model from memory to save RAM on 8GB machine
        if self.current_svd_pipe is not None:
            del self.current_svd_pipe
            self.current_svd_pipe = None
            if self.device == "mps":
                torch.mps.empty_cache()
                
        return pipe

    def get_image_to_video_pipeline(self):
        """
        Loads and caches the Stable Video Diffusion pipeline.
        """
        if self.current_svd_pipe is not None:
            return self.current_svd_pipe

        print("[*] Loading Image-to-Video Pipeline (Stable Video Diffusion)...")
        model_id = "stabilityai/stable-video-diffusion-img2vid-xt"
        
        pipe = StableVideoDiffusionPipeline.from_pretrained(
            model_id,
            torch_dtype=torch.float16 if self.device != "cpu" else torch.float32,
            variant="fp16" if self.device != "cpu" else None
        )
        
        pipe = pipe.to(self.device)
        
        # Disable SDPA on MPS to prevent Metal 4GB allocation crashes
        # if self.device == "mps":
        #     try:
        #         pipe.unet.set_default_attn_processor()
        #     except Exception as e:
        #         print(f"[!] Failed to set default attention processor: {e}")
        
        # Memory-saving optimizations for M2 8GB Mac
        pipe.enable_attention_slicing()
        pipe.enable_vae_slicing()
        
        try:
            # SVD is very large, CPU offload helps prevent crashes on 8GB RAM
            if self.device == "mps":
                # For macOS, sequential CPU offloading works better sometimes, try standard first
                pipe.enable_model_cpu_offload()
            elif self.device == "cuda":
                pipe.enable_model_cpu_offload()
        except Exception as e:
            print(f"[!] SVD CPU offload failed to enable: {e}")

        self.current_svd_pipe = pipe
        
        # Clear T2V model from memory to save RAM
        if self.current_t2v_pipe is not None:
            del self.current_t2v_pipe
            self.current_t2v_pipe = None
            self.current_t2v_model_id = None
            if self.device == "mps":
                torch.mps.empty_cache()
                
        return pipe

    def generate_text_to_video(self, prompt, model_id, num_frames=16, steps=20, guidance_scale=7.5, seed=None, height=512, width=512, device=None, progress_callback=None):
        """
        Generates frames from a text prompt using AnimateDiff.
        """
        if device and device != self.device:
            print(f"[*] Switching generator device from {self.device} to {device}...")
            self.device = device
            self.current_t2v_pipe = None
            self.current_t2v_model_id = None
            self.current_svd_pipe = None
            if self.device == "mps" and hasattr(torch, "mps"):
                torch.mps.empty_cache()

        pipe = self.get_text_to_video_pipeline(model_id)
        
        generator = None
        if seed is not None and seed >= 0:
            generator = torch.Generator(device=self.device).manual_seed(seed)
        
        # Prepare pipeline call args
        kwargs = {
            "prompt": prompt,
            "negative_prompt": "bad quality, worse quality, low quality, blurry, deformed, distorted, static, jittery",
            "num_frames": num_frames,
            "num_inference_steps": steps,
            "guidance_scale": guidance_scale,
            "generator": generator,
            "height": height,
            "width": width,
        }
        
        # Bind the progress callback
        kwargs = self._setup_progress_callback(pipe, steps, progress_callback, kwargs)
        
        print(f"[*] Running Text-to-Video generation (steps={steps}, frames={num_frames})...")
        with torch.no_grad():
            output = pipe(**kwargs)
            
        # AnimateDiff returns a list of frames
        return output.frames[0]

    def generate_image_to_video(self, image_path, num_frames=14, steps=20, guidance_scale=2.5, seed=None, height=512, width=512, device=None, progress_callback=None):
        """
        Generates frames from an input image using Stable Video Diffusion.
        """
        if device and device != self.device:
            print(f"[*] Switching generator device from {self.device} to {device}...")
            self.device = device
            self.current_t2v_pipe = None
            self.current_t2v_model_id = None
            self.current_svd_pipe = None
            if self.device == "mps" and hasattr(torch, "mps"):
                torch.mps.empty_cache()

        pipe = self.get_image_to_video_pipeline()
        
        # Load and resize image to standard SVD dimensions (1024x576 or 512x512)
        # SVD is trained on 1024x576, but 512x512 is much faster and uses far less memory
        image = Image.open(image_path).convert("RGB")
        image = image.resize((width, height)) # Resize based on selected resolution
        
        generator = None
        if seed is not None and seed >= 0:
            generator = torch.Generator(device=self.device).manual_seed(seed)
            
        kwargs = {
            "image": image,
            "num_frames": num_frames,
            "num_inference_steps": steps,
            "min_guidance_scale": guidance_scale,
            "max_guidance_scale": guidance_scale,
            "decode_chunk_size": 2, # Process 2 frames at a time in VAE decoder to avoid OOM
            "generator": generator
        }
        
        kwargs = self._setup_progress_callback(pipe, steps, progress_callback, kwargs)
        
        print(f"[*] Running Image-to-Video generation (steps={steps}, frames={num_frames})...")
        with torch.no_grad():
            output = pipe(**kwargs)
            
        return output.frames[0]

if __name__ == "__main__":
    # Test script entry point
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        print("[*] Running local generation test...")
        generator = VideoGenerator()
        
        # Test Text-to-Video with extremely light settings: 2 steps, 8 frames
        # Use tiny base model to test pipeline creation
        test_prompt = "cartoon cat waving"
        test_model = "frankjoshua/toonyou_beta6"
        
        def test_callback(step, total):
            print(f"    -> Progress: Step {step}/{total}")
            
        try:
            print("[*] Generating test video (this verifies device setup and downloading)...")
            frames = generator.generate_text_to_video(
                prompt=test_prompt,
                model_id=test_model,
                num_frames=8,
                steps=2,
                guidance_scale=5.0,
                seed=42,
                height=256,
                width=256,
                progress_callback=test_callback
            )
            print(f"[+] Success! Generated {len(frames)} test frames.")
            
            # Save test video
            from utils import save_video, save_thumbnail
            os.makedirs("generations", exist_ok=True)
            save_video(frames, "generations/test_output.mp4", fps=4)
            save_thumbnail(frames, "generations/test_output.png")
            print("[+] Saved test_output.mp4 and test_output.png in generations/")
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[!] Test generation failed: {e}")
            sys.exit(1)
