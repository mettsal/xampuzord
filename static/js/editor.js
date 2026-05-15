// static/js/editor-enhanced.js
document.addEventListener('DOMContentLoaded', function() {
    const postBody = document.getElementById('postBody');
    const postTitle = document.getElementById('postTitle');
    const tagInput = document.getElementById('tagInput');
    const fontSelector = document.getElementById('fontSelector');
    const themeSelector = document.getElementById('themeSelector');
    const togglePreview = document.getElementById('togglePreview');
    const previewPanel = document.getElementById('previewPanel');
    const previewContent = document.getElementById('previewContent');
    const postForm = document.getElementById('postForm');
    
    // Teaser upload elements
    const teaserType = document.getElementById('teaserType');
    const imageUploadSection = document.getElementById('imageUploadSection');
    const uploadArea = document.getElementById('uploadArea');
    const teaserImageInput = document.getElementById('teaserImageInput');
    const uploadText = document.getElementById('uploadText');
    const uploadProgress = document.getElementById('uploadProgress');
    const imagePreview = document.getElementById('imagePreview');
    const previewImg = document.getElementById('previewImg');
    const removeImage = document.getElementById('removeImage');
    const teaserImagePath = document.getElementById('teaserImagePath');
    
    // =============  TEASER FUNCTIONALITY  =============
    
    // Show/hide image upload section based on teaser type
    if (teaserType && imageUploadSection) {
        teaserType.addEventListener('change', () => {
            if (teaserType.value === 'image') {
                imageUploadSection.style.display = 'block';
            } else {
                imageUploadSection.style.display = 'none';
            }
        });
    }
    
    // File upload handling
    if (uploadArea && teaserImageInput) {
        // Click to upload
        uploadArea.addEventListener('click', () => {
            teaserImageInput.click();
        });
        
        // Drag and drop
        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadArea.style.borderColor = 'var(--accent)';
            uploadArea.style.backgroundColor = 'rgba(255, 238, 0, 0.1)';
        });
        
        uploadArea.addEventListener('dragleave', (e) => {
            e.preventDefault();
            uploadArea.style.borderColor = '';
            uploadArea.style.backgroundColor = '';
        });
        
        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.style.borderColor = '';
            uploadArea.style.backgroundColor = '';
            
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                handleFileUpload(files[0]);
            }
        });
        
        // File input change
        teaserImageInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                handleFileUpload(e.target.files[0]);
            }
        });
    }
    
    // Handle file upload
    async function handleFileUpload(file) {
        // Validate file type
        const allowedTypes = ['image/png', 'image/jpg', 'image/jpeg', 'image/gif', 'image/webp'];
        if (!allowedTypes.includes(file.type)) {
            alert('Tipo de arquivo não permitido. Use PNG, JPG, GIF ou WEBP.');
            return;
        }
        
        // Validate file size (16MB)
        if (file.size > 16 * 1024 * 1024) {
            alert('Arquivo muito grande. Máximo 16MB.');
            return;
        }
        
        // Show progress
        uploadText.classList.add('hidden');
        uploadProgress.classList.remove('hidden');
        
        try {
            const formData = new FormData();
            formData.append('file', file);
            
            const response = await fetch('/api/upload/teaser', {
                method: 'POST',
                body: formData
            });
            
            const result = await response.json();
            
            if (result.success) {
                // Update hidden input
                teaserImagePath.value = result.filename;
                
                // Show preview
                previewImg.src = result.url;
                imagePreview.classList.remove('hidden');
                
                console.log('Image uploaded successfully:', result.filename);
            } else {
                throw new Error(result.error || 'Upload failed');
            }
        } catch (error) {
            console.error('Upload error:', error);
            alert('Erro ao enviar imagem: ' + error.message);
        } finally {
            // Hide progress
            uploadProgress.classList.add('hidden');
            uploadText.classList.remove('hidden');
        }
    }
    
    // Remove image
    if (removeImage) {
        removeImage.addEventListener('click', () => {
            teaserImagePath.value = '';
            imagePreview.classList.add('hidden');
            previewImg.src = '';
            teaserImageInput.value = '';
        });
    }
    
    // =============  EXISTING FUNCTIONALITY  =============
    
    // Font selector
    if (fontSelector && postBody) {
        fontSelector.addEventListener('change', (e) => {
            postBody.style.fontFamily = e.target.value;
        });
    }
    
    // Preview toggle
    if (togglePreview && previewPanel) {
        togglePreview.addEventListener('click', () => {
            previewPanel.classList.toggle('hidden');
            if (!previewPanel.classList.contains('hidden')) {
                updatePreview();
            }
        });
    }
    
    // Update preview
    function updatePreview() {
        if (previewContent && postBody && postTitle) {
            const html = marked.parse(postBody.value);
            previewContent.innerHTML = `
                <h2 class="text-xl font-bold mb-3">${postTitle.value || 'Untitled'}</h2>
                ${html}
            `;
        }
    }
    
    // Auto-save draft
    let autoSaveTimer;
    if (postBody) {
        postBody.addEventListener('input', () => {
            clearTimeout(autoSaveTimer);
            autoSaveTimer = setTimeout(() => {
                const draft = {
                    title: postTitle.value,
                    body: postBody.value,
                    tags: tagInput.value,
                    font: fontSelector.value,
                    post_theme: themeSelector ? themeSelector.value : 'inherit',
                    teaser_type: teaserType ? teaserType.value : 'auto',
                    teaser_image: teaserImagePath ? teaserImagePath.value : ''
                };
                localStorage.setItem('postDraft', JSON.stringify(draft));
                console.log('Draft auto-saved');
            }, 1000);
            
            // Update preview if visible
            if (!previewPanel.classList.contains('hidden')) {
                updatePreview();
            }
        });
    }
    
    // Load draft if exists
    const draft = localStorage.getItem('postDraft');
    if (draft && !postBody.value) { // Only load if not editing existing post
        try {
            const draftData = JSON.parse(draft);
            if (postTitle) postTitle.value = draftData.title || '';
            if (postBody) postBody.value = draftData.body || '';
            if (tagInput) tagInput.value = draftData.tags || '';
            if (fontSelector) fontSelector.value = draftData.font || 'Consolas';
            if (themeSelector) themeSelector.value = draftData.post_theme || 'inherit';
            if (teaserType) teaserType.value = draftData.teaser_type || 'auto';
            if (teaserImagePath) teaserImagePath.value = draftData.teaser_image || '';
        } catch (e) {
            console.error('Error loading draft:', e);
        }
    }
    
    // Convert markdown to HTML before submitting
    if (postForm) {
        postForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const formData = new FormData(postForm);
            const bodyMarkdown = formData.get('body');
            const bodyHtml = marked.parse(bodyMarkdown);
            
            // Create JSON payload
            const payload = {
                title: formData.get('title'),
                body_html: bodyHtml,
                tags: formData.get('tags'),
                font: formData.get('font'),
                post_theme: formData.get('post_theme') || 'inherit',
                teaser_type: formData.get('teaser_type') || 'auto',
                teaser_image: formData.get('teaser_image') || ''
            };
            
            try {
                const response = await fetch(postForm.action || '/post/new', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(payload)
                });
                
                const result = await response.json();
                
                if (result.success) {
                    // Clear draft
                    localStorage.removeItem('postDraft');
                    // Redirect to post
                    window.location.href = `/post/${result.post_id}`;
                } else {
                    alert('Error saving post');
                }
            } catch (error) {
                console.error('Error:', error);
                alert('Error saving post');
            }
        });
    }
    
    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        // Ctrl+S to save
        if (e.ctrlKey && e.key === 's' && postForm) {
            e.preventDefault();
            postForm.dispatchEvent(new Event('submit'));
        }
        
        // Ctrl+P to preview
        if (e.ctrlKey && e.key === 'p' && togglePreview) {
            e.preventDefault();
            togglePreview.click();
        }
    });
});