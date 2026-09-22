// static/js/main-enhanced.js

// Read the CSRF token rendered into the page <meta> for state-changing fetches.
function getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
}

document.addEventListener('DOMContentLoaded', function() {
    // Mobile hamburger menu
    const navToggle = document.getElementById('navToggle');
    const navMenu = document.getElementById('navMenu');
    if (navToggle && navMenu) {
        navToggle.addEventListener('click', () => {
            const opened = navMenu.classList.toggle('flex');
            navMenu.classList.toggle('hidden', !opened);
            navToggle.setAttribute('aria-expanded', opened);
        });
    }

    // Enhanced B/W Theme Management
    const themeToggle = document.getElementById('themeToggle');
    const body = document.body;
    const searchBar = document.getElementById('searchBar');

    // Autocomplete de tags: popula o <datalist> da busca com as top 50 tags
    // (/api/tags). Solução nativa (input[list]) — sem lib de UI, funciona em
    // mobile e desktop. Falha silenciosa: sem a API, a busca continua igual.
    const tagSuggestions = document.getElementById('tagSuggestions');
    if (searchBar && tagSuggestions) {
        fetch('/api/tags')
            .then(r => r.json())
            .then(tags => {
                tags.forEach(t => {
                    const opt = document.createElement('option');
                    opt.value = t.name;
                    tagSuggestions.appendChild(opt);
                });
            })
            .catch(() => {});
    }
    
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
    
    // Busca com dropdown: a searchBar mora na nav (base.html), presente em
    // toda página, então essa lógica fica fora do bloco de infinite scroll
    // (que só existe na index). A busca nunca toca o grid/mosaico — ela
    // consulta /api/posts (mesmo filtro título/tags/conteúdo de
    // filter_by_search em app.py) e mostra os resultados num dropdown
    // clicável abaixo da searchBar; cada item linka direto pro post.
    const searchDropdown = document.getElementById('searchDropdown');

    if (searchBar && searchDropdown) {
        const MAX_RESULTS = 8;
        let searchTimeout;
        let searchRequestId = 0;

        const hideDropdown = () => {
            searchDropdown.classList.add('hidden');
            searchDropdown.innerHTML = '';
        };

        const renderResults = (posts) => {
            if (posts.length === 0) {
                searchDropdown.innerHTML = `<div class="search-result-empty px-3 py-2 text-sm opacity-70">Nenhum post encontrado</div>`;
                searchDropdown.classList.remove('hidden');
                return;
            }
            searchDropdown.innerHTML = posts.slice(0, MAX_RESULTS).map(post => `
                <a href="/post/${post.id}" class="search-result-item block px-3 py-2 border-b border-current last:border-b-0">
                    <div class="text-sm font-bold truncate">${post.title}</div>
                    <div class="text-xs opacity-60">@${post.author} • ${new Date(post.created_at).toLocaleDateString('pt-BR')}</div>
                </a>
            `).join('');
            searchDropdown.classList.remove('hidden');
        };

        const searchPosts = async (query) => {
            if (!query) {
                hideDropdown();
                return;
            }
            const requestId = ++searchRequestId;
            try {
                const params = new URLSearchParams({ page: 1, tags: JSON.stringify([query]) });
                const response = await fetch(`/api/posts?${params}`);
                const posts = await response.json();
                if (requestId !== searchRequestId) return; // resposta velha, query já mudou
                renderResults(posts);
            } catch (error) {
                console.error('Error searching posts:', error);
            }
        };

        searchBar.addEventListener('input', (e) => {
            clearTimeout(searchTimeout);
            const query = e.target.value.trim().toLowerCase();
            searchTimeout = setTimeout(() => searchPosts(query), 300); // Debounce 300ms
        });

        searchBar.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                searchBar.value = '';
                clearTimeout(searchTimeout);
                hideDropdown();
                searchBar.blur();
            }
        });

        searchBar.addEventListener('focus', () => {
            const query = searchBar.value.trim().toLowerCase();
            if (query) searchPosts(query);
        });

        // Fecha o dropdown ao clicar fora dele e da searchBar
        document.addEventListener('click', (e) => {
            if (!searchDropdown.contains(e.target) && e.target !== searchBar) {
                hideDropdown();
            }
        });

        // Click em tags do post/card também busca por elas
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('tag-pill')) {
                e.preventDefault(); // Tag fica dentro do <a> do card: não navega pro post
                e.stopPropagation();
                // Na página do post a pill mostra "tipo:valor" (post.html); no
                // grid só o valor (index.html). O filtro do backend casa contra
                // tag.value dentro do JSON, então buscamos só a parte do valor.
                const tagText = e.target.textContent.trim();
                const searchTerm = tagText.includes(':') ? tagText.split(':').slice(1).join(':').trim() : tagText;
                searchBar.value = searchTerm;
                clearTimeout(searchTimeout);
                searchPosts(searchTerm.toLowerCase());
                searchBar.focus();
            }
        });
    }

    // Infinite Scroll (só na index)
    const postGrid = document.getElementById('postGrid');
    const scrollSentinel = document.getElementById('scrollSentinel');
    const loadingIndicator = document.getElementById('loadingIndicator');

    if (postGrid && scrollSentinel) {
        const PAGE_SIZE = 9; // must match app.py per_page
        let currentPage = 2;
        let isLoading = false;
        let hasMore = true;

        const loadMorePosts = async () => {
            if (isLoading || !hasMore) return;
            isLoading = true;
            if (loadingIndicator) loadingIndicator.classList.remove('hidden');

            try {
                const params = new URLSearchParams({ page: currentPage });
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

    // Mosaico 3 colunas opcional no mobile (estilo Instagram). Só existe na
    // index; a preferência fica em localStorage como o tema global.
    const gridToggle = document.getElementById('gridToggle');
    if (postGrid && gridToggle) {
        const applyGridMode = (threeCols) => {
            postGrid.classList.toggle('mosaic-3', threeCols);
            gridToggle.textContent = threeCols ? '▤ 1 coluna' : '▦ 3 colunas';
            gridToggle.setAttribute('aria-pressed', threeCols);
        };
        applyGridMode(localStorage.getItem('gridCols') === '3');
        gridToggle.addEventListener('click', () => {
            const threeCols = !postGrid.classList.contains('mosaic-3');
            localStorage.setItem('gridCols', threeCols ? '3' : '1');
            applyGridMode(threeCols);
        });
    }

    // Create post card element with teaser support
    function createPostCard(post) {
        const card = document.createElement('a');
        card.href = `/post/${post.id}`;
        const themeClass = post.post_theme ? `post-theme-${post.post_theme}` : 'post-theme-inherit';
        card.className = `post-card p-0 hover:scale-105 transition-transform cursor-pointer relative block ${themeClass}`;
        
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
                    <div class="hidden md:flex flex-wrap gap-2 justify-center">
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
                    <div class="hidden md:flex flex-wrap gap-2 mb-2">
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
                        <div class="hidden md:flex flex-wrap gap-1">
                            ${tagsHtml}
                        </div>
                    </div>
                </div>
            `;
        }
        
        card.innerHTML = cardContent;

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