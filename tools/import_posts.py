#!/usr/bin/env python3
"""Importador de posts do Xampu Para Ossos.

Popula o blog a partir do acervo de poesia em `poesia/` (.txt, .md e arquivos
sem extensão), sem passar pelo editor web. Roda direto sobre o app context
(não usa HTTP), portanto é imune ao CSRF e ao rate-limiting da aplicação.

O acervo foi copiado do Windows em 02/07/2026 e a cópia achatou mtime e birth
time de TODOS os arquivos — metadados de filesystem não dizem nada aqui.
As datas vêm, em ordem de prioridade:

  1. Sufixo de data no nome do arquivo, dd-mm-aa ou dd-mm-aaaa, separador
     opcional: "caveira-16-01-25" -> 2025-01-16 (título "caveira");
     "mundolesado10-09-25" também vale. Sufixo que não é data de verdade
     (mês 19 etc.) fica no título.
  2. Componente de ano no caminho:
       poesia/2018/…       -> 2018-01-01
       poesia/2016-2017/…  -> 2016-01-01  (primeiro ano do range)
       poesia/sub-2015/…   -> 2014-01-01  ("antes de 2015")
  3. Sem sinal nenhum -> sentinela 2000-01-01 (fundo do grid cronológico,
     claramente "sem data"; re-datável depois pelo editor).

  Arquivos com a mesma data-base ganham +1 segundo cada, em ordem de
  caminho, para a ordenação do grid ser estável entre execuções.

Tags: cada pasta do caminho vira tag — "2019" -> year; "2016-2017" -> DUAS
tags year (2016 e 2017); "english", "prosa", "sub-2015"… -> genre. Arquivos
na raiz ficam sem tags.

Conteúdo: texto cru -> html.escape() -> <pre><code>…</code></pre>. NÃO usa
bleach de propósito: o strip=True comeria "<coisa>" da poesia visual; texto
escapado não carrega HTML nenhum e preserva o espaçamento byte-a-byte.

Colisões de título (o acervo tem dezenas de títulos repetidos):
  a. mesmo diretório + mesmo nome com extensões diferentes = variantes do
     mesmo poema -> fica só a melhor (.md > .txt > sem extensão);
  b. conteúdo idêntico (após normalizar fim-de-linha) = duplicata -> importa
     a primeira (ordem de caminho) e pula as demais;
  c. conteúdo diferente = poemas distintos -> sufixo romano em ordem de
     caminho: "prosa", "prosa ii", "prosa iii", …

Dedup contra o banco: por título final. Se já existe, pula — a menos que
--update seja passado (corpo, data e tags são atualizados, decrementando as
tags antigas como a rota de edição faz).

--wipe-seed apaga os posts de exemplo "Digital Dreams #N" do `flask seed-db`,
ajustando os contadores de Tag.

Exemplos:
    python tools/import_posts.py --dry-run
    python tools/import_posts.py --wipe-seed
    python tools/import_posts.py --update
    DATABASE_URL=sqlite:////caminho/copia.db python tools/import_posts.py
"""
import argparse
import html
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

# Permite rodar como `python tools/import_posts.py` a partir da raiz do projeto:
# garante que o diretório do app (pai de tools/) esteja no sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Importa os singletons do app (mesmo padrão de run.py e do bloco __main__).
from app import app, db, Post, User, process_tags, decrement_tags  # noqa: E402

CONTENT_EXTENSIONS = {'.txt', '.md', ''}  # '' = sem extensão (acervo tem ~200, todos texto)
JUNK_NAMES = {'desktop.ini', 'readme', 'readme.txt', 'readme.md', 'readme.txt.txt'}
EXT_PRIORITY = {'.md': 0, '.txt': 1, '': 2}  # menor = melhor variante
SENTINEL_DATE = datetime(2000, 1, 1)
TITLE_MAX = 200  # Post.title é String(200)
TAG_MAX = 50     # Tag.name é String(50)
ROMAN = ('ii', 'iii', 'iv', 'v', 'vi', 'vii', 'viii', 'ix', 'x',
         'xi', 'xii', 'xiii', 'xiv', 'xv', 'xvi', 'xvii', 'xviii', 'xix', 'xx')

