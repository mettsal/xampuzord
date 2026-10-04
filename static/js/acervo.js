// static/js/acervo.js — painel do acervo (/admin/acervo)
//
// Estado inicial vem de GET /api/admin/acervo; o painel guarda só o desejado
// (marcado ou não) de cada arquivo/post e manda as DIFERENÇAS no POST — ver
// acervo.py para o porquê.
(() => {
    const API = '/api/admin/acervo';
    const csrfToken = () => {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.content : '';
    };

    const $ = (id) => document.getElementById(id);
    const treeEl = $('acervoTree');
    const orphansEl = $('acervoOrphans');
    const bar = $('acervoBar');
    const modal = $('acervoModal');

    let files = [];            // [{path, title, date, post_id, state}]
    let orphans = [];          // [{id, title, source_path, state}]
    const desired = new Map(); // path -> bool
    const desiredPost = new Map(); // id -> bool
    const expanded = new Set();
    let root = null;
    let stateFilter = 'all';
    let query = '';
    let pending = null;        // payload revisado no modal

    // -- util ---------------------------------------------------------------
    const fold = (s) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
    const el = (tag, cls, text) => {
        const node = document.createElement(tag);
        if (cls) node.className = cls;
        if (text != null) node.textContent = text;
        return node;
    };
    const isOn = (f) => f.state === 'on';
    const isChanged = (f) => desired.get(f.path) !== isOn(f);
    const postChanged = (o) => desiredPost.get(o.id) !== (o.state === 'on');
    const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

    function fileVisible(f) {
        if (stateFilter === 'changed' && !isChanged(f)) return false;
        if (!['all', 'changed'].includes(stateFilter) && f.state !== stateFilter) return false;
        if (query && !fold(`${f.path} ${f.title}`).includes(query)) return false;
        return true;
    }
    const filtering = () => stateFilter !== 'all' || query !== '';

    // -- árvore -------------------------------------------------------------
    function buildTree() {
        root = { name: '', path: '', folders: new Map(), files: [] };
        for (const f of files) {
            const parts = f.path.split('/');
            let node = root;
            for (const part of parts.slice(0, -1)) {
                if (!node.folders.has(part)) {
                    const path = node.path ? `${node.path}/${part}` : part;
                    node.folders.set(part, { name: part, path, folders: new Map(), files: [] });
                }
                node = node.folders.get(part);
            }
            node.files.push(f);
        }
    }

    function* allFiles(node) {
        yield* node.files;
        for (const child of node.folders.values()) yield* allFiles(child);
    }

    const byName = (a, b) => a.name.localeCompare(b.name, 'pt-BR', { numeric: true });

    function render() {
        const frag = document.createDocumentFragment();
        renderNode(root, 0, frag);
        treeEl.replaceChildren(frag);
        if (!treeEl.childElementCount) {
            treeEl.append(el('p', 'xpo-acervo-empty', 'nada aqui com esse filtro.'));
        }
        renderOrphans();
        updateCounts();
    }

    function renderNode(node, depth, out) {
        const folders = [...node.folders.values()].sort(byName);
        for (const folder of folders) {
            const scope = [...allFiles(folder)];
            const visible = scope.filter(fileVisible);
            if (!visible.length) continue;
            const open = filtering() || expanded.has(folder.path);
            out.append(folderRow(folder, depth, scope, visible, open));
            if (open) renderNode(folder, depth + 1, out);
        }
        const leaves = node.files.filter(fileVisible).sort((a, b) => a.path.localeCompare(b.path, 'pt-BR', { numeric: true }));
        for (const f of leaves) out.append(fileRow(f, depth));
    }

    function folderRow(folder, depth, scope, visible, open) {
        const row = el('div', 'acv-row acv-folder');
        row.style.setProperty('--depth', depth);
        row.dataset.folder = folder.path;

        const caret = el('button', 'acv-caret', open ? '▼' : '▶');
        caret.type = 'button';
        caret.setAttribute('aria-label', open ? 'fechar pasta' : 'abrir pasta');
        caret.setAttribute('aria-expanded', String(open));

        const box = el('input');
        box.type = 'checkbox';
        const onCount = visible.filter((f) => desired.get(f.path)).length;
        box.checked = onCount === visible.length;
        box.indeterminate = onCount > 0 && onCount < visible.length;
        box.setAttribute('aria-label', `publicar pasta ${folder.name}`);

        const name = el('span', 'acv-name', folder.name);
        const totalOn = scope.filter((f) => desired.get(f.path)).length;
        const meta = el('span', 'acv-meta', `${totalOn}/${scope.length} no site`);
        row.append(caret, box, name, meta);

        const fresh = scope.filter((f) => f.state === 'new').length;
        if (fresh) row.append(el('span', 'acv-badge acv-badge-new', plural(fresh, 'novo', 'novos')));
        const changed = scope.filter(isChanged).length;
        if (changed) row.append(el('span', 'acv-badge acv-badge-changed', `±${changed}`));
        return row;
    }

    function fileRow(f, depth) {
        const row = el('label', 'acv-row acv-file');
        row.style.setProperty('--depth', depth);
        if (isChanged(f)) row.classList.add(desired.get(f.path) ? 'is-adding' : 'is-removing');

        const box = el('input');
        box.type = 'checkbox';
        box.checked = desired.get(f.path);
        box.dataset.path = f.path;

        const title = el('span', 'acv-title', f.title);
        const filename = f.path.split('/').pop();
        const meta = el('span', 'acv-meta', `${f.date.slice(0, 4) === '2000' ? 'sem data' : f.date} · ${filename}`);
        row.append(box, title, meta);

        if (f.state === 'new') row.append(el('span', 'acv-badge acv-badge-new', 'novo'));
        if (f.state === 'hidden') row.append(el('span', 'acv-badge', 'oculto'));
        if (f.post_id) {
            const link = el('a', 'acv-link', 'ver ↗');
            link.href = `/post/${f.post_id}`;
            link.target = '_blank';
            link.rel = 'noopener';
            row.append(link);
        }
        return row;
    }

    function renderOrphans() {
        const wrap = $('acervoOrphansWrap');
        wrap.hidden = orphans.length === 0;
        $('acervoOrphansCount').textContent = `(${orphans.length})`;
        const frag = document.createDocumentFragment();
        for (const o of orphans) {
            const row = el('label', 'acv-row acv-file');
            row.style.setProperty('--depth', 0);
            if (postChanged(o)) row.classList.add(desiredPost.get(o.id) ? 'is-adding' : 'is-removing');
            const box = el('input');
            box.type = 'checkbox';
            box.checked = desiredPost.get(o.id);
            box.dataset.postId = o.id;
            const link = el('a', 'acv-link', 'ver ↗');
            link.href = `/post/${o.id}`;
            link.target = '_blank';
            link.rel = 'noopener';
            row.append(box, el('span', 'acv-title', o.title),
                el('span', 'acv-meta', o.source_path ? `arquivo sumiu: ${o.source_path}` : `#${o.id}`));
            if (o.state === 'hidden') row.append(el('span', 'acv-badge', 'oculto'));
            row.append(link);
            frag.append(row);
        }
        orphansEl.replaceChildren(frag);
    }

    // -- contagens e barra de mudanças --------------------------------------
    function payload() {
        const p = { include: [], exclude: [], include_posts: [], exclude_posts: [] };
        for (const f of files) {
            if (!isChanged(f)) continue;
            (desired.get(f.path) ? p.include : p.exclude).push(f.path);
        }
        for (const o of orphans) {
            if (!postChanged(o)) continue;
            (desiredPost.get(o.id) ? p.include_posts : p.exclude_posts).push(o.id);
        }
        return p;
    }

    function updateCounts() {
        const counts = { all: files.length, on: 0, hidden: 0, new: 0, changed: 0 };
        for (const f of files) {
            counts[f.state] += 1;
            if (isChanged(f)) counts.changed += 1;
        }
        counts.changed += orphans.filter(postChanged).length;
        document.querySelectorAll('[data-count]').forEach((span) => {
            span.textContent = counts[span.dataset.count];
        });

        const toImport = files.filter((f) => isChanged(f) && f.state === 'new').length;
        const toShow = files.filter((f) => isChanged(f) && f.state === 'hidden').length
            + orphans.filter((o) => postChanged(o) && desiredPost.get(o.id)).length;
        const toHide = files.filter((f) => isChanged(f) && f.state === 'on').length
            + orphans.filter((o) => postChanged(o) && !desiredPost.get(o.id)).length;
        const parts = [];
        if (toImport) parts.push(`+${toImport} importar`);
        if (toShow) parts.push(`+${toShow} reexibir`);
        if (toHide) parts.push(`−${toHide} ocultar`);
        bar.hidden = parts.length === 0;
        $('acervoSummary').textContent = parts.length
            ? `${plural(counts.changed, 'mudança', 'mudanças')}: ${parts.join(' · ')}` : '';
    }

    // -- eventos ------------------------------------------------------------
    treeEl.addEventListener('click', (ev) => {
        const caret = ev.target.closest('.acv-caret');
        if (!caret) return;
        const path = caret.closest('[data-folder]').dataset.folder;
        if (expanded.has(path)) expanded.delete(path); else expanded.add(path);
        render();
    });

    treeEl.addEventListener('change', (ev) => {
        const box = ev.target;
        if (box.dataset.path) {
            desired.set(box.dataset.path, box.checked);
        } else {
            const folderPath = box.closest('[data-folder]').dataset.folder;
            const folder = folderPath.split('/').reduce((node, part) => node.folders.get(part), root);
            // Com filtro ativo, a pasta age só sobre o que está à vista.
            const scope = [...allFiles(folder)].filter(fileVisible);
            const allChecked = scope.every((f) => desired.get(f.path));
            scope.forEach((f) => desired.set(f.path, !allChecked));
        }
        render();
    });

    orphansEl.addEventListener('change', (ev) => {
        desiredPost.set(Number(ev.target.dataset.postId), ev.target.checked);
        render();
    });

    document.querySelectorAll('[data-filter]').forEach((btn) => {
        btn.addEventListener('click', () => {
            stateFilter = btn.dataset.filter;
            document.querySelectorAll('[data-filter]').forEach((b) => b.classList.toggle('is-active', b === btn));
            render();
        });
    });

    let filterTimer;
    $('acervoFilter').addEventListener('input', (ev) => {
        clearTimeout(filterTimer);
        filterTimer = setTimeout(() => { query = fold(ev.target.value.trim()); render(); }, 150);
    });

    document.querySelector('[data-bulk="expand"]').addEventListener('click', () => {
        (function walk(node) {
            for (const child of node.folders.values()) { expanded.add(child.path); walk(child); }
        })(root);
        render();
    });
    document.querySelector('[data-bulk="collapse"]').addEventListener('click', () => {
        expanded.clear();
        render();
    });

    $('acervoReset').addEventListener('click', () => { resetDesired(); render(); });

    // -- revisar / aplicar --------------------------------------------------
    async function post(body) {
        const res = await fetch(API, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
            body: JSON.stringify(body),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
        return data;
    }

    function planSection(label, items, cls) {
        if (!items.length) return null;
        const sec = el('section', `acv-plan ${cls}`);
        sec.append(el('h3', null, `${label} (${items.length})`));
        const list = el('ul');
        for (const item of items) list.append(el('li', null, item.path ? `${item.title} — ${item.path}` : item.title));
        sec.append(list);
        return sec;
    }

    $('acervoReview').addEventListener('click', async (ev) => {
        const btn = ev.currentTarget;
        btn.disabled = true;
        try {
            pending = payload();
            const plan = await post({ ...pending, dry_run: true });
            const box = $('acervoPlan');
            box.replaceChildren(...[
                planSection('Importar e publicar', plan.import, 'acv-plan-add'),
                planSection('Reexibir', plan.show, 'acv-plan-add'),
                planSection('Ocultar do site', plan.hide, 'acv-plan-remove'),
            ].filter(Boolean));
            if (!box.childElementCount) box.append(el('p', null, 'Nada a mudar — o site já está assim.'));
            modal.hidden = false;
            $('acervoApply').focus();
        } catch (err) {
            alert(`Não deu para revisar: ${err.message}`);
        } finally {
            btn.disabled = false;
        }
    });

    const closeModal = () => { modal.hidden = true; pending = null; };
    $('acervoCancel').addEventListener('click', closeModal);
    modal.addEventListener('click', (ev) => { if (ev.target === modal) closeModal(); });
    document.addEventListener('keydown', (ev) => { if (ev.key === 'Escape' && !modal.hidden) closeModal(); });

    $('acervoApply').addEventListener('click', async (ev) => {
        const btn = ev.currentTarget;
        btn.disabled = true;
        try {
            const done = await post({ ...pending, dry_run: false });
            closeModal();
            await load();
            const n = done.import.length + done.show.length + done.hide.length;
            $('acervoSummary').textContent = '';
            treeEl.insertAdjacentElement('beforebegin', flash(`✓ ${plural(n, 'mudança aplicada', 'mudanças aplicadas')} no site.`));
        } catch (err) {
            alert(`Não deu para aplicar: ${err.message}`);
        } finally {
            btn.disabled = false;
        }
    });

    function flash(text) {
        document.querySelectorAll('.xpo-acervo-flash').forEach((n) => n.remove());
        const node = el('p', 'xpo-acervo-flash', text);
        setTimeout(() => node.remove(), 6000);
        return node;
    }

    window.addEventListener('beforeunload', (ev) => {
        if (!bar.hidden) { ev.preventDefault(); ev.returnValue = ''; }
    });

    // -- carga ----------------------------------------------------------------
    function resetDesired() {
        desired.clear();
        files.forEach((f) => desired.set(f.path, isOn(f)));
        desiredPost.clear();
        orphans.forEach((o) => desiredPost.set(o.id, o.state === 'on'));
    }

    async function load() {
        const res = await fetch(API, { headers: { Accept: 'application/json' } });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        files = data.files;
        orphans = data.orphans;
        resetDesired();
        buildTree();
        render();
    }

    load().catch((err) => {
        treeEl.replaceChildren(el('p', 'xpo-acervo-empty', `Falha ao carregar o acervo: ${err.message}`));
    });
})();
