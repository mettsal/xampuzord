"""Texto limpo e medidas de um poema, + regra curto/longo.

`body_html` do acervo é `<pre><code>` com o texto escapado (ver import_posts.py);
posts do editor podem ter HTML de markdown. Aqui tudo vira texto puro.
"""
import html
import re

LONG_CUTOFF = 40            # linhas não vazias; > corte = longo (calibrar no histograma)
PROSE_TAGS = {'prosa'}      # prosa não entra na regra curto/longo
BLOCK_END = re.compile(r'</(p|div|li|h[1-6]|pre|blockquote)>|<br\s*/?>', re.I)
TAG = re.compile(r'<[^>]+>')


def clean_text(body_html):
    text = BLOCK_END.sub('\n', body_html or '')
    text = html.unescape(TAG.sub('', text))
    return '\n'.join(line.rstrip() for line in text.replace('\r', '').split('\n')).strip('\n')


def stats(body_html):
    text = clean_text(body_html)
    lines = [ln for ln in text.split('\n') if ln.strip()]
    stanzas = [s for s in re.split(r'\n\s*\n', text) if s.strip()]
    return {
        'text': text,
        'n_lines': len(lines),
        'n_words': len(text.split()),
        'n_stanzas': len(stanzas),
    }


def tag_values(tags):
    return {str(t.get('value', '')).lower() for t in tags or [] if isinstance(t, dict)}


def length_class(n_lines, tags=None, cutoff=LONG_CUTOFF):
    """'curto' | 'longo' | None (prosa ou vazio: fora da regra)."""
    if n_lines == 0 or tag_values(tags) & PROSE_TAGS:
        return None
    return 'longo' if n_lines > cutoff else 'curto'
