// State management
let activeMode = 'text-to-video';
let uploadedImageFile = null;
let uploadedAudioFile = null;
let isGenerating = false;
let progressSource = null;
let activeVideoMetadata = null;
let currentTimerInterval = null;
let generationStartTime = 0;

// On Page Load
document.addEventListener('DOMContentLoaded', () => {
    loadGallery();
    checkExistingProgress();
    
    // Setup drag and drop for image/audio uploads
    setupDragAndDrop();
});

// Switch generator mode
function switchMode(mode) {
    if (isGenerating) return;
    
    activeMode = mode;
    
    // Update tabs UI
    document.getElementById('mode-t2v').classList.toggle('active', mode === 'text-to-video');
    document.getElementById('mode-i2v').classList.toggle('active', mode === 'image-to-video');
    
    // Update forms visibility
    document.getElementById('group-t2v').classList.toggle('active-group', mode === 'text-to-video');
    document.getElementById('group-i2v').classList.toggle('active-group', mode === 'image-to-video');
    
    // Adjust form requirements
    const promptInput = document.getElementById('prompt');
    if (mode === 'text-to-video') {
        promptInput.setAttribute('required', 'required');
    } else {
        promptInput.removeAttribute('required');
    }

    // Auto-adjust default guidance scale based on mode
    const guidanceInput = document.getElementById('guidance');
    const guidanceVal = document.getElementById('guidance-val');
    if (mode === 'image-to-video') {
        guidanceInput.value = 2.5;
        guidanceVal.innerText = '2.5';
    } else {
        guidanceInput.value = 7.5;
        guidanceVal.innerText = '7.5';
    }
}

// Toggle Advanced Settings Accordion
function toggleAdvancedSettings() {
    const box = document.getElementById('advanced-settings-box');
    const chevron = document.getElementById('advanced-chevron');
    
    box.classList.toggle('collapsed');
    
    if (box.classList.contains('collapsed')) {
        chevron.style.transform = 'rotate(0deg)';
    } else {
        chevron.style.transform = 'rotate(180deg)';
    }
}

// Drag and drop setup
function setupDragAndDrop() {
    const dropZone = document.getElementById('upload-zone');
    const audioZone = document.getElementById('audio-zone');
    
    // Image drag/drop
    if (dropZone) {
        ['dragenter', 'dragover'].forEach(eventName => {
            dropZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropZone.style.borderColor = 'var(--accent-pink)';
                dropZone.style.background = 'rgba(219, 39, 119, 0.03)';
            }, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropZone.style.borderColor = 'rgba(255, 255, 255, 0.1)';
                dropZone.style.background = 'rgba(0, 0, 0, 0.15)';
            }, false);
        });

        dropZone.addEventListener('drop', (e) => {
            const dt = e.dataTransfer;
            const files = dt.files;
            if (files.length > 0) {
                handleImageFile(files[0]);
            }
        });
    }

    // Audio drag/drop
    if (audioZone) {
        ['dragenter', 'dragover'].forEach(eventName => {
            audioZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
                audioZone.style.borderColor = 'var(--accent-purple)';
                audioZone.style.background = 'rgba(139, 92, 246, 0.03)';
            }, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            audioZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
                audioZone.style.borderColor = 'rgba(255, 255, 255, 0.1)';
                audioZone.style.background = 'rgba(0, 0, 0, 0.15)';
            }, false);
        });

        audioZone.addEventListener('drop', (e) => {
            const dt = e.dataTransfer;
            const files = dt.files;
            if (files.length > 0) {
                handleAudioFile(files[0]);
            }
        });
    }
}

function handleImageUpload(event) {
    const files = event.target.files;
    if (files.length > 0) {
        handleImageFile(files[0]);
    }
}

function handleImageFile(file) {
    if (!file.type.startsWith('image/')) {
        alert('Please upload an image file (PNG, JPG, JPEG).');
        return;
    }
    
    uploadedImageFile = file;
    
    const reader = new FileReader();
    reader.onload = function(e) {
        document.getElementById('upload-prompt').style.display = 'none';
        document.getElementById('upload-preview').src = e.target.result;
        document.getElementById('upload-preview-box').style.display = 'block';
    };
    reader.readAsDataURL(file);
}

function clearUploadedImage(event) {
    event.stopPropagation();
    uploadedImageFile = null;
    document.getElementById('image-input').value = '';
    document.getElementById('upload-preview-box').style.display = 'none';
    document.getElementById('upload-prompt').style.display = 'flex';
}

// Audio Upload Functions
function handleAudioUpload(event) {
    const files = event.target.files;
    if (files.length > 0) {
        handleAudioFile(files[0]);
    }
}