# Sufixo de data no nome: caveira-16-01-25 / prosa_05_07_2021 / mundolesado10-09-25
_DATE_SUFFIX = re.compile(r'[-_ ]?(\d{1,2})[-_.](\d{1,2})[-_.](\d{2}|\d{4})$')
_YEAR = re.compile(r'\d{4}')
_YEAR_RANGE = re.compile(r'(\d{4})\s*[-–]\s*(\d{4})')
_SUB_YEAR = re.compile(r'sub[-_ ](\d{4})', re.IGNORECASE)


@dataclass
class Poem:
    path: Path                 # caminho absoluto do arquivo
    rel: Path                  # caminho relativo à raiz do acervo
    title: str                 # título final (pós-desambiguação)
    text: str                  # conteúdo com fim-de-linha normalizado (\n)
    created_at: datetime = SENTINEL_DATE
    date_source: str = 'sentinela'   # 'nome' | 'pasta' | 'sentinela'
    tag_values: tuple = ()
    renamed_from: str = ''           # título original, se ganhou sufixo romano


def split_date_suffix(stem: str):
    """(título, datetime|None) — só remove o sufixo do título se for data válida."""
    m = _DATE_SUFFIX.search(stem)
    if m:
        day, month, year = (int(g) for g in m.groups())
        if year < 100:
            year += 2000
        if 1990 <= year <= 2035:
            try:
                when = datetime(year, month, day)
            except ValueError:  # mês 19, dia 32, 30/02…
                when = None
            if when is not None:
                title = stem[:m.start()].strip(' -_')
                return (title or stem.strip(' -_')), when
    return stem.strip(' -_'), None


def year_from_component(name: str):
    """'2018' -> 2018 | '2016-2017' -> 2016 | 'sub-2015' -> 2014 | senão None."""
    name = name.strip()
    if _YEAR.fullmatch(name):
        return int(name)
    m = _YEAR_RANGE.fullmatch(name)
    if m:
        return int(m.group(1))
    m = _SUB_YEAR.fullmatch(name)
    if m:
        return int(m.group(1)) - 1
    return None


def base_date_for(rel: Path, filename_date):
    """Cadeia de prioridade da data; retorna (datetime, origem)."""
    if filename_date is not None:
        return filename_date, 'nome'
    year = None
    for comp in rel.parent.parts:  # o componente mais profundo vence
        y = year_from_component(comp)
        if y is not None:
            year = y
    if year is not None:
        return datetime(year, 1, 1), 'pasta'
    return SENTINEL_DATE, 'sentinela'


def tag_values_for(rel: Path) -> tuple:
    """Cada pasta do caminho vira tag; range de anos vira duas tags de ano."""
    values, seen = [], set()
    for comp in rel.parent.parts:
        comp = comp.strip()
        m = _YEAR_RANGE.fullmatch(comp)
        parts = [m.group(1), m.group(2)] if m else [comp.replace(',', ' ')[:TAG_MAX]]
        for value in parts:
            if value and value.lower() not in seen:
                seen.add(value.lower())
                values.append(value)
    return tuple(values)


