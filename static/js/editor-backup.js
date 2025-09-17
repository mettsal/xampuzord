// static/js/editor.js
document.addEventListener('DOMContentLoaded', function() {
    const postBody = document.getElementById('postBody');
    const postTitle = document.getElementById('postTitle');
    const tagInput = document.getElementById('tagInput');
    const fontSelector = document.getElementById('fontSelector');
    const togglePreview = document.getElementById('togglePreview');
    const previewPanel = document.getElementById('previewPanel');
    const previewContent = document.getElementById('previewContent');
    const postForm = document.getElementById('postForm');
    
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
                    font: fontSelector.value
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
                font: formData.get('font')
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