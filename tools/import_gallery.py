#!/usr/bin/env python3
"""Importa imagens de `graphics/galeria/` para a página /galeria.

Legendas em `graphics/galeria/subtitles.json` (opcional; vazio vale):

    {
      "IMG_20260924_161629.jpg": {"title": "caveira coroada", "caption": "acrílica, 2026"}
    }

Sem entrada no JSON, o título é o nome do arquivo sem extensão.

Idempotente: o ledger (instance/publish_ledger.json, seção "galeria") liga o
sha256 de cada imagem ao GalleryItem criado. Rodar de novo só cria imagens
novas e atualiza título/legenda das já publicadas se o JSON mudou desde o
último import (edição feita pelo site não é desfeita). Imagem apagada no site
não volta. O JSON só vale quando este script roda — reiniciar o serviço não o lê.

    python tools/import_gallery.py --dry-run
    DATABASE_URL=sqlite:////caminho/copia.db python tools/import_gallery.py
"""
import argparse
import hashlib
import json
import shutil
import sys
import uuid
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from import_posts import app, db, resolve_author  # noqa: E402
from app import GalleryItem  # noqa: E402
from publish_inbox import DEFAULT_LEDGER, ROOT, load_ledger, save_ledger  # noqa: E402

DEFAULT_DIR = ROOT / 'graphics' / 'galeria'
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}


def load_subtitles(path: Path) -> dict:
    if path.is_file() and path.read_text(encoding='utf-8').strip():
        return json.loads(path.read_text(encoding='utf-8'))
    return {}


def main() -> int:
    parser = argparse.ArgumentParser(description='Importa graphics/galeria/ para /galeria.')
    parser.add_argument('--dir', default=str(DEFAULT_DIR))
    parser.add_argument('--ledger', default=str(DEFAULT_LEDGER))
    parser.add_argument('--author', default=None, help='Username (padrão: primeiro admin).')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    src_dir, ledger_path = Path(args.dir), Path(args.ledger)
    subtitles = load_subtitles(src_dir / 'subtitles.json')
    ledger = load_ledger(ledger_path)
    seen = ledger.setdefault('galeria', {})
    applied = ledger.setdefault('galeria_meta', {})  # sha256 -> [título, legenda] do JSON já aplicados
    changed = False

    with app.app_context():
        author = resolve_author(args.author)
        if not author:
            print('❌ nenhum autor/admin no banco')
            return 1
        upload_dir = Path(app.root_path) / app.config['UPLOAD_FOLDER']

        for path in sorted(src_dir.iterdir()):
            if path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            try:
                with Image.open(path) as img:
                    img.verify()
            except Exception:
                print(f'🚫 não é imagem: {path.name}')
                continue

            meta = subtitles.get(path.name, {})
            title = (meta.get('title') or path.stem).strip()[:200]
            caption = (meta.get('caption') or '').strip()[:2000] or None
            digest = hashlib.sha256(path.read_bytes()).hexdigest()

            if digest in seen:
                item = db.session.get(GalleryItem, seen[digest])
                if item is None:
                    continue  # apagada no site: respeita
                # só reaplica quando o JSON mudou desde o último import: edição
                # feita pelo site (/galeria, "editar") não é desfeita
                if applied.get(digest) == [title, caption]:
                    continue
                if (item.title, item.caption) != (title, caption):
                    print(f'♻️  legenda   {path.name} -> #{item.id} "{title}"')
                    if not args.dry_run:
                        item.title, item.caption = title, caption
                        db.session.commit()
                if not args.dry_run:
                    applied[digest] = [title, caption]
                    changed = True
                continue

            print(f'➕ galeria   {path.name} -> "{title}"')
            if args.dry_run:
                continue
            upload_dir.mkdir(parents=True, exist_ok=True)
            filename = f'{uuid.uuid4().hex}_{path.name}'
            shutil.copyfile(path, upload_dir / filename)
            item = GalleryItem(title=title, caption=caption, author_id=author.id,
                               image_path=f'uploads/teasers/{filename}')
            db.session.add(item)
            db.session.commit()
            seen[digest] = item.id
            applied[digest] = [title, caption]
            changed = True
            print(f'   ✅ item #{item.id}')

    if changed and not args.dry_run:
        save_ledger(ledger_path, ledger)
    return 0


if __name__ == '__main__':
    sys.exit(main())
