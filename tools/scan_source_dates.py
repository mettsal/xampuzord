"""Escaneia a pasta-fonte de poesia (ex. Google Drive montado como G:\\My Drive\\poesia)
e exporta um JSON com as datas de arquivo (ctime/mtime) do sistema de arquivos local.

Existe porque a cópia usada pelo import_posts.py chegou nesta VM com todos os
arquivos carimbados com a mesma mtime (a data da cópia/clone) — o filesystem
local não tem mais a data real de cada poema. Se a fonte original (Drive) ainda
preserva timestamps (no Windows, st_ctime é a data de criação do arquivo, não
"change time" como no Linux), este script roda **na máquina com acesso a essa
fonte** e o JSON resultante é copiado para esta VM, para uso com
`import_posts.py --date-manifest`.

Puro stdlib de propósito: precisa rodar em qualquer máquina (Windows/Mac/Linux)
sem instalar nada — não importa app.py nem depende do venv deste projeto.

Uso (na máquina com a pasta fonte):
    python scan_source_dates.py --dir "G:\\My Drive\\poesia" --out dates.json
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

CONTENT_EXTENSIONS = {'.txt', '.md', ''}
JUNK_NAMES = {'desktop.ini', 'readme', 'readme.txt', 'readme.md', 'readme.txt.txt'}


def scan(root: Path) -> dict:
    manifest = {}
    for path in sorted(root.rglob('*')):
        if not path.is_file():
            continue
        if path.name.lower() in JUNK_NAMES:
            continue
        if path.suffix.lower() not in CONTENT_EXTENSIONS:
            continue
        st = path.stat()
        rel = path.relative_to(root).as_posix()
        manifest[rel] = {
            'ctime': datetime.fromtimestamp(st.st_ctime).isoformat(),
            'mtime': datetime.fromtimestamp(st.st_mtime).isoformat(),
        }
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--dir', required=True, help='Pasta fonte a escanear (ex. G:\\My Drive\\poesia).')
    parser.add_argument('--out', default='dates.json', help='Arquivo JSON de saída (padrão: dates.json).')
    args = parser.parse_args()

    root = Path(args.dir)
    if not root.is_dir():
        print(f'❌ Pasta não encontrada: {root.resolve()}')
        return 1

    manifest = scan(root)
    Path(args.out).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'✅ {len(manifest)} arquivos escaneados em {root.resolve()}')
    print(f'📄 Manifesto salvo em: {Path(args.out).resolve()}')
    print('   Copie esse arquivo para a VM e use: python tools/import_posts.py --date-manifest dates.json')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