function handleAudioFile(file) {
    if (!file.type.startsWith('audio/') && !file.name.endsWith('.mp3') && !file.name.endsWith('.wav') && !file.name.endsWith('.m4a')) {
        alert('Please upload a valid audio file (MP3, WAV, M4A).');
        return;
    }
    
    uploadedAudioFile = file;
    document.getElementById('audio-filename').innerText = file.name;
    document.getElementById('audio-prompt').style.display = 'none';
    document.getElementById('audio-preview-box').style.display = 'flex';
}

function clearUploadedAudio(event) {
    if (event) {
        event.stopPropagation();
    }
    uploadedAudioFile = null;
    document.getElementById('audio-input').value = '';
    document.getElementById('audio-preview-box').style.display = 'none';
    document.getElementById('audio-prompt').style.display = 'flex';
}

// Generate execution
async function handleGenerate(event) {
    event.preventDefault();
    if (isGenerating) return;
    
    const formData = new FormData();
    formData.append('mode', activeMode);
    formData.append('num_frames', document.getElementById('frames').value);
    formData.append('steps', document.getElementById('steps').value);
    formData.append('guidance_scale', document.getElementById('guidance').value);
    formData.append('fps', document.getElementById('fps').value);
    formData.append('seed', document.getElementById('seed').value);
    
    if (activeMode === 'text-to-video') {
        const promptText = document.getElementById('prompt').value.trim();
        const modelSelect = document.getElementById('model-select');
        const selectedModelOption = modelSelect.options[modelSelect.selectedIndex];
        
        formData.append('prompt', promptText);
        formData.append('model_id', modelSelect.value);
        formData.append('model_name', selectedModelOption.getAttribute('data-name'));
    } else {
        if (!uploadedImageFile) {
            alert('Please upload an avatar image for Image-to-Video generation.');
            return;
        }
        formData.append('image', uploadedImageFile);
        formData.append('model_name', 'Stable Video Diffusion');
    }
    
    if (uploadedAudioFile) {
        formData.append('audio', uploadedAudioFile);
    }
    
    // Set UI to generating state
    setGeneratingState(true);
    
    try {
        const response = await fetch('/api/generate', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.detail || 'Failed to start generation');
        }
        
        // Connect to progress event stream
        listenToProgress();
        
    } catch (err) {
        alert('Error: ' + err.message);
        setGeneratingState(false);
    }
}

// Change UI components on generation state change
function setGeneratingState(generating) {
    isGenerating = generating;
    const generateBtn = document.getElementById('generate-btn');
    const renderPanel = document.getElementById('render-panel');
    
    if (generating) {
        generateBtn.setAttribute('disabled', 'disabled');
        generateBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Rendering Video...';
        renderPanel.style.display = 'block';
        
        // Scroll to rendering panel
        renderPanel.scrollIntoView({ behavior: 'smooth' });
        
        // Start client-side timer
        generationStartTime = Date.now();
        if (currentTimerInterval) clearInterval(currentTimerInterval);
        currentTimerInterval = setInterval(() => {
            const secs = ((Date.now() - generationStartTime) / 1000).toFixed(1);
            document.getElementById('elapsed-time').innerText = secs + 's';
        }, 100);
    } else {
        generateBtn.removeAttribute('disabled');
        generateBtn.innerHTML = '<i class="fa-solid fa-circle-play"></i> Generate Local Video';
        
        if (currentTimerInterval) {
            clearInterval(currentTimerInterval);
            currentTimerInterval = null;
        }
    }
}

// Connect to progress Server-Sent Events (SSE)
function listenToProgress() {
    if (progressSource) {
        progressSource.close();
    }
    
    progressSource = new EventSource('/api/progress');
    
    progressSource.onmessage = function(event) {
        const data = JSON.parse(event.data);
        updateProgressUI(data);
        
        if (data.status === 'done') {
            progressSource.close();
            setGeneratingState(false);
            
            // Highlight success, then clean UI and refresh gallery
            setTimeout(() => {
                document.getElementById('render-panel').style.display = 'none';
                loadGallery();
            }, 3000);
        } else if (data.status === 'error') {
            progressSource.close();
            setGeneratingState(false);
            
            // Keep error message on screen
            document.getElementById('progress-percent').innerHTML = '<i class="fa-solid fa-triangle-exclamation" style="color: var(--accent-red)"></i>';
            document.getElementById('status-text').innerText = 'Generation Failed';
            document.getElementById('log-message').innerText = 'Fatal Error: ' + data.error;
            document.getElementById('log-message').style.color = 'var(--accent-red)';
        }
    };
    
    progressSource.onerror = function() {
        progressSource.close();
    };
}

