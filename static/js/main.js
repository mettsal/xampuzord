// static/js/main-enhanced.js

// Read the CSRF token rendered into the page <meta> for state-changing fetches.
function getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
}

document.addEventListener('DOMContentLoaded', function() {
    // Enhanced B/W Theme Management
    const themeToggle = document.getElementById('themeToggle');
    const body = document.body;
    const searchBar = document.getElementById('searchBar');
    
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
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCsrfToken()
                    },
                    body: JSON.stringify({theme: theme, font: localStorage.getItem('font') || 'Consolas'})
                });
            }
        });
    }
    
    // Search functionality
    if (searchBar) {
        let searchTimeout;
        searchBar.addEventListener('input', (e) => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                const searchQuery = e.target.value.trim().toLowerCase();
                filterPostsBySearch(searchQuery);
            }, 300); // Debounce 300ms
        });

        // Clear search on Escape
        searchBar.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                searchBar.value = '';
                filterPostsBySearch('');
            }
        });
    }

    // Click on tags to search
    document.addEventListener('click', (e) => {
        if (e.target.classList.contains('tag-pill') && searchBar) {
            e.stopPropagation(); // Prevent post navigation
            const tagText = e.target.textContent.trim();
            searchBar.value = tagText;
            filterPostsBySearch(tagText.toLowerCase());
            searchBar.focus();
        }
    });

    function filterPostsBySearch(query) {
        const postCards = document.querySelectorAll('.post-card');
        const searchCount = document.getElementById('searchCount');

        if (!query) {
            // Show all posts
            postCards.forEach(card => card.style.display = '');
            if (searchCount) searchCount.classList.add('hidden');
            return;
        }

        let visibleCount = 0;
        postCards.forEach(card => {
            // Get all tag elements in this card
            const tags = card.querySelectorAll('.tag-pill');
            const tagValues = Array.from(tags).map(tag => tag.textContent.toLowerCase());

            // Check if any tag matches the search query
            const matches = tagValues.some(tag => tag.includes(query));

            card.style.display = matches ? '' : 'none';
            if (matches) visibleCount++;
        });

        // Show count feedback
        if (searchCount) {
            searchCount.textContent = `${visibleCount} post${visibleCount !== 1 ? 's' : ''} encontrado${visibleCount !== 1 ? 's' : ''}`;
            searchCount.classList.remove('hidden');
        }
    }

    // Infinite Scroll and other functionality
    const postGrid = document.getElementById('postGrid');
    const scrollSentinel = document.getElementById('scrollSentinel');
    const loadingIndicator = document.getElementById('loadingIndicator');

    if (postGrid && scrollSentinel) {
        const PAGE_SIZE = 9; // must match app.py per_page
        let currentPage = 2;
        let isLoading = false;
        let hasMore = true;
        let searchTags = [];

        const loadMorePosts = async () => {
            if (isLoading || !hasMore) return;
            isLoading = true;
            if (loadingIndicator) loadingIndicator.classList.remove('hidden');

            try {
                const params = new URLSearchParams({
                    page: currentPage,
                    tags: JSON.stringify(searchTags)
                });
                const response = await fetch(`/api/posts?${params}`);
                const posts = await response.json();

                posts.forEach(post => {
                    const postCard = createPostCard(post);
                    postGrid.appendChild(postCard);
                });

                if (posts.length > 0) currentPage++;

                // A short (or empty) page means we've reached the end: stop observing
                // so the sentinel doesn't keep refetching the same empty page forever.
                if (posts.length < PAGE_SIZE) {
                    hasMore = false;
                    observer.unobserve(scrollSentinel);
                    if (loadingIndicator) loadingIndicator.classList.add('hidden');
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
                if (entries[0].isIntersecting && !isLoading && hasMore) {
                    loadMorePosts();
                }
            },
            { threshold: 0.1 }
        );

        observer.observe(scrollSentinel);
    }
    
    // Create post card element with teaser support
    function createPostCard(post) {
        const card = document.createElement('div');
        const themeClass = post.post_theme ? `post-theme-${post.post_theme}` : 'post-theme-inherit';
        card.className = `post-card p-0 hover:scale-105 transition-transform cursor-pointer relative ${themeClass}`;
        
        const tagsHtml = post.tags.map(tag => `
            <span class="tag-pill px-2 py-1 text-xs border border-current">
                ${tag.value}
            </span>
        `).join('');
        
        let cardContent = '';
        
        // Handle different teaser types
        if (post.teaser_type === 'image' && post.teaser_image) {
            cardContent = `
                <div class="teaser-image absolute inset-0">
                    <img src="/static/${post.teaser_image}" alt="${post.title}">
                </div>
                <div class="absolute inset-0 flex flex-col justify-between p-4 overlay-content">
                    <div></div>
                    <h3 class="text-center text-lg glowy-title">${post.title}</h3>
                    <div class="flex flex-wrap gap-2 justify-center">
                        ${tagsHtml}
                    </div>
                </div>
            `;
        } else if (post.teaser_type === 'none') {
            cardContent = `
                <div class="p-4">
                    <h3 class="text-lg font-bold mb-2">${post.title}</h3>
                    <div class="text-sm mb-3 opacity-70">
                        @${post.author} • ${new Date(post.created_at).toLocaleDateString('pt-BR')}
                    </div>
                    <div class="text-sm opacity-50 italic mb-3">Post sem preview</div>
                    <div class="flex flex-wrap gap-2 mb-2">
                        ${tagsHtml}
                    </div>
                    <div class="text-xs opacity-50">
                        👁 ${post.views} views
                    </div>
                </div>
            `;
        } else {
            // Auto text preview (default)
            cardContent = `
                <div class="text-preview-container absolute inset-0 flex flex-col justify-start items-start">
                    <div class="post-body text-preview-content">
                        ${post.body_html}
                    </div>
                    <div class="absolute bottom-4 left-4 right-4">
                        <h3 class="text-left text-sm glowy-title mb-2">${post.title}</h3>
                        <div class="flex flex-wrap gap-1">
                            ${tagsHtml}
                        </div>
                    </div>
                </div>
            `;
        }
        
        card.innerHTML = cardContent;
        
        card.addEventListener('click', () => {
            window.location.href = `/post/${post.id}`;
        });
        
        return card;
    }
});

// Delete post function
function deletePost(postId) {
    if (confirm('Tem certeza que deseja deletar este post? Esta ação não pode ser desfeita.')) {
        fetch(`/post/${postId}/delete`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                window.location.href = '/';
            } else {
                alert('Erro ao deletar post: ' + (data.error || 'Erro desconhecido'));
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Erro ao deletar post');
        });
    }
}