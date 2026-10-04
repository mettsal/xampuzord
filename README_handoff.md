# Handoff: Home (arquivo + mosaico) e Galeria — Xampu Para Ossos

Repo alvo: `mettsal/xampuzord` (Flask + Jinja + Tailwind + `static/css/style.css`).

## Overview
Redesign do cabeçalho/home e nova página **Galeria**:
- Home: ribbon de feed no topo, cabeçalho com novo logo, **lateral esquerda estilo Blogspot** (Arquivo em árvore Ano → Mês → Poemas + Marcadores com contagem) e o **mesmo mosaico de 3 colunas atual** no centro.
- Galeria: lista vertical de imagens (título → imagem → mini-card de legenda).

## About the Design Files
`Xampu Feed Options.dc.html` é uma **referência de design em HTML**, não código de produção. Recriar nos templates Jinja existentes (`templates/base.html`, `templates/index.html`, nova `templates/galeria.html`), usando Tailwind/`style.css` e os padrões do repo. No arquivo, implementar as opções **3a** (Home) e **3b** (Galeria); rodadas 1 e 2 são histórico.

## Fidelity
**Hi-fi** para layout, cores, tipografia e interações. Os dados (datas, marcadores, legendas da galeria) no mock são exemplos — vir do banco.

## Screens

### 1. Ribbon (topo de todas as páginas) — `base.html`
- Faixa full-width, `background:#1c1c1c`, texto `#e9e6de`, `padding:8px 28px`, JetBrains Mono (ou a mono do site) 12px, `letter-spacing:.06em`, flex com `gap:18px`.
- Conteúdo: `[◂ ocultar arquivo | ▸ arquivo & marcadores]` (cor `#ffee00`, = accent atual) · `N poemas · atualizado <data do último post>` · `último: <título>` (cor `#9d998f`) · à direita links **RSS** e **Atom** (`#f08a4b`) → `url_for('feed_rss')`, `url_for('feed_atom')`.
- Hover: `background:#2a2a28`. Clique em qualquer ponto do ribbon alterna a lateral (só na home). Na galeria, o primeiro item mostra `GALERIA · N imagens`.

### 2. Cabeçalho — `base.html` `<nav>`
- `background:#f6f4ef`, `padding:18px 28px`, `border-bottom:1px solid #e2ded5`, flex `space-between`.
- Esquerda: logo `xoxox_xampu_para_ossos_original_red_beige.svg` em **56×110px**, `image-rendering:pixelated`, `margin:-8px 0` (não aumenta a altura do header) + "XAMPU PARA OSSOS" Consolas 30px bold, `letter-spacing:.04em`, `text-shadow:0 0 10px rgba(255,238,0,.9)` (= `.cyber-glow`). Substitui `wp-icon.png`/`.logo-icon` (pode manter a animação `logo-pulse` se desejado).
- Direita (gap 22px, mono 12px, `letter-spacing:.08em`, `#555`): **Poemas · Galeria · Sobre · Depoimentos · [lupa] · ⚡ Tema · Entrar/Registrar como pseudônimo**. Item ativo: `color:#1c1c1c; border-bottom:1px solid #1c1c1c`.
- **"Entrar" + "Cadastrar Pseudônimo" viram um único link** "Entrar/Registrar como pseudônimo" (→ `login`, com link para registro dentro da página de login, ou página combinada). Logado: manter "+ Novo Post", "Xampu", "Sair (user)".
- **Busca (lupa)**: wrapper fixo 22×22px `position:relative`; dentro, `label` `position:absolute; right:0; top:50%; translateY(-50%); z-index:20; background:#f6f4ef; width:22px; overflow:hidden; flex-direction:row-reverse`. Em `:hover` e `:focus-within` → `width:260px; padding-left:10px; border-bottom:1px solid #1c1c1c`. Transição `width .35s cubic-bezier(.2,.8,.2,1)`. Abre **para a esquerda, sobrepondo** os outros botões, sem empurrar layout. Manter `id="searchBar"`, `list="tagSuggestions"` e `#searchDropdown` (ancorado ao label) para não quebrar `main.js`. Ícone: SVG lupa 16px, stroke `#1c1c1c` 1.6.

