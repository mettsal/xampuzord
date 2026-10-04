"""Painel do acervo (/admin/acervo): quais arquivos de poesia/ estão no site.

Cada arquivo do acervo está em um de três estados:
  on      -> tem post visível
  hidden  -> tem post, mas oculto (Post.hidden)
  new     -> nunca virou post (chegou do Drive depois, ou ficou de fora)

O painel manda só as MUDANÇAS em relação ao que carregou (incluir/excluir
caminhos e ids), nunca o estado inteiro: assim um poema publicado pelo
tools/publish_inbox.py no meio da sessão não é ocultado por tabela.

Incluir 'new' importa o arquivo (mesmas regras do tools/import_posts.py:
título, data, tags e colisões); incluir 'hidden' reexibe; excluir oculta.
Nada é apagado — views, curtidas e comentários ficam no post oculto.

Importado só de dentro das rotas (lazy), porque tools/import_posts.py
importa o próprio app.
"""
import json
from collections import defaultdict
from pathlib import Path

from app import app, db, Post, process_tags, decrement_tags, increment_tags
from tools.import_posts import body_html_for, collect_poems, free_title

ACERVO_ROOT = Path(app.root_path) / 'poesia'
DATE_MANIFEST = Path(app.root_path) / 'tools' / 'dates.json'


def scan():
    """Poemas importáveis do acervo (variantes e duplicatas já resolvidas)."""
    if not ACERVO_ROOT.is_dir():
        return [], []
    manifest = None
    if DATE_MANIFEST.is_file():
        manifest = json.loads(DATE_MANIFEST.read_text(encoding='utf-8'))
    return collect_poems(ACERVO_ROOT, manifest)


def link_orphans(poems):
    """Liga posts sem source_path ao arquivo de mesmo conteúdo. Idempotente.

    Posts importados antes de existir Post.source_path, ou criados pelo editor
    com texto idêntico a um arquivo. Corpo editado no site depois do import
    não casa — esses continuam como 'posts sem arquivo' no painel.
    """
    linked = {path for (path,) in db.session.query(Post.source_path)
              .filter(Post.source_path.isnot(None))}
    by_body = defaultdict(list)
    for poem in poems:
        if poem.rel.as_posix() not in linked:
            by_body[body_html_for(poem.text)].append(poem)
    if not by_body:
        return 0
    count = 0
    for post in Post.query.filter(Post.source_path.is_(None)).order_by(Post.id):
        candidates = by_body.get(post.body_html)
        if not candidates:
            continue
        poem = next((c for c in candidates if c.title == post.title), candidates[0])
        candidates.remove(poem)
        post.source_path = poem.rel.as_posix()
        count += 1
    if count:
        db.session.commit()
    return count


def tree_state():
    """Estado de todos os arquivos + posts sem arquivo, para o painel."""
    poems, notes = scan()
    link_orphans(poems)
    posts = {p.source_path: p for p in
             db.session.query(Post.id, Post.title, Post.hidden, Post.source_path, Post.created_at)
             .filter(Post.source_path.isnot(None))}

    files = []
    for poem in poems:
        key = poem.rel.as_posix()
        post = posts.pop(key, None)
        files.append({
            'path': key,
            'title': post.title if post else poem.title,
            'date': (post.created_at if post else poem.created_at).date().isoformat(),
            'post_id': post.id if post else None,
            'state': 'new' if post is None else ('hidden' if post.hidden else 'on'),
        })

    # Sobrou em `posts`: arquivo de origem sumiu do acervo. Somam-se os do editor.
    orphan_rows = list(posts.values()) + (
        db.session.query(Post.id, Post.title, Post.hidden, Post.source_path, Post.created_at)
        .filter(Post.source_path.is_(None)).all())
    orphans = sorted(({'id': p.id, 'title': p.title, 'source_path': p.source_path,
                       'state': 'hidden' if p.hidden else 'on'} for p in orphan_rows),
                     key=lambda o: o['id'], reverse=True)
    return {'files': files, 'orphans': orphans, 'left_out': len(notes)}


def _show(post, changes):
    if post.hidden:
        post.hidden = False
        increment_tags(post.tags)
        changes['show'].append({'id': post.id, 'title': post.title})


def _hide(post, changes):
    if not post.hidden:
        post.hidden = True
        decrement_tags(post.tags)
        changes['hide'].append({'id': post.id, 'title': post.title})


def apply_changes(include=(), exclude=(), include_posts=(), exclude_posts=(),
                  author=None, dry_run=False):
    """Aplica as mudanças do painel. Em dry_run nada é gravado (rollback)."""
    poems, _notes = scan()
    link_orphans(poems)
    by_key = {poem.rel.as_posix(): poem for poem in poems}
    changes = {'import': [], 'show': [], 'hide': [], 'ignored': []}

    for key in dict.fromkeys(include):  # dedup preservando ordem
        poem = by_key.get(key)
        if poem is None:
            changes['ignored'].append(key)
            continue
        post = Post.query.filter_by(source_path=key).first()
        if post is not None:
            _show(post, changes)
            continue
        body_html = body_html_for(poem.text)
        same = Post.query.filter_by(title=poem.title, source_path=None).first()
        if same is not None and same.body_html == body_html:
            same.source_path = key  # já estava no site sem vínculo: adota
            _show(same, changes)
            continue
        post = Post(title=free_title(poem.title), body_html=body_html,
                    tags=process_tags(', '.join(poem.tag_values)),
                    author_id=author.id, created_at=poem.created_at, source_path=key)
        db.session.add(post)
        db.session.flush()  # free_title do próximo precisa enxergar este
        changes['import'].append({'id': post.id, 'title': post.title, 'path': key})

    for key in dict.fromkeys(exclude):
        post = Post.query.filter_by(source_path=key).first()
        if post is None:
            changes['ignored'].append(key)
        else:
            _hide(post, changes)

    for post_id in dict.fromkeys(include_posts):
        post = db.session.get(Post, int(post_id))
        if post is not None:
            _show(post, changes)
    for post_id in dict.fromkeys(exclude_posts):
        post = db.session.get(Post, int(post_id))
        if post is not None:
            _hide(post, changes)

    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()
    return changes
