#!/usr/bin/env python3
"""Publicação automática: poema jogado em `0_publicar/` no Drive vira post.

Roda logo depois do rclone em tools/drive_sync.sh (quando PUBLISH_INBOX=1 no
drive-sync.env) e também à mão:

    python tools/publish_inbox.py --dry-run
    DATABASE_URL=sqlite:////caminho/copia.db python tools/publish_inbox.py

Regras:
  - Lê .txt/.md/sem-extensão de `poesia/0_publicar/` (subpastas incluídas).
    Mesma leitura do tools/import_posts.py: UTF-16 do Notepad, CRLF, linhas
    em branco iniciais, html.escape + <pre><code> (sem bleach).
  - Título = nome do arquivo sem o sufixo de data ("caveira-16-01-25" ->
    "caveira"); nome inutilizável -> primeira linha do poema.
  - Data do post = AGORA (é publicação: o poema entra no topo do grid).
  - Tags: subpastas dentro de 0_publicar + ano (do sufixo de data no nome,
    senão o ano corrente).
  - Ledger em instance/publish_ledger.json, seção "poemas"
    (caminho -> sha256 + post_id):
      * arquivo já publicado e igual        -> nada;
      * arquivo já publicado e editado      -> atualiza o corpo do post;
      * post apagado no site                -> NÃO republica (respeita a
                                               remoção);
      * arquivo novo com título já existente e mesmo texto -> adota o post
        existente (não duplica); texto diferente -> sufixo romano ("ii"…).
  - Só grava se o arquivo estiver estável (o rclone já filtra com --min-age).
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from import_posts import (  # noqa: E402
    CONTENT_EXTENSIONS, JUNK_NAMES, TAG_MAX, TITLE_MAX,
    app, db, Post, process_tags, utcnow,
    body_html_for, decode_bytes, first_line_title, free_title, resolve_author,
    split_date_suffix, strip_leading_blank_lines,
)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INBOX = ROOT / 'poesia' / '0_publicar'
DEFAULT_LEDGER = ROOT / 'instance' / 'publish_ledger.json'
STATUS_FILE = ROOT / 'instance' / 'publish_status.json'  # lido pelo painel /admin → Site

# O que esta execução fez, para o status do painel.
RUN = {'published': [], 'updated': []}


def load_ledger(path: Path) -> dict:
    if path.is_file():
        return json.loads(path.read_text(encoding='utf-8'))
    return {}


def save_ledger(path: Path, ledger: dict) -> None:
    """Escrita atômica: nunca deixa o ledger pela metade."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True),
                   encoding='utf-8')
    os.replace(tmp, path)


def read_poem(path: Path):
    """Texto normalizado do poema, ou None se binário/vazio."""
    text = decode_bytes(path.read_bytes())
    if text is None:
        return None
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    if not text.strip():
        return None
    return strip_leading_blank_lines(text)


def tags_for(rel: Path, filename_date) -> str:
    values = [comp.strip().replace(',', ' ')[:TAG_MAX] for comp in rel.parent.parts]
    values.append(str((filename_date or datetime.now()).year))
    seen, unique = set(), []
    for value in values:
        if value and value.lower() not in seen:
            seen.add(value.lower())
            unique.append(value)
    return ', '.join(unique)


def main() -> int:
    parser = argparse.ArgumentParser(description='Publica poemas de poesia/0_publicar.')
    parser.add_argument('--inbox', default=str(DEFAULT_INBOX))
    parser.add_argument('--ledger', default=str(DEFAULT_LEDGER))
    parser.add_argument('--author', default=None, help='Username (padrão: primeiro admin).')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    inbox, ledger_path = Path(args.inbox), Path(args.ledger)
    if not inbox.is_dir():
        print(f'publish_inbox: {inbox} não existe ainda, nada a fazer')
        return 0

    # source_path é relativo a poesia/ (o painel /admin/acervo usa a mesma base)
    try:
        prefix = inbox.resolve().relative_to(ROOT / 'poesia').as_posix() + '/'
    except ValueError:
        prefix = None
    full_ledger = load_ledger(ledger_path)
    ledger = full_ledger.setdefault('poemas', {})
    changed = False

    with app.app_context():
        author = resolve_author(args.author)
        if not author:
            print('❌ publish_inbox: nenhum autor/admin no banco')
            return 1

        for path in sorted(inbox.rglob('*')):
            if (not path.is_file() or path.name.lower() in JUNK_NAMES
                    or path.suffix.lower() not in CONTENT_EXTENSIONS):
                continue
            rel = path.relative_to(inbox)
            key = rel.as_posix()
            text = read_poem(path)
            if text is None:
                print(f'⬜ ignora    {key} (vazio ou binário)')
                continue
            digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
            entry = ledger.get(key)

            if entry and entry['sha256'] == digest:
                continue  # já publicado, sem mudança

            if entry:
                post = db.session.get(Post, entry['post_id'])
                if post is None:
                    print(f'🗑️  ignora    {key} (post #{entry["post_id"]} foi apagado no site)')
                    entry['sha256'] = digest
                    changed = True
                    continue
                print(f'♻️  atualiza  {key} -> #{post.id} "{post.title}"')
                if not args.dry_run:
                    post.body_html = body_html_for(text)
                    post.updated_at = utcnow()
                    db.session.commit()
                    entry['sha256'] = digest
                    changed = True
                    RUN['updated'].append(post.title)
                continue

            title, filename_date = split_date_suffix(path.stem)
            if not title.strip(' -_.') or path.stem.startswith('.'):
                title = first_line_title(text) or title or path.stem
            title = title[:TITLE_MAX]
            body_html = body_html_for(text)

            same = Post.query.filter_by(title=title).first()
            if same and same.body_html == body_html:
                print(f'🔗 adota     {key} -> #{same.id} "{same.title}" (já estava no site)')
                if not args.dry_run:
                    if prefix and not same.source_path:
                        same.source_path = prefix + key
                        db.session.commit()
                    ledger[key] = {'sha256': digest, 'post_id': same.id}
                    changed = True
                continue

            final_title = free_title(title)
            tags = tags_for(rel, filename_date)
            print(f'➕ publica   {key} -> "{final_title}" [{tags}]')
            if args.dry_run:
                continue
            post = Post(title=final_title, body_html=body_html,
                        tags=process_tags(tags), author_id=author.id,
                        created_at=utcnow(),
                        source_path=prefix + key if prefix else None)
            db.session.add(post)
            db.session.commit()
            ledger[key] = {'sha256': digest, 'post_id': post.id}
            changed = True
            RUN['published'].append(post.title)
            print(f'   ✅ post #{post.id}')

    if changed and not args.dry_run:
        save_ledger(ledger_path, full_ledger)
    return 0


def write_status(**fields):
    """Última execução (hora, o que publicou, erro) para o painel admin."""
    try:
        save_ledger(STATUS_FILE, {'at': datetime.now().isoformat(timespec='seconds'), **RUN, **fields})
    except OSError:
        pass


if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    try:
        code = main()
    except Exception as exc:
        if not dry_run:
            write_status(ok=False, error=f'{type(exc).__name__}: {str(exc).splitlines()[0]}'[:300])
        raise
    if not dry_run:
        write_status(ok=code == 0)
    sys.exit(code)