### 3. Home — `index.html`
Layout: flex; lateral 260px + `main` `flex:1; padding:28px`.

**Lateral (aside)** — `padding:28px 24px`, `border-right:1px solid #e2ded5`, seções com gap 32px. Recolhe animando `width 260px→0` + `opacity` (`.45s cubic-bezier(.2,.8,.2,1)`); estado em `localStorage`.
- Título de seção: mono 11px, `letter-spacing:.14em`, `#8a8578` — "ARQUIVO", "MARCADORES".
- **Arquivo** (árvore, ref. thiagovscoelho.blogspot.com): linhas `padding:4px 0`, seta mono 9px `▶/▼` `#8a8578`, contagem `(n)` mono 11px `#8a8578`.
  - Ano: serif (Newsreader) 19px, indent 0.
  - Mês (nome por extenso PT-BR): 17px, indent 18px.
  - Poema: 16px itálico, indent 36px, link para `view_post`.
  - Padrão: ano atual e mês mais recente abertos. Hover: `color:#8a6d00`.
- **Marcadores**: lista ordenada por contagem desc; linha flex `space-between`, serif 17px + `(n)`; hover `#ece8dd`; ativo `background:#ffee00`. Clique filtra o mosaico (pode reusar filtro de tags da busca ou `?tag=`); "limpar ✕" aparece quando há filtro.
- Dados novos necessários no backend: contagem de posts por ano/mês (e títulos), contagem de posts por tag.

**Mosaico** — manter exatamente o `#postGrid` atual (3 colunas, cards `aspect-ratio:1`, gap 0, borda 1px, xadrez W/B `6n+4`/`6n+6`, preview Consolas 0.8rem/1.1, título com `.glowy-title`, tag pills, hover borda/glow amarelo, infinite scroll). Só passa a ocupar a área à direita da lateral. No mock, o rodapé do card tem fundo em gradiente (`linear-gradient(to top, <bg> 60%, transparent)`) para o título ficar legível sobre o texto — opcional.

### 4. Galeria — nova `templates/galeria.html` + rota `/galeria`
- Mesmo ribbon + cabeçalho (item "Galeria" ativo).
- `main`: `max-width:760px; margin:0 auto; padding:56px 28px 80px`; coluna com `gap:72px`.
- Cada item (`<figure>`):
  - Linha de título: Newsreader 32px regular + `#id` mono 11px `#8a8578` à direita.
  - Imagem: largura 100%, `aspect-ratio:4/3` (ou proporção natural), `border:1px solid #1c1c1c`, fundo `#fff`, `object-fit:cover`.
  - Mini-card legenda: `background:#fff; border:1px solid #e2ded5; padding:16px 18px`; legenda Newsreader itálico 18px/1.5 `#3a3833`; meta mono 11px `#8a8578`: `@autor · data · ♡ n`.
- Modelo sugerido: `GalleryItem(id, title, image_path, caption, author_id, created_at)`; upload pelo admin reaproveitando o fluxo de `teaser_image` do editor.

## Design Tokens
- Fundo página `#f6f4ef` · cards/legendas `#ffffff` · ink `#1c1c1c` · ribbon `#1c1c1c` / hover `#2a2a28`
- Divisórias `#e2ded5`, `#ebe8e0` · texto secundário `#555`, `#5a574f`, `#8a8578`, `#9d998f`
- Accent `#ffee00` (= `--accent`) · feed `#f08a4b` · hover arquivo `#8a6d00` · hover marcador `#ece8dd`
- Fontes: Consolas/Courier New (marca, mosaico), JetBrains Mono (UI/meta — pode trocar pela Consolas do site), Newsreader (arquivo, marcadores, galeria) via Google Fonts.
- Raio 0 em tudo. Sem sombras exceto glow amarelo do hover do card.

## Assets
- `xoxox_xampu_para_ossos_original_red_beige.svg` — novo logo (112×219 nativo, pixel art). Colocar em `static/images/`.

## Files
- `Xampu Feed Options.dc.html` — protótipo (opções 3a e 3b).
- `xoxox_xampu_para_ossos_original_red_beige.svg`
