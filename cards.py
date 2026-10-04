"""Cartões de compartilhamento (og:image) — o poema inteiro, encaixado.

render_post_card(): 1200×630 nas cores do tema do poema. "Zoom completo": o
maior corpo de fonte em que o poema INTEIRO cabe — uma coluna enquanto for
legível, senão até 5 colunas (fluxo de jornal). Se nem no menor corpo couber,
corta a última linha visível com "…".

render_site_card(): o cartão padrão do site (logo + nome), gerado uma vez e
versionado em static/images/og-default.png (ver tools/make_share_images.py).

Pillow puro, sem rede. Fonte mono com cobertura de símbolos (◯ ☽ ◑ ● ◐).
"""
import hashlib
import html
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630
PAD = 56
GAP = 36            # entre colunas (até 3)
GAP_TIGHT = 20      # 4-5 colunas
MIN_SIZE, MAX_SIZE = 6, 30
READABLE = 16       # corpo mínimo para preferir uma coluna só
MAX_COLS = 5
LINE_HEIGHT = 1.3
CARD_VERSION = '3'  # muda o hash do cache quando o layout mudar
MAX_LINES = 600     # teto de trabalho: poema maior que isso é cortado no cartão

ROOT = Path(__file__).resolve().parent
LOGO_PATH = ROOT / 'static' / 'images' / 'logo-pixel.png'
FONT_CANDIDATES = [
    '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf',
    '/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf',
    '/usr/share/fonts/truetype/noto/NotoSansMono-Regular.ttf',
]
BOLD_CANDIDATES = [
    '/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf',
    '/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf',
    '/usr/share/fonts/truetype/noto/NotoSansMono-Bold.ttf',
]

# (fundo, texto, acento) — mesmas cores das .post-theme-* do style.css;
# fundo em gradiente = tupla de cores (diagonal 135°, como no CSS).
THEMES = {
    'inherit':   ('#f6f4ef', '#1c1c1c', '#ffee00'),
    'light':     ('#ffffff', '#000000', '#ffee00'),
    'dark':      ('#000000', '#ffffff', '#ffee00'),
    'cyberpunk': ('#1a0033', '#00ffff', '#ff00ff'),
    'matrix':    ('#000000', '#00ff00', '#00ff00'),
    'vaporwave': (('#ff6ec7', '#7b68ee', '#00d4ff'), '#ffffff', '#ff6ec7'),
    'noir':      ('#1a1a1a', '#e0e0e0', '#888888'),
    'sunset':    (('#ff4e50', '#f9d423'), '#ffffff', '#ff4e50'),
    'ocean':     ('#001f3f', '#7fdbff', '#39cccc'),
}


