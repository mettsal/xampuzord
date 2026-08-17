// static/js/post-view.js
// Zoom do poema: auto-fit à largura da tela + controles manuais [−] % [+]

document.addEventListener('DOMContentLoaded', function() {
    const content = document.getElementById('poemContent');
    const zoomIn = document.getElementById('zoomIn');
    const zoomOut = document.getElementById('zoomOut');
    const zoomLabel = document.getElementById('zoomLevel');
    if (!content || !zoomIn || !zoomOut || !zoomLabel) return;

    // Seletor de tema para o LEITOR: não altera o post salvo; a preferência
    // fica em localStorage ('readerPostTheme'). Vazio = tema escolhido pelo autor.
    const readerTheme = document.getElementById('readerTheme');
    const themeWrapper = document.getElementById('postThemeWrapper');
    if (readerTheme && themeWrapper) {
        const POST_THEMES = ['inherit', 'dark', 'light', 'cyberpunk', 'matrix', 'vaporwave', 'noir', 'sunset', 'ocean'];
        const authorTheme = themeWrapper.dataset.authorTheme || 'inherit';

        const applyReaderTheme = (theme) => {
            POST_THEMES.forEach(t => themeWrapper.classList.remove(`post-theme-${t}`));
            themeWrapper.classList.add(`post-theme-${theme || authorTheme}`);
        };

        const savedTheme = localStorage.getItem('readerPostTheme');
        if (savedTheme && POST_THEMES.includes(savedTheme)) {
            readerTheme.value = savedTheme;
            applyReaderTheme(savedTheme);
        }

        readerTheme.addEventListener('change', () => {
            const theme = readerTheme.value;
            if (theme) {
                localStorage.setItem('readerPostTheme', theme);
            } else {
                localStorage.removeItem('readerPostTheme');
            }
            applyReaderTheme(theme);
        });
    }

    // Curtida anônima: toggle por visitante (UUID no localStorage). O estado
    // "eu curti" fica no navegador; o contador vem do servidor.
    // getCsrfToken() é global, definida em main.js (carregado antes).
    const likeBtn = document.getElementById('likeBtn');
    if (likeBtn) {
        let visitorId = localStorage.getItem('visitorId');
        if (!visitorId) {
            visitorId = (window.crypto && crypto.randomUUID)
                ? crypto.randomUUID()
                : String(Date.now()) + '-' + Math.random();
            localStorage.setItem('visitorId', visitorId);
        }
        const postId = likeBtn.dataset.postId;
        const likedPosts = JSON.parse(localStorage.getItem('likedPosts') || '{}');
        const likeIcon = document.getElementById('likeIcon');
        const likeCount = document.getElementById('likeCount');

        const renderLike = (liked, count) => {
            likeIcon.textContent = liked ? '♥' : '♡';
            likeBtn.setAttribute('aria-pressed', liked);
            if (count !== undefined) likeCount.textContent = count;
        };
        renderLike(!!likedPosts[postId]);

        likeBtn.addEventListener('click', async () => {
            try {
                const res = await fetch(`/post/${postId}/like`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCsrfToken()
                    },
                    body: JSON.stringify({visitor_id: visitorId})
                });
                const data = await res.json();
                if (data.success) {
                    if (data.liked) {
                        likedPosts[postId] = true;
                    } else {
                        delete likedPosts[postId];
                    }
                    localStorage.setItem('likedPosts', JSON.stringify(likedPosts));
                    renderLike(data.liked, data.likes);
                }
            } catch (e) {
                console.error('Like error:', e);
            }
        });
    }

    const MIN_ZOOM = 0.5;
    const MAX_ZOOM = 3;
    const FIT_FLOOR = 0.55; // abaixo disso o texto fica ilegível; mantém scroll horizontal
    const STEP = 0.1;

    let zoom = 1;
    let userSet = false; // zoom manual não é sobrescrito pelo auto-fit

    function applyZoom(value) {
        zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, value));
        content.style.setProperty('--poem-zoom', zoom);
        zoomLabel.textContent = Math.round(zoom * 100) + '%';
    }

    function fitToWidth() {
        // Mede na escala 1 para obter a largura real do verso mais largo
        content.style.setProperty('--poem-zoom', 1);
        const available = content.clientWidth;
        let widest = content.scrollWidth;
        content.querySelectorAll('pre').forEach(pre => {
            widest = Math.max(widest, pre.scrollWidth);
        });
        if (widest > available && available > 0) {
            applyZoom(Math.max(FIT_FLOOR, available / widest));
        } else {
            applyZoom(1);
        }
    }

    zoomIn.addEventListener('click', () => {
        userSet = true;
        applyZoom(zoom + STEP);
    });

    zoomOut.addEventListener('click', () => {
        userSet = true;
        applyZoom(zoom - STEP);
    });

    // Clicar no % volta ao ajuste automático
    zoomLabel.addEventListener('click', () => {
        userSet = false;
        fitToWidth();
    });

    let resizeTimeout;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimeout);
        resizeTimeout = setTimeout(() => {
            if (!userSet) fitToWidth();
        }, 200);
    });

    fitToWidth();
});
