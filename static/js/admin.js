// static/js/admin.js — painel admin (/admin): Posts · Moderação · Usuários · Site
//
// Tudo via /api/admin/* (JSON + X-CSRFToken). Texto de usuário entra sempre
// por textContent, nunca innerHTML.
(() => {
    const csrfToken = () => {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.content : '';
    };
    const $ = (id) => document.getElementById(id);
    const el = (tag, cls, text) => {
        const node = document.createElement(tag);
        if (cls) node.className = cls;
        if (text != null) node.textContent = text;
        return node;
    };
    const button = (label, cls, onClick) => {
        const b = el('button', `acv-action ${cls || ''}`.trim(), label);
        b.type = 'button';
        b.addEventListener('click', onClick);
        return b;
    };
    const link = (label, href) => {
        const a = el('a', 'acv-link', label);
        a.href = href;
        a.target = '_blank';
        a.rel = 'noopener';
        return a;
    };
    const fold = (s) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
    const day = (iso) => (iso ? new Date(iso).toLocaleDateString('pt-BR') : '—');
    const when = (iso) => (iso ? new Date(iso).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' }) : '—');

    async function api(url, method = 'GET', body) {
        const opts = { method, headers: { Accept: 'application/json' } };
        if (body !== undefined) {
            opts.headers['Content-Type'] = 'application/json';
            opts.body = JSON.stringify(body);
        }
        if (method !== 'GET') opts.headers['X-CSRFToken'] = csrfToken();
        const res = await fetch(url, opts);
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
        return data;
    }

    function flash(text, isError) {
        document.querySelectorAll('.xpo-acervo-flash').forEach((n) => n.remove());
        const node = el('p', `xpo-acervo-flash${isError ? ' is-error' : ''}`, text);
        document.querySelector('.xpo-admin-tabs').insertAdjacentElement('afterend', node);
        setTimeout(() => node.remove(), 5000);
    }
    const fail = (err) => flash(`Erro: ${err.message}`, true);

    // -- abas ---------------------------------------------------------------
    const loaded = new Set();
    const loaders = { posts: loadPosts, moderacao: loadModeration, usuarios: loadUsers, site: loadSite };

    function showTab(name) {
        if (!loaders[name]) name = 'posts';
        document.querySelectorAll('[data-tab]').forEach((b) => {
            const active = b.dataset.tab === name;
            b.classList.toggle('is-active', active);
            b.setAttribute('aria-selected', String(active));
        });
        document.querySelectorAll('[data-panel]').forEach((p) => { p.hidden = p.dataset.panel !== name; });
        if (!loaded.has(name)) {
            loaded.add(name);
            loaders[name]().catch(fail);
        }
    }
    document.querySelectorAll('[data-tab]').forEach((b) => b.addEventListener('click', () => {
        history.replaceState(null, '', `#${b.dataset.tab}`);
        showTab(b.dataset.tab);
    }));

    // -- posts --------------------------------------------------------------
    const PAGE = 100;
    let posts = [];
    let postFilter = 'all';
    let postQuery = '';
    let postLimit = PAGE;

    async function loadPosts() {
        posts = await api('/api/admin/posts');
        renderPosts();
    }

    function visiblePosts() {
        const sort = $('postSort').value;
        const list = posts.filter((p) => {
            if (postFilter === 'visible' && p.hidden) return false;
            if (postFilter === 'hidden' && !p.hidden) return false;
            return !postQuery || fold(`${p.title} ${p.slug || ''}`).includes(postQuery);
        });
        if (sort === 'views') list.sort((a, b) => b.views - a.views);
        else if (sort === 'title') list.sort((a, b) => a.title.localeCompare(b.title, 'pt-BR', { numeric: true }));
        else list.sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''));
        return list;
    }

    function renderPosts() {
        const counts = { all: posts.length, visible: posts.filter((p) => !p.hidden).length };
        counts.hidden = counts.all - counts.visible;
        document.querySelectorAll('[data-post-count]').forEach((s) => { s.textContent = counts[s.dataset.postCount]; });

        const list = visiblePosts();
        const frag = document.createDocumentFragment();
        list.slice(0, postLimit).forEach((p) => frag.append(postRow(p)));
        if (!list.length) frag.append(el('p', 'xpo-acervo-empty', 'nenhum post com esse filtro.'));
        $('postList').replaceChildren(frag);
        $('postMore').hidden = list.length <= postLimit;
        $('postMore').textContent = `mostrar mais (${list.length - postLimit})`;
    }

    function replacePost(updated) {
        posts = posts.map((p) => (p.id === updated.id ? updated : p));
        renderPosts();
    }

    function postRow(p) {
        const row = el('div', `acv-row acv-admin-row${p.hidden ? ' is-muted' : ''}`);
        const title = el('span', 'acv-title', p.title);
        title.title = p.slug ? `/post/${p.slug}` : '';
        const meta = el('span', 'acv-meta', `${day(p.created_at)} · 👁 ${p.views} · ♡ ${p.likes} · 💬 ${p.comments}`);
        row.append(title, meta);
        if (p.hidden) row.append(el('span', 'acv-badge', 'oculto'));

        const actions = el('span', 'acv-actions');
        actions.append(button('título', '', () => editTitle(row, p)));
        if (p.views > 0) {
            actions.append(button('zerar views', '', async () => {
                try {
                    await api(`/api/admin/posts/${p.id}/views/reset`, 'POST');
                    replacePost({ ...p, views: 0 });
                    flash(`Views de "${p.title}" zeradas.`);
                } catch (err) { fail(err); }
            }));
        }
        actions.append(button(p.hidden ? 'mostrar' : 'ocultar', '', async () => {
            try {
                replacePost(await api(`/api/admin/posts/${p.id}`, 'PATCH', { hidden: !p.hidden }));
            } catch (err) { fail(err); }
        }));
        actions.append(link('ver ↗', p.url), link('editor ↗', `/post/${p.id}/edit`));
        row.append(actions);
        return row;
    }

    function editTitle(row, p) {
        const input = el('input', 'acv-title-input');
        input.value = p.title;
        input.maxLength = 200;
        input.setAttribute('aria-label', 'Novo título');
        const save = async () => {
            const title = input.value.trim();
            if (!title || title === p.title) { renderPosts(); return; }
            try {
                const updated = await api(`/api/admin/posts/${p.id}`, 'PATCH', { title });
                replacePost(updated);
                flash(updated.slug !== p.slug
                    ? `Título salvo. Nova URL: /post/${updated.slug} (a antiga redireciona).`
                    : 'Título salvo.');
            } catch (err) { fail(err); }
        };
        input.addEventListener('keydown', (ev) => {
            if (ev.key === 'Enter') save();
            if (ev.key === 'Escape') renderPosts();
        });
        const actions = el('span', 'acv-actions');
        actions.append(button('salvar', 'is-primary', save), button('cancelar', '', renderPosts));
        row.replaceChildren(input, actions);
        input.focus();
        input.select();
    }

    document.querySelectorAll('[data-post-filter]').forEach((b) => b.addEventListener('click', () => {
        postFilter = b.dataset.postFilter;
        postLimit = PAGE;
        document.querySelectorAll('[data-post-filter]').forEach((x) => x.classList.toggle('is-active', x === b));
        renderPosts();
    }));
    let filterTimer;
    $('postFilter').addEventListener('input', (ev) => {
        clearTimeout(filterTimer);
        filterTimer = setTimeout(() => { postQuery = fold(ev.target.value.trim()); postLimit = PAGE; renderPosts(); }, 150);
    });
    $('postSort').addEventListener('change', () => { postLimit = PAGE; renderPosts(); });
    $('postMore').addEventListener('click', () => { postLimit += PAGE; renderPosts(); });
    $('viewsResetAll').addEventListener('click', async () => {
        const typed = prompt('Isto zera as views de TODOS os poemas e não tem volta.\nDigite "zerar" para confirmar:');
        if (typed == null) return;
        if (typed.trim().toLowerCase() !== 'zerar') { flash('Nada feito: confirmação não bate.', true); return; }
        try {
            const res = await api('/api/admin/views/reset', 'POST', { confirm: 'zerar' });
            posts = posts.map((p) => ({ ...p, views: 0 }));
            renderPosts();
            flash(`Views zeradas em ${res.posts} poema(s).`);
        } catch (err) { fail(err); }
    });

    // -- moderação ----------------------------------------------------------
    async function loadModeration() {
        const data = await api('/api/admin/moderation');
        renderItems('commentList', 'commentCount', data.comments, 'comments', 'nenhum comentário.');
        renderItems('testimonialList', 'testimonialCount', data.testimonials, 'testimonials', 'nenhum depoimento.');
    }

    function renderItems(listId, countId, items, kind, empty) {
        $(countId).textContent = `(${items.length})`;
        const frag = document.createDocumentFragment();
        for (const item of items) {
            const row = el('div', 'acv-row acv-admin-row acv-mod-row');
            const head = el('span', 'acv-meta acv-mod-head', `@${item.author} · ${when(item.created_at)}`);
            const body = el('span', 'acv-mod-body', item.body);
            const actions = el('span', 'acv-actions');
            if (item.post) actions.append(link(`em "${item.post.title}" ↗`, item.post.url));
            actions.append(button('apagar', 'is-danger', async () => {
                if (!confirm(`Apagar este ${kind === 'comments' ? 'comentário' : 'depoimento'} de @${item.author}?`)) return;
                try {
                    await api(`/api/admin/${kind}/${item.id}`, 'DELETE');
                    row.remove();
                    const left = $(listId).querySelectorAll('.acv-mod-row').length;
                    $(countId).textContent = `(${left})`;
                    flash('Apagado.');
                } catch (err) { fail(err); }
            }));
            row.append(head, body, actions);
            frag.append(row);
        }
        if (!items.length) frag.append(el('p', 'xpo-acervo-empty', empty));
        $(listId).replaceChildren(frag);
    }

    // -- usuários -----------------------------------------------------------
    async function loadUsers() {
        renderUsers(await api('/api/admin/users'));
    }

    function renderUsers(users) {
        const frag = document.createDocumentFragment();
        for (const u of users) {
            const row = el('div', `acv-row acv-admin-row${u.is_banned ? ' is-muted' : ''}`);
            row.append(el('span', 'acv-title', `@${u.username}`),
                el('span', 'acv-meta', `${u.email} · desde ${day(u.created_at)} · 💬 ${u.comments} · ✍ ${u.testimonials}`));
            if (u.is_admin) row.append(el('span', 'acv-badge acv-badge-changed', 'admin'));
            if (u.is_banned) row.append(el('span', 'acv-badge acv-badge-new', 'bloqueado'));
            if (!u.comments && !u.testimonials && !u.is_admin) row.append(el('span', 'acv-badge', 'sem atividade'));
            const actions = el('span', 'acv-actions');
            if (!u.is_admin && !u.is_self) {
                actions.append(button(u.is_banned ? 'desbloquear' : 'bloquear', '', async () => {
                    try {
                        await api(`/api/admin/users/${u.id}`, 'PATCH', { banned: !u.is_banned });
                        await loadUsers();
                    } catch (err) { fail(err); }
                }));
                actions.append(button('apagar', 'is-danger', async () => {
                    const extra = u.comments + u.testimonials ? ` e ${u.comments} comentário(s) + ${u.testimonials} depoimento(s)` : '';
                    if (!confirm(`Apagar a conta @${u.username}${extra}? Não tem volta.`)) return;
                    try {
                        await api(`/api/admin/users/${u.id}`, 'DELETE');
                        await loadUsers();
                        flash(`@${u.username} apagado.`);
                    } catch (err) { fail(err); }
                }));
            }
            row.append(actions);
            frag.append(row);
        }
        $('userList').replaceChildren(frag);
    }

    // -- site ---------------------------------------------------------------
    async function loadSite() {
        renderSite(await api('/api/admin/site'));
    }

    function renderSite(data) {
        const frag = document.createDocumentFragment();
        for (const sw of data.switches) {
            const row = el('label', `acv-row xpo-admin-switch${sw.on ? '' : ' is-off'}`);
            const box = el('input');
            box.type = 'checkbox';
            box.checked = sw.on;
            box.addEventListener('change', async () => {
                try {
                    renderSite(await api('/api/admin/site', 'PATCH', { [sw.key]: box.checked }));
                    flash(`${sw.label}: ${box.checked ? 'aberto' : 'fechado'}.`);
                } catch (err) { box.checked = !box.checked; fail(err); }
            });
            row.append(box, el('span', 'acv-title', sw.label), el('span', 'acv-meta', sw.on ? 'aberto' : 'fechado'));
            frag.append(row);
        }
        $('switchList').replaceChildren(frag);

        const st = data.status;
        const pub = st.publish;
        const pubText = !pub ? 'ainda não rodou'
            : pub.ok === false ? `${when(pub.at)} — ERRO: ${pub.error}`
            : `${when(pub.at)} — ${pub.published.length} publicado(s)${pub.published.length ? `: ${pub.published.join(', ')}` : ''}`
              + (pub.updated.length ? ` · ${pub.updated.length} atualizado(s)` : '');
        const rows = [
            ['Poemas', `${st.posts_visible} no site · ${st.posts_hidden} ocultos`],
            ['Views', String(st.views_total)],
            ['Contas', `${st.users}${st.users_banned ? ` · ${st.users_banned} bloqueada(s)` : ''}`],
            ['Último backup', st.backup ? `${when(st.backup.at)} (${st.backup.count} guardados)` : 'nenhum backup encontrado ⚠'],
            ['Publicação automática', pubText],
        ];
        const dl = document.createDocumentFragment();
        for (const [k, v] of rows) {
            dl.append(el('dt', null, k));
            const dd = el('dd', null, v);
            if (v.includes('⚠') || v.includes('ERRO')) dd.classList.add('is-warn');
            dl.append(dd);
        }
        $('siteStatus').replaceChildren(dl);
    }

    showTab(location.hash.slice(1));
})();