def _font(candidates, size):
    for path in candidates:
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def _rgb(color):
    color = color.lstrip('#')
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def _mix(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def _background(spec):
    """Cor sólida ou gradiente diagonal (calculado pequeno e ampliado)."""
    if isinstance(spec, str):
        return Image.new('RGB', (W, H), _rgb(spec))
    stops = [_rgb(c) for c in spec]
    small_w, small_h = 60, 32
    small = Image.new('RGB', (small_w, small_h))
    for x in range(small_w):
        for y in range(small_h):
            t = (x / (small_w - 1) + y / (small_h - 1)) / 2
            seg = min(int(t * (len(stops) - 1)), len(stops) - 2)
            local = t * (len(stops) - 1) - seg
            small.putpixel((x, y), _mix(stops[seg], stops[seg + 1], local))
    return small.resize((W, H), Image.BILINEAR)


def poem_text(body_html):
    """body_html -> texto do poema, espaçamento preservado."""
    text = re.sub(r'<br\s*/?>', '\n', body_html or '', flags=re.I)
    text = re.sub(r'</p\s*>', '\n\n', text, flags=re.I)
    text = html.unescape(re.sub(r'<[^>]+>', '', text))
    lines = [line.rstrip() for line in text.replace('\r', '').expandtabs(4).split('\n')]
    while lines and not lines[-1]:
        lines.pop()
    while lines and not lines[0]:
        lines.pop(0)
    return lines[:MAX_LINES]


def _wrap(lines, width):
    """Quebra linha maior que a coluna no último espaço (ou corta seco).

    Cada corte TEM de encurtar a linha: a continuação ganha 2 espaços de
    recuo, então um corte antes da coluna 3 não progrediria (loop infinito).
    """
    out = []
    for line in lines:
        while len(line) > width:
            indent = len(line) - len(line.lstrip(' '))
            cut = line.rfind(' ', max(indent + 1, 3), width + 1)
            if cut < 3:
                cut = width  # sem espaço útil: corte seco (width >= 8)
            out.append(line[:cut].rstrip())
            rest = line[cut:].lstrip()
            line = '  ' + rest if rest else ''
            if len(out) > MAX_LINES:
                return out
        out.append(line)
    return out


def _layout(lines, box_w, box_h, size, cols):
    """(linhas quebradas, linhas por coluna, largura da coluna) para um corpo/colunas."""
    gap = GAP if cols <= 3 else GAP_TIGHT
    col_w = (box_w - gap * (cols - 1)) / cols
    char_w = _font(FONT_CANDIDATES, size).getlength('M')
    wrapped = _wrap(lines, max(8, int(col_w // char_w)))
    return wrapped, int(box_h // round(size * LINE_HEIGHT)), col_w, gap


def fit(lines, box_w, box_h):
    """(tamanho, colunas, cabe_inteiro): o poema inteiro no maior corpo.

    Verso é unidade: primeiro só valem arranjos em que (quase) nenhuma linha
    precisa ser quebrada; quebrar verso só se não houver outro jeito. Uma
    coluna tem prioridade enquanto o corpo for legível (>= READABLE).
    """
    for max_broken in (max(1, len(lines) // 20), None):
        one = multi = None
        for size in range(MAX_SIZE, MIN_SIZE - 1, -1):
            for cols in range(1, MAX_COLS + 1):
                wrapped, rows, _col_w, _gap = _layout(lines, box_w, box_h, size, cols)
                if len(wrapped) > rows * cols:
                    continue
                if max_broken is not None and len(wrapped) - len(lines) > max_broken:
                    continue
                if cols == 1 and one is None:
                    one = (size, 1)
                elif cols > 1 and multi is None:
                    multi = (size, cols)
                break  # menos colunas possível neste corpo
            if one:
                break  # corpos menores só piorariam a coluna única
        if one and (one[0] >= READABLE or multi is None or multi[0] <= one[0]):
            return (*one, True)
        if multi:
            return (*multi, True)
    return MIN_SIZE, MAX_COLS, False


def _ellipsize(draw, text, font, max_w):
    if draw.textlength(text, font=font) <= max_w:
        return text
    while text and draw.textlength(text + '…', font=font) > max_w:
        text = text[:-1]
    return text.rstrip() + '…'


def _logo(height):
    logo = Image.open(LOGO_PATH).convert('RGBA')
    scale = height / logo.height
    return logo.resize((max(1, round(logo.width * scale)), height), Image.NEAREST)


def render_post_card(title, body_html, theme='inherit'):
    bg_spec, fg_hex, accent_hex = THEMES.get(theme or 'inherit', THEMES['inherit'])
    img = _background(bg_spec)
    draw = ImageDraw.Draw(img)
    fg, accent = _rgb(fg_hex), _rgb(accent_hex)
    bg_ref = _rgb(bg_spec if isinstance(bg_spec, str) else bg_spec[0])
    muted = _mix(fg, bg_ref, 0.45)

    # coluna da direita: logo em pixel art
    logo = _logo(219)
    logo_x = W - PAD - logo.width
    img.paste(logo, (logo_x, H - PAD - logo.height - 30), logo)

    # título + barra de acento (o "glow" amarelo do site)
    title_font = _font(BOLD_CANDIDATES, 34)
    title = _ellipsize(draw, ' '.join((title or '').split()), title_font, logo_x - PAD - 32)
    draw.text((PAD, PAD - 6), title, font=title_font, fill=fg)
    draw.rectangle((PAD, PAD + 42, PAD + 72, PAD + 47), fill=accent)

    # rodapé
    foot_font = _font(FONT_CANDIDATES, 15)
    draw.text((PAD, H - PAD - 4), 'XAMPU PARA OSSOS · xampuparaossos.com.br',
              font=foot_font, fill=muted, anchor='ls')

    # o poema, no maior corpo em que cabe inteiro
    box_x, box_y = PAD, PAD + 72
    box_w = logo_x - 32 - PAD
    box_h = H - PAD - 30 - box_y
    lines = poem_text(body_html) or ['']
    size, cols, whole = fit(lines, box_w, box_h)
    wrapped, rows, col_w, gap = _layout(lines, box_w, box_h, size, cols)
    if not whole:
        wrapped = wrapped[:rows * cols]
        wrapped[-1] = wrapped[-1][:max(0, len(wrapped[-1]) - 1)] + '…'
    font = _font(FONT_CANDIDATES, size)
    line_h = round(size * LINE_HEIGHT)
    for i, line in enumerate(wrapped):
        col, row = divmod(i, rows)
        draw.text((box_x + col * (col_w + gap), box_y + row * line_h), line, font=font, fill=fg)
    return img


def render_site_card():
    """Cartão padrão (home, galeria, sobre): logo grande + nome do site."""
    img = Image.new('RGB', (W, H), _rgb('#f6f4ef'))
    draw = ImageDraw.Draw(img)
    logo = _logo(438)
    img.paste(logo, (PAD + 40, (H - logo.height) // 2), logo)
    x = PAD + 40 + logo.width + 64
    draw.rectangle((x - 8, 250, x + 560, 318), fill=_rgb('#ffee00'))
    draw.text((x, 300), 'XAMPU PARA OSSOS', font=_font(BOLD_CANDIDATES, 56),
              fill=_rgb('#1c1c1c'), anchor='ls')
    draw.text((x, 372), 'poesia · xampuparaossos.com.br', font=_font(FONT_CANDIDATES, 24),
              fill=_rgb('#5a574f'), anchor='ls')
    return img


def card_path(cache_dir, post):
    """Arquivo em cache do cartão; o hash muda quando título/corpo/tema mudam."""
    digest = hashlib.sha256('\x00'.join(
        [CARD_VERSION, post.title or '', post.body_html or '', post.post_theme or '']
    ).encode()).hexdigest()[:12]
    return Path(cache_dir) / f'{post.id}-{digest}.png'


def ensure_card(cache_dir, post):
    """Gera (se preciso) e devolve o PNG do cartão; apaga versões antigas."""
    path = card_path(cache_dir, post)
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix('.tmp')
        render_post_card(post.title, post.body_html, post.post_theme).save(tmp, 'PNG', optimize=True)
        tmp.replace(path)
        for old in path.parent.glob(f'{post.id}-*.png'):
            if old != path:
                old.unlink(missing_ok=True)
    return path
