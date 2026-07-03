#!/usr/bin/env python3
"""Importador de posts do Xampu Para Ossos.

Popula o blog a partir de arquivos de poesia (.txt/.md) numa pasta local,
sem passar pelo editor web. Roda direto sobre o app context (não usa HTTP),
portanto é imune ao CSRF da aplicação.

Estrutura de pastas esperada:

    poesia/{ano}/{slug}.txt      ->  título = "slug", ano = {ano}
    poesia/{slug}.txt            ->  título = "slug", data = mtime do arquivo

Regras de metadados (decididas com o dono do blog):
  - Título: nome do arquivo (sem extensão); um sufixo de data no nome, tipo
    "caveira-16-01-25", é removido do título.
  - Data (created_at): data de modificação do arquivo; se o arquivo estiver
    numa pasta com nome de ano (YYYY), o ANO passa a ser o da pasta.
  - Tags: vazias.  Fonte/tema: padrão do modelo (Consolas / inherit).
  - Conteúdo: texto CRU -> sanitize_html() -> embrulhado em <pre><code>,
    preservando byte-a-byte o espaçamento (a poesia é visual/concreta).

Dedup: por TÍTULO. Se já existe um post com aquele título, é pulado — a menos
que --update seja passado, aí o corpo e a data são atualizados.

Exemplos:
    python tools/import_posts.py --dry-run
    python tools/import_posts.py
    python tools/import_posts.py --dir poesia --update
    python tools/import_posts.py --author matheus
"""
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

# Permite rodar como `python tools/import_posts.py` a partir da raiz do projeto:
# garante que o diretório do app (pai de tools/) esteja no sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Importa os singletons do app (mesmo padrão de run.py e do bloco __main__).
from app import app, db, Post, User, sanitize_html  # noqa: E402

CONTENT_EXTENSIONS = {'.txt', '.md'}
# Sufixo de data no nome do arquivo: -16-01-25 / _16_01_2025 / -16.01.25
_DATE_SUFFIX = re.compile(r'[-_ ]\d{1,2}[-_.]\d{1,2}[-_.]\d{2,4}$')


def title_from_filename(path: Path) -> str:
    """Deriva o título a partir do nome do arquivo, removendo sufixo de data."""
    stem = path.stem
    cleaned = _DATE_SUFFIX.sub('', stem).strip(' -_')
    return cleaned or stem


def created_at_for(path: Path) -> datetime:
    """mtime do arquivo, com o ano sobrescrito pela pasta {YYYY} se houver."""
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    parent = path.parent.name
    if re.fullmatch(r'\d{4}', parent):
        year = int(parent)
        try:
            return mtime.replace(year=year)
        except ValueError:
            # ex.: 29/fev do mtime num ano não bissexto -> cai pro 1º de janeiro
            return datetime(year, 1, 1)
    return mtime


def read_text(path: Path) -> str:
    """Lê o arquivo preservando o conteúdo; tenta utf-8 e cai pra latin-1."""
    for encoding in ('utf-8', 'latin-1'):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding='utf-8', errors='replace')


def resolve_author(username: str | None) -> User | None:
    """Autor: o informado por --author, senão o primeiro admin."""
    if username:
        return User.query.filter_by(username=username).first()
    return User.query.filter_by(is_admin=True).first()


def iter_content_files(root: Path):
    """Todos os .txt/.md sob `root`, em ordem estável."""
    for path in sorted(root.rglob('*')):
        if path.is_file() and path.suffix.lower() in CONTENT_EXTENSIONS:
            yield path


def main() -> int:
    parser = argparse.ArgumentParser(description='Importa posts de poesia para o blog.')
    parser.add_argument('--dir', default='poesia',
                        help="Pasta raiz com os arquivos (padrão: 'poesia').")
    parser.add_argument('--author', default=None,
                        help='Username do autor (padrão: primeiro admin).')
    parser.add_argument('--update', action='store_true',
                        help='Atualiza posts já existentes (mesmo título) em vez de pular.')
    parser.add_argument('--dry-run', action='store_true',
                        help='Só mostra o que faria, sem gravar no banco.')
    args = parser.parse_args()

    root = Path(args.dir)
    if not root.is_dir():
        print(f"❌ Pasta não encontrada: {root.resolve()}")
        return 1

    with app.app_context():
        author = resolve_author(args.author)
        if not author:
            if args.author:
                print(f"❌ Autor '{args.author}' não encontrado. Rode 'flask list-users'.")
            else:
                print("❌ Nenhum admin no banco. Rode 'flask seed-db' ou 'flask make-admin'.")
            return 1

        print(f"✍️  Autor: {author.username} (id={author.id})")
        print(f"📂 Lendo de: {root.resolve()}")
        if args.dry_run:
            print("🔎 DRY-RUN: nada será gravado.\n")

        created = updated = skipped = 0

        for path in iter_content_files(root):
            title = title_from_filename(path)
            created_at = created_at_for(path)
            body_html = sanitize_html(read_text(path))
            existing = Post.query.filter_by(title=title).first()

            rel = path.relative_to(root)
            if existing:
                if not args.update:
                    print(f"⏭️  pula   {rel}  (título já existe: '{title}')")
                    skipped += 1
                    continue
                print(f"♻️  atualiza {rel}  -> '{title}' ({created_at.date()})")
                if not args.dry_run:
                    existing.body_html = body_html
                    existing.created_at = created_at
                    existing.updated_at = datetime.utcnow()
                updated += 1
            else:
                print(f"➕ cria    {rel}  -> '{title}' ({created_at.date()})")
                if not args.dry_run:
                    db.session.add(Post(
                        title=title,
                        body_html=body_html,
                        tags=[],
                        author_id=author.id,
                        created_at=created_at,
                    ))
                created += 1

        if not args.dry_run:
            db.session.commit()

        print(f"\n✅ Concluído. Criados: {created} | Atualizados: {updated} | Pulados: {skipped}")
        if args.dry_run:
            print("   (dry-run — rode de novo sem --dry-run para gravar)")

    return 0


if __name__ == '__main__':
    sys.exit(main())