def decode_bytes(raw: bytes):
    """Texto do arquivo, ou None se for binário de verdade.

    O Notepad do Windows salvou dezenas de .txt do acervo como UTF-16 (com BOM
    FF FE e um byte NUL a cada dois) — o BOM decide antes do sniff de binário.
    Depois: utf-8 (com/sem BOM) -> cp1252 (Windows) -> latin-1 (nunca falha).
    """
    if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
        try:
            return raw.decode('utf-16')
        except UnicodeDecodeError:
            return None
    if b'\x00' in raw[:8192]:
        return None
    for encoding in ('utf-8-sig', 'cp1252'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode('latin-1')


def body_html_for(text: str) -> str:
    """Escapa o texto cru e embrulha em <pre><code>, preservando byte-a-byte."""
    return f'<pre><code>{html.escape(text)}</code></pre>'


def first_line_title(text: str) -> str:
    """Primeira linha não vazia do poema — para arquivos sem nome utilizável."""
    for line in text.splitlines():
        line = ' '.join(line.split()).strip(' -_')
        if line and re.search(r'\w', line):
            return line[:80]
    return ''


def resolve_author(username):
    """Autor: o informado por --author, senão o primeiro admin."""
    if username:
        return User.query.filter_by(username=username).first()
    return User.query.filter_by(is_admin=True).first()


def collect_poems(root: Path):
    """Lê o acervo e resolve variantes, duplicatas e colisões de título.

    Puro: não toca no banco. Retorna (poemas prontos, notas do que ficou fora).
    """
    notes = []

    # -- coleta bruta -------------------------------------------------------
    candidates = []
    for path in sorted(root.rglob('*')):
        if not path.is_file():
            continue
        if path.name.lower() in JUNK_NAMES:
            continue
        if path.suffix.lower() not in CONTENT_EXTENSIONS:
            continue
        raw = path.read_bytes()
        rel = path.relative_to(root)
        text = decode_bytes(raw)
        if text is None:
            notes.append(f'🚫 binário   {rel}')
            continue
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        if not text.strip():
            notes.append(f'⬜ vazio     {rel}')
            continue
        candidates.append((path, rel, text))

    # -- (a) variantes: mesmo diretório + mesmo nome, extensões diferentes ---
    groups = defaultdict(list)
    for path, rel, text in candidates:
        groups[(str(rel.parent).lower(), path.stem.lower())].append((path, rel, text))
    survivors = []
    for group in groups.values():
        group.sort(key=lambda item: EXT_PRIORITY[item[0].suffix.lower()])
        best = group[0]
        for _, rel, _text in group[1:]:
            notes.append(f'🔀 variante  {rel}  (fica {best[1].name})')
        survivors.append(best)
    survivors.sort(key=lambda item: str(item[1]))

    # -- título, data e tags de cada sobrevivente ----------------------------
    poems = []
    for path, rel, text in survivors:
        title, filename_date = split_date_suffix(path.stem)
        # Nome inutilizável ('-----', '.txt'…): o título vem da 1ª linha do poema.
        if not title.strip(' -_.') or path.stem.startswith('.'):
            title = first_line_title(text) or title or path.stem
        base, source = base_date_for(rel, filename_date)
        poems.append(Poem(path=path, rel=rel, title=title[:TITLE_MAX], text=text,
                          created_at=base, date_source=source,
                          tag_values=tag_values_for(rel)))

    # -- (b) duplicatas e (c) mesmo título com conteúdo distinto -------------
    by_original = defaultdict(list)  # título original -> poemas já aceitos
    taken = set()                    # todos os títulos finais (lowercase)
    final = []
    for poem in poems:
        original_key = poem.title.lower()
        twin = next((kept for kept in by_original[original_key]
                     if kept.text.strip() == poem.text.strip()), None)
        if twin is not None:
            notes.append(f'🔁 duplicata {poem.rel}  (igual a {twin.rel})')
            continue
        by_original[original_key].append(poem)
        if original_key in taken:
            base_title = poem.title
            for suffix in list(ROMAN) + [str(n) for n in range(21, 100)]:
                trial = f'{base_title[:TITLE_MAX - len(suffix) - 1]} {suffix}'
                if trial.lower() not in taken:
                    poem.renamed_from, poem.title = base_title, trial
                    break
        taken.add(poem.title.lower())
        final.append(poem)

    # -- +1s por arquivo dentro da mesma data-base (ordenação estável) -------
    seq = Counter()
    for poem in final:
        base = poem.created_at
        poem.created_at = base + timedelta(seconds=seq[base])
        seq[base] += 1

    return final, notes


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
    parser.add_argument('--wipe-seed', action='store_true',
                        help="Apaga os posts de exemplo 'Digital Dreams #N' do seed-db.")
    args = parser.parse_args()

    root = Path(args.dir)
    if not root.is_dir():
        print(f"❌ Pasta não encontrada: {root.resolve()}")
        return 1

    poems, notes = collect_poems(root)

    with app.app_context():
        author = resolve_author(args.author)
        if not author:
            if args.author:
                print(f"❌ Autor '{args.author}' não encontrado. Rode 'flask list-users'.")
            else:
                print("❌ Nenhum admin no banco. Rode 'flask seed-db' ou 'flask make-admin'.")
            return 1

        # Não vazar credenciais caso o banco um dia seja postgres com senha na URL.
        db_uri = re.sub(r'//[^@/]+@', '//***@', app.config['SQLALCHEMY_DATABASE_URI'])

        print(f"✍️  Autor: {author.username} (id={author.id})")
        print(f"📂 Lendo de: {root.resolve()}")
        print(f"🗄️  Banco: {db_uri}")
        if args.dry_run:
            print("🔎 DRY-RUN: nada será gravado.")
        print()

        for note in notes:
            print(note)
        if notes:
            print()

        wiped = 0
        if args.wipe_seed:
            seeds = Post.query.filter(Post.title.like('Digital Dreams #%')).all()
            wiped = len(seeds)
            for seed in seeds:
                print(f"🧹 seed      apaga '{seed.title}'")
                if not args.dry_run:
                    decrement_tags(seed.tags)
                    db.session.delete(seed)
            if seeds:
                print()

        created = updated = skipped = 0
        date_sources = Counter()

        for poem in poems:
            date_sources[poem.date_source] += 1
            tag_note = f"  [{', '.join(poem.tag_values)}]" if poem.tag_values else ''
            rename_note = f"  (era '{poem.renamed_from}')" if poem.renamed_from else ''
            when = f"{poem.created_at.date()}·{poem.date_source}"

            existing = Post.query.filter_by(title=poem.title).first()
            if existing:
                if not args.update:
                    print(f"⏭️  pula     {poem.rel}  (título já existe: '{poem.title}')")
                    skipped += 1
                    continue
                print(f"♻️  atualiza {poem.rel}  -> '{poem.title}' ({when}){tag_note}{rename_note}")
                if not args.dry_run:
                    decrement_tags(existing.tags)
                    existing.tags = process_tags(', '.join(poem.tag_values))
                    existing.body_html = body_html_for(poem.text)
                    existing.created_at = poem.created_at
                    existing.updated_at = datetime.utcnow()
                updated += 1
            else:
                print(f"➕ cria     {poem.rel}  -> '{poem.title}' ({when}){tag_note}{rename_note}")
                if not args.dry_run:
                    db.session.add(Post(
                        title=poem.title,
                        body_html=body_html_for(poem.text),
                        tags=process_tags(', '.join(poem.tag_values)),
                        author_id=author.id,
                        created_at=poem.created_at,
                    ))
                created += 1

        if not args.dry_run:
            db.session.commit()

        kinds = Counter(note.split(maxsplit=1)[0] for note in notes)
        renamed = sum(1 for poem in poems if poem.renamed_from)
        print(f"\n✅ Concluído. Criados: {created} | Atualizados: {updated} | Pulados (banco): {skipped}"
              + (f" | Seed apagados: {wiped}" if args.wipe_seed else ''))
        print(f"   Fora por regra local: variantes {kinds['🔀']} | duplicatas {kinds['🔁']}"
              f" | binários {kinds['🚫']} | vazios {kinds['⬜']}")
        print(f"   Títulos desambiguados (sufixo romano): {renamed}")
        print(f"   Datas: nome-do-arquivo {date_sources['nome']} | pasta {date_sources['pasta']}"
              f" | sentinela-2000 {date_sources['sentinela']}")
        if args.dry_run:
            print("   (dry-run — rode de novo sem --dry-run para gravar)")

    return 0


if __name__ == '__main__':
    sys.exit(main())