// Update progress stats in the UI
function updateProgressUI(data) {
    const progressBar = document.getElementById('progress-bar');
    const progressPercent = document.getElementById('progress-percent');
    const statusText = document.getElementById('status-text');
    const stepCount = document.getElementById('step-count');
    const etaTime = document.getElementById('eta-time');
    const logMessage = document.getElementById('log-message');
    
    const progress = data.progress || 0;
    progressBar.style.width = progress + '%';
    progressPercent.innerText = progress + '%';
    
    // Status text details
    if (data.status === 'loading_model') {
        statusText.innerText = 'Initializing';
        logMessage.innerText = 'Downloading / Loading model checkpoints into memory...';
        stepCount.innerText = '-- / --';
        etaTime.innerText = 'estimating...';
    } else if (data.status === 'generating') {
        statusText.innerText = 'Denoising';
        logMessage.innerText = `Performing Diffusion Steps on MPS device...`;
        stepCount.innerText = `${data.step} / ${data.total_steps}`;
        etaTime.innerText = data.eta > 0 ? data.eta + 's' : 'calculating...';
    } else if (data.status === 'saving') {
        statusText.innerText = 'Encoding';
        logMessage.innerText = 'Generating thumbnail and exporting frames to MP4 H.264...';
        stepCount.innerText = 'Complete';
        etaTime.innerText = '0.0s';
    } else if (data.status === 'done') {
        statusText.innerText = 'Ready!';
        logMessage.innerText = 'Video generated successfully!';
        logMessage.style.color = 'var(--accent-green)';
        stepCount.innerText = 'Saved';
        etaTime.innerText = '0.0s';
    }
}

// Resets API and UI in case of failure or lock
async function resetStateAfterFailure() {
    try {
        const response = await fetch('/api/reset-state', { method: 'POST' });
        if (response.ok) {
            document.getElementById('render-panel').style.display = 'none';
            setGeneratingState(false);
            loadGallery();
        } else {
            const data = await response.json();
            alert('Reset failed: ' + data.detail);
        }
    } catch (err) {
        alert('Reset failed: ' + err.message);
    }
}

// Checks if a job was running previously on backend
async function checkExistingProgress() {
    try {
        // Use EventSource directly to check if there is an active generation
        const recoverSource = new EventSource('/api/progress');
        recoverSource.onmessage = function(event) {
            const data = JSON.parse(event.data);
            if (data.status === 'loading_model' || data.status === 'generating' || data.status === 'saving') {
                setGeneratingState(true);
                // Switch back to listen
                recoverSource.close();
                listenToProgress();
            } else {
                recoverSource.close();
            }
        };
        recoverSource.onerror = function() {
            recoverSource.close();
        };
    } catch (e) {
        console.log("No ongoing generation found.");
    }
}

