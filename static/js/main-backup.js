// static/js/main.js
document.addEventListener('DOMContentLoaded', function() {
    // Enhanced B/W Theme Management
    const themeToggle = document.getElementById('themeToggle');
    const body = document.body;
    
    // Load saved theme
    const savedTheme = localStorage.getItem('theme') || 'light';
    if (savedTheme === 'dark') {
        body.classList.add('dark');
        updateThemeButton(true);
    } else {
        updateThemeButton(false);
    }
    
    function updateThemeButton(isDark) {
        if (themeToggle) {
            themeToggle.innerHTML = isDark ? '☀️ Branco' : '🌙 Preto';
        }
    }
    
    if (themeToggle) {
        themeToggle.addEventListener('click', () => {
            body.classList.toggle('dark');
            const isDark = body.classList.contains('dark');
            const theme = isDark ? 'dark' : 'light';
            localStorage.setItem('theme', theme);
            updateThemeButton(isDark);
            
            // Save to user settings if logged in
            if (window.currentUser) {
                fetch('/api/user/settings', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({theme: theme, font: localStorage.getItem('font') || 'Consolas'})
                });
            }
        });
    }
    
    // Infinite Scroll and other functionality remains the same...
    const postGrid = document.getElementById('postGrid');
    const scrollSentinel = document.getElementById('scrollSentinel');
    const loadingIndicator = document.getElementById('loadingIndicator');
    
    if (postGrid && scrollSentinel) {
        let currentPage = 2;
        let isLoading = false;
        let searchTags = [];
        
        const loadMorePosts = async () => {
            if (isLoading) return;
            isLoading = true;
            if (loadingIndicator) loadingIndicator.classList.remove('hidden');
            
            try {
                const params = new URLSearchParams({
                    page: currentPage,
                    tags: JSON.stringify(searchTags)
                });
                const response = await fetch(`/api/posts?${params}`);
                const posts = await response.json();
                
                if (posts.length > 0) {
                    posts.forEach(post => {
                        const postCard = createPostCard(post);
                        postGrid.appendChild(postCard);
                    });
                    currentPage++;
                }
            } catch (error) {
                console.error('Error loading posts:', error);
            } finally {
                isLoading = false;
                if (loadingIndicator) loadingIndicator.classList.add('hidden');
            }
        };
        
        const observer = new IntersectionObserver(
            entries => {
                if (entries[0].isIntersecting && !isLoading) {
                    loadMorePosts();
                }
            },
            { threshold: 0.1 }
        );
        
        observer.observe(scrollSentinel);
    }
    
    function createPostCard(post) {
        const card = document.createElement('div');
        card.className = 'post-card p-4 hover:scale-105 transition-transform cursor-pointer';
        
        const tagsHtml = post.tags.map(tag => `
            <span class="tag-pill px-2 py-1 text-xs border border-current">
                ${tag.type}:${tag.value}
            </span>
        `).join('');
        
        card.innerHTML = `
            <h3 class="text-lg font-bold mb-2">${post.title}</h3>
            <div class="text-sm mb-3 opacity-70">
                @${post.author} • ${new Date(post.created_at).toLocaleDateString()}
            </div>
            <div class="mb-3 line-clamp-4">
                ${post.body_html}
            </div>
            <div class="flex flex-wrap gap-2 mb-2">
                ${tagsHtml}
            </div>
            <div class="text-xs opacity-50">
                👁 ${post.views} views
            </div>
        `;
        
        card.addEventListener('click', () => {
            window.location.href = `/post/${post.id}`;
        });
        
        return card;
    }
});