// Load Videos Grid
async function loadGallery() {
    const grid = document.getElementById('gallery-grid');
    const badge = document.getElementById('gallery-count');
    
    try {
        const response = await fetch('/api/videos');
        const videos = await response.json();
        
        badge.innerText = `${videos.length} video${videos.length === 1 ? '' : 's'}`;
        
        if (videos.length === 0) {
            grid.innerHTML = `
                <div class="gallery-empty-state">
                    <i class="fa-solid fa-film fa-3x"></i>
                    <p class="primary-text">No local videos generated yet</p>
                    <p class="secondary-text">Write a prompt or upload an image and click generate above!</p>
                </div>
            `;
            return;
        }
        
        let gridHtml = '';
        videos.forEach(vid => {
            const baseName = vid.filename.split('.')[0];
            const cleanPrompt = vid.prompt ? vid.prompt.replace(/"/g, '&quot;') : (vid.mode === 'image-to-video' ? 'Image-to-Video Animation' : 'Untitled');
            const modelLabel = vid.mode === 'image-to-video' ? 'Stable Video Diffusion' : vid.model.split('/').pop();
            
            gridHtml += `
                <div class="gallery-card" onclick="openLightbox(${JSON.stringify(vid).replace(/"/g, '&quot;')})">
                    <span class="card-badge">${vid.mode === 'image-to-video' ? 'Img2Vid' : 'Txt2Vid'}</span>
                    <span class="card-duration">${vid.duration}</span>
                    
                    <div class="card-media-wrapper">
                        <!-- Play Icon Hover -->
                        <div class="play-hover-overlay">
                            <i class="fa-solid fa-circle-play"></i>
                        </div>
                        <!-- Static Image Thumbnail -->
                        <img src="${vid.thumbnail_url}" alt="Thumbnail">
                        <!-- Loop Video for Hover Playing -->
                        <video src="${vid.video_url}" muted loop playsinline></video>
                    </div>
                    
                    <div class="card-details">
                        <p class="card-prompt">${cleanPrompt}</p>
                        <div class="card-meta-row">
                            <span class="card-date">${vid.created_at}</span>
                        </div>
                        <div class="card-actions">
                            <a href="${vid.video_url}" download class="card-btn" onclick="event.stopPropagation()">
                                <i class="fa-solid fa-download"></i> Download
                            </a>
                            <button class="card-btn delete-btn" onclick="event.stopPropagation(); deleteVideo('${vid.filename}')">
                                <i class="fa-solid fa-trash-can"></i> Delete
                            </button>
                        </div>
                    </div>
                </div>
            `;
        });
        
        grid.innerHTML = gridHtml;
        
        // Add hover play listeners to videos
        setupHoverToPlay();
        
    } catch (err) {
        grid.innerHTML = `
            <div class="gallery-empty-state">
                <i class="fa-solid fa-circle-exclamation fa-3x" style="color: var(--accent-red)"></i>
                <p class="primary-text" style="color: var(--accent-red)">Failed to load gallery</p>
                <p class="secondary-text">${err.message}</p>
            </div>
        `;
    }
}

// Play video on hover
function setupHoverToPlay() {
    const cards = document.querySelectorAll('.gallery-card');
    cards.forEach(card => {
        const video = card.querySelector('video');
        const img = card.querySelector('img');
        
        card.addEventListener('mouseenter', () => {
            if (video) {
                video.style.display = 'block';
                img.style.display = 'none';
                video.play().catch(e => console.log("Video hover autoplay blocked:", e));
            }
        });
        
        card.addEventListener('mouseleave', () => {
            if (video) {
                video.style.display = 'none';
                img.style.display = 'block';
                video.pause();
                video.currentTime = 0;
            }
        });
    });
}

// Delete video from gallery list
async function deleteVideo(filename) {
    if (!confirm('Are you sure you want to delete this generation? This action cannot be undone.')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/videos/${filename}`, {
            method: 'DELETE'
        });
        if (response.ok) {
            loadGallery();
        } else {
            const data = await response.json();
            alert('Failed to delete: ' + data.detail);
        }
    } catch (err) {
        alert('Error: ' + err.message);
    }
}

// Lightbox modal controls
function openLightbox(video) {
    activeVideoMetadata = video;
    
    const lightbox = document.getElementById('lightbox');
    const lightboxVideo = document.getElementById('lightbox-video');
    const metaPrompt = document.getElementById('meta-prompt');
    const metaModel = document.getElementById('meta-model');
    const metaMode = document.getElementById('meta-mode');
    const metaFramesFps = document.getElementById('meta-frames-fps');
    const metaGuidanceSteps = document.getElementById('meta-guidance-steps');
    const metaSeed = document.getElementById('meta-seed');
    const downloadBtn = document.getElementById('lightbox-download');
    
    // Set video src
    lightboxVideo.src = video.video_url;
    
    // Populating sidebar
    metaPrompt.innerText = video.prompt || (video.mode === 'image-to-video' ? 'Image-to-Video Animation' : 'Untitled prompt');
    metaModel.innerText = video.model;
    metaMode.innerText = video.mode === 'image-to-video' ? 'Image-to-Video (SVD)' : 'Text-to-Video (AnimateDiff)';
    metaFramesFps.innerText = `${video.frames} frames @ ${video.fps} FPS (${video.duration})`;
    metaGuidanceSteps.innerText = `${video.guidance_scale} scale / ${video.steps} steps`;
    metaSeed.innerText = video.seed;
    
    downloadBtn.href = video.video_url;
    downloadBtn.download = video.filename;
    
    lightbox.style.display = 'flex';
}

function closeLightbox() {
    const lightbox = document.getElementById('lightbox');
    const lightboxVideo = document.getElementById('lightbox-video');
    lightboxVideo.pause();
    lightboxVideo.src = '';
    lightbox.style.display = 'none';
    activeVideoMetadata = null;
}

// Delete video inside Lightbox modal
async function deleteVideoFromLightbox() {
    if (!activeVideoMetadata) return;
    
    const filename = activeVideoMetadata.filename;
    if (!confirm('Are you sure you want to delete this generation? This action cannot be undone.')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/videos/${filename}`, {
            method: 'DELETE'
        });
        if (response.ok) {
            closeLightbox();
            loadGallery();
        } else {
            const data = await response.json();
            alert('Failed to delete: ' + data.detail);
        }
    } catch (err) {
        alert('Error: ' + err.message);
    }
}

// Closes lightbox on outside click
window.addEventListener('click', (event) => {
    const lightbox = document.getElementById('lightbox');
    if (event.target === lightbox) {
        closeLightbox();
    }
});
