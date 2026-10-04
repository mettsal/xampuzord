# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Projeto: Xampu Para Ossos (Boneshampoo)

Um blog minimalista de poesia digital com estética cyberpunk/K-punk. Interface tipo Instagram grid 3x3, **9 temas customizados por post**, editor Markdown com auto-save, sistema de teasers customizáveis, e search em tempo real por tags.

## Comandos Essenciais

### Setup Inicial
```bash
# Criar ambiente virtual
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Instalar dependências
pip install -r requirements.txt

# Inicializar banco de dados
flask init-db

# Seed com dados de exemplo (opcional)
flask seed-db
```

### Desenvolvimento
```bash
# Rodar aplicação (porta 5000)
python run.py

# Aplicação ficará em http://localhost:5000
```

### Database Management
```bash
# Inicializar tabelas
flask init-db

# Popular com posts de exemplo
flask seed-db

# Migrações (se atualizando de versão antiga): post_theme e body_md
python tools/migrate_add_post_theme.py
python tools/migrate_add_post_body_md.py
python tools/migrate_add_post_source.py   # source_path + hidden (painel do acervo)
python tools/migrate_add_post_slug.py     # slug + post_slug_alias (URLs com título)
python tools/migrate_prelaunch.py         # user.is_banned + site_setting (painel admin)

# Banco SQLite: instance/xampuparaossos.db
```

### Sync do Google Drive (acervo `poesia/`)
```bash
# Drive "poesia etc" -> poesia/ (mão única, rclone copy: nunca apaga local)
tools/drive_sync.sh --dry-run        # ensaio
tools/drive_sync.sh                  # roda agora

# Timer de usuário (a cada 5 min, sem sudo; units em tools/systemd/)
systemctl --user status xampu-drive-sync.timer
journalctl --user -u xampu-drive-sync.service -n 50

# Config: ~/.config/xampuzord/drive-sync.env (DRIVE_SRC, DRIVE_DEST)
# rclone: ~/.local/bin/rclone, remote "gdrive" (scope drive.readonly)
```
O sync traz os arquivos; o acervo em geral continua com importação manual
(`tools/import_posts.py`). Exceção: a caixa **`0_publicar/`** do Drive
(Google Docs exportados como `.txt`). Com `PUBLISH_INBOX=1` no
`drive-sync.env`, `tools/publish_inbox.py` roda após cada sync e publica
poema novo de lá como post (data = agora; tags = subpastas + ano). Ledger em
`instance/publish_ledger.json`: edição no Drive atualiza o post, post apagado
no site não volta, poema já existente (mesmo título e texto) é adotado sem
duplicar.

### URLs dos posts (`/post/<slug>`)
`slugify()` em `app.py`: título sem acento, minúsculo, hífens, até 80 chars
("xampu é o quê não é" → `xampu-e-o-que-nao-e`). Título repetido ganha `-2`,
`-3`…; título sem nenhuma letra ("☆", "500") vira `poema-<id>` (número puro
colidiria com a rota por id). O slug é atribuído no hook `before_flush`
(`assign_post_slugs`) — vale para editor, importador, `publish_inbox` e painel
do acervo sem código extra. `/post/<id>` responde 301 para o slug; título
editado gera slug novo e o antigo vira `PostSlugAlias` (301). Feeds: `<link>`
com slug, `<id>/<guid>` com a URL por id (estável). Gerar links com
`post_url(post)` (global no Jinja) / `post.slug` no JS — nunca
`url_for('view_post', ...)` com id. Rotas de ação (`/post/<id>/edit|delete|
like|comment`) continuam por id.

### Painel do acervo (`/admin/acervo`, admin)
Árvore de `poesia/` com checkbox por pasta e por poema: marcado = no site.
Desmarcar **oculta** (`Post.hidden`: some de home, busca, feeds, arquivo,
ribbon e `Tag.count`; post vira 404 para não-admin, mas guarda views/curtidas/
comentários). Marcar arquivo nunca importado **importa** (regras do
`import_posts.py`). O front manda só as diferenças; revisão em dry-run antes de
aplicar. Lógica em `acervo.py`; posts se ligam ao arquivo por
`Post.source_path` (relativo a `poesia/`), preenchido pelo importador,
pelo `publish_inbox.py` e, para posts antigos, por conteúdo
(`tools/migrate_add_post_source.py`). Consultas públicas usam
`public_posts()`/`get_visible_post_or_404()` — **não usar `Post.query` cru
em rota pública**.

### Painel admin (`/admin`)
Abas **Posts · Moderação · Usuários · Site** (+ link para o Acervo), front em
`static/js/admin.js`, dados via `/api/admin/*` (decorator `admin_required`).
- Posts: título editável inline (slug novo + alias), zerar views (por poema e
  global com confirmação "zerar"), ocultar/mostrar.
- Moderação: comentários e depoimentos recentes, com apagar.
- Usuários: bloquear (`User.is_banned` → `load_user` devolve None e o login
  recusa) e apagar (leva comentários/depoimentos). Admin e a própria conta não.
- Site: interruptores em `site_setting` (`registration_open`, `comments_open`,
  `testimonials_open`; ler com `setting(key)`) + estado: último backup e última
  publicação automática (`instance/publish_status.json`).

### Rate limit e CAPTCHA
O Cloudflare Tunnel entrega tudo vindo de 127.0.0.1; a chave do limiter é
`client_ip()` (header `CF-Connecting-IP`, **só** quando o remoto é loopback).
Não há limite global: só as rotas de escrita têm limite explícito.
Cadastro: honeypot (`website`) sempre; Cloudflare Turnstile quando
`TURNSTILE_SITE_KEY` e `TURNSTILE_SECRET_KEY` estão no `.env`.
`flask seed-db` recusa rodar em produção; `flask prune-seed-users` remove as
contas `poet_N` do seed.

### Cartão de compartilhamento e buscadores
`GET /post/<slug>/card.png` (`cards.py`, Pillow): 1200×630 nas cores do tema,
com o poema inteiro no maior corpo que couber (uma coluna enquanto legível,
até 5; verso não é quebrado se houver alternativa). Cache em
`instance/cards/<id>-<hash>.png` (hash de título+corpo+tema; mudar o layout =
subir `CARD_VERSION`). `post.html` usa o cartão como `og:image` (capa própria
tem prioridade); demais páginas usam `static/images/og-default.png`.
`/robots.txt` e `/sitemap.xml` (só posts visíveis).

### Backup do banco
```bash
tools/db_backup.sh                                   # agora (sqlite .backup + integrity_check)
systemctl --user status xampu-db-backup.timer        # diário 03:00, guarda 14
ls ~/backups/xampu-db/
```

### ⚠️ O working tree é a produção
O gunicorn e o timer do Drive rodam direto deste diretório. Mudança de schema:
**aplicar a migração no banco antes de pôr o modelo novo no `app.py`** — senão
o próximo restart (ou reboot) derruba o site.

### Galeria
```bash
# graphics/galeria/*.jpg|png|… + graphics/galeria/subtitles.json -> /galeria
#   subtitles.json: {"arquivo.jpg": {"title": "...", "caption": "..."}}
python tools/import_gallery.py --dry-run
python tools/import_gallery.py       # idempotente; reedita título/legenda
# Banco antigo sem a tabela: python tools/migrate_add_gallery.py
```
O `subtitles.json` só é lido quando o script roda (restart não o aplica), e só
reaplica uma legenda se o JSON mudou desde o último import (ledger
`galeria_meta`). Edição do dia a dia: em `/galeria`, logado como admin, cada
imagem tem "editar" (título, legenda, data, trocar arquivo) —
`POST /galeria/<id>/edit`.

### CLI de Gestão de Usuários
```bash
# Listar todos usuários
flask list-users

# Resetar senha do admin
flask reset-admin-password

# Promover usuário para admin
flask make-admin
```

## Arquitetura do Sistema

### Stack Tecnológico
- **Backend**: Flask + SQLAlchemy (Python 3.10+)
- **Database**: SQLite (dev) → PostgreSQL (prod)
- **Frontend**: Vanilla JS + Tailwind CSS (estático, build via `npm run build:css`)
- **Auth**: Flask-Login com Werkzeug password hashing
- **Security**: Bleach (XSS), Flask-Limiter (rate limiting)
- **Markdown**: marked.js (client-side parsing)
- **Feeds**: feedgen (RSS 2.0 + Atom 1.0, global e por tag)
- **Compartilhamento**: sem lib — links de intent (X/WhatsApp) + Web Share API (Instagram)
- **Deployment**: Gunicorn + Nginx (recomendado)

### Estrutura de Dados

#### Modelo Post
```python
Post {
    id, title, body_html (rendered markdown),
    tags: JSON [{'type': 'year'|'genre', 'value': str}],
    font: str (Consolas, Courier New, Monaco, Fira Code),
    post_theme: str (inherit, dark, light, cyberpunk, matrix, vaporwave, noir, sunset, ocean),
    teaser_type: 'auto'|'image'|'none',
    teaser_image: str (path relativo a /static/),
    views: int,
    source_path: str|None (arquivo em poesia/, NULL = editor),
    slug: str (URL /post/<slug>, único; ver "URLs dos posts"),
    hidden: bool (oculto pelo painel do acervo),
    author_id, created_at, updated_at
}
```

#### Sistema de Teasers
- **auto**: Preview de texto truncado (padrão)
- **image**: Imagem de capa com título overlay
- **none**: Só metadados (sem preview)

Uploads salvos em `static/uploads/teasers/` com UUID no filename.

### Fluxo de Criação de Posts

1. **Editor** (`templates/editor.html`):
   - Markdown textarea com preview live
   - Upload drag-and-drop para teaser images
   - Auto-save para localStorage a cada 1s
   - Keyboard shortcuts: Ctrl+S (save), Ctrl+P (preview)

2. **Processing** (`app.py`):
   - Frontend converte Markdown → HTML (marked.js)
   - Backend sanitiza HTML (bleach)
   - Tags processadas em JSON com tipagem automática
   - Anos (YYYY) → type='year', resto → type='genre'

3. **Rendering**:
   - Grid: `createPostCard()` aplica teaser correto
   - Post view: Renderiza com font específica do post
   - CSS: `.post-content` preserva whitespace/line-height

### Sistema de Temas (Implementado!)

**Tema Global**: Toggle Preto/Branco (`body.dark`) afeta navbar, fundo, estrutura.

**Temas por Post** (9 opções):
- **inherit**: Herda tema global
- **dark**: Preto puro (#000)
- **light**: Branco puro (#fff)
- **cyberpunk**: Roxo escuro + Ciano + Magenta glow (#1a0033)
- **matrix**: Verde matrix no preto (#00ff00)
- **vaporwave**: Gradiente rosa/roxo/azul
- **noir**: Cinza escuro estilo filme (#1a1a1a)
- **sunset**: Gradiente laranja/amarelo
- **ocean**: Azul marinho + Azul claro (#001f3f)

Cada post pode ter tema independente. CSS usa classes `.post-theme-{nome}` com custom properties isoladas.

### Compartilhamento Social

`templates/base.html` expõe `{% block head %}{% endblock %}` (vazio por
padrão) logo antes de `</head>`, permitindo que templates filhos injetem
meta tags próprias. `templates/post.html` usa esse bloco para declarar
Open Graph (`og:title`, `og:description`, `og:image`, `og:url`) e Twitter
Card (`summary_large_image`), reaproveitando `post.body_html|striptags|truncate`
para a descrição e `post.teaser_image` (com fallback pro logo) para a imagem.

Botões de compartilhar na página do post:
- **X / WhatsApp**: links de intent puros (`twitter.com/intent/tweet`,
  `wa.me`), sem JS.
- **Instagram**: não tem intent de compartilhamento por URL. `static/js/post-view.js`
  tenta `navigator.share()` (Web Share API, abre a folha nativa no mobile,
  onde o Instagram costuma aparecer) e cai para `navigator.clipboard.writeText()`
  (copiar link) quando a API não existe (desktop).

### Importante: Consistência de Estilo

- **Font Kerning**: Desabilitado (`font-kerning: normal`) para look "code editor"
- **Line Height**: 1.2 para posts (match Sublime Text)
- **Tab Size**: 4 espaços em `<pre>` e `<code>`
- **Text Rendering**: `optimizeSpeed` (sem antialiasing)
- **Whitespace**: Conteúdo auto-wrapped em `<pre><code>` no backend
- **Word Wrap**: `word-wrap: break-word` (não quebra palavras no meio)
- **Scroll**: Posts completos têm `overflow-x: auto`, previews têm limite visual

### API Endpoints Principais

```
GET  /                          → Homepage com 9 posts iniciais
GET  /sobre                     → Página sobre o projeto
GET  /api/posts?page=N&tags=[]  → Infinite scroll + busca (título/tags/conteúdo)
GET  /post/<slug>               → Post (oculto = 404 p/ não-admin)
GET  /post/<id>                 → 301 para /post/<slug> (slug antigo também)
POST /post/new                  → Criar post (JSON, requer auth, rate: 20/hora)
POST /post/<id>/edit            → Editar (ownership check)
POST /post/<id>/delete          → Deletar (+ cleanup de imagem)
POST /api/upload/teaser         → Upload imagem (max 16MB, rate: 10/min)
GET  /api/tags                  → Autocomplete tags (top 50)
POST /api/user/settings         → Salvar preferências user
POST /login                     → Login (rate: 10/min - anti brute force)
POST /register                  → Registro (rate: 5/hora - anti spam)
POST /post/<id>/like            → Toggle curtida anônima (visitor_id, rate: 30/min)
POST /post/<id>/comment         → Comentar (requer login, rate: 10/hora)
POST /comment/<id>/delete       → Deletar comentário (admin)
GET|POST /depoimentos           → Guestbook (POST requer login, rate: 10/hora)
POST /depoimento/<id>/delete    → Deletar depoimento (admin)
GET  /feed.xml[?tag=X]          → Feed RSS 2.0, corpo completo (global ou por tag)
GET  /feed.atom[?tag=X]         → Feed Atom 1.0, corpo completo (global ou por tag)
GET  /post/<slug>/card.png      → Cartão de compartilhamento (og:image)
GET  /robots.txt, /sitemap.xml  → Buscadores
GET  /admin                     → Painel admin (abas; dados em /api/admin/*)
GET  /admin/acervo              → Painel do acervo (admin)
GET|POST /api/admin/acervo      → Estado do acervo / aplicar include/exclude (dry_run)
```

### Security Notes

**Implementado:**
- ✅ **Rate Limiting** (Flask-Limiter): Login 10/min, Registro 5/hora, Posts 20/hora
- ✅ **HTML sanitization**: Bleach com allowlist de tags
- ✅ **File uploads**: Validação extensão + tamanho (16MB max) + UUID renaming
- ✅ **Auth**: Ownership checks em edit/delete (owner ou admin)
- ✅ **Passwords**: Werkzeug PBKDF2 hashing (nunca plaintext)
- ✅ **Sessions**: Flask-Login + HTTPOnly cookies
- ✅ **Environment vars**: SECRET_KEY e DATABASE_URL via .env

**Para Produção** (ver SECURITY.md):
- Gerar SECRET_KEY forte: `python -c "import secrets; print(secrets.token_hex(32))"`
- Configurar HTTPS (Let's Encrypt)
- Migrar para PostgreSQL
- `FLASK_DEBUG=False`
- Usar Gunicorn + Nginx

### User Roles

- **Regular User**: Criar/editar/deletar próprios posts
- **Admin** (`is_admin=True`): Acesso a `/admin`, pode editar/deletar qualquer post
- Admin padrão seed: usuário `xampuzordmin` (senha definida no seed em app.py — trocar em produção com `flask reset-admin-password`)

### Frontend Architecture

**main.js**:
- Theme toggle com localStorage persistence
- **Search/filter por título, tags e conteúdo** em tempo real (debounce 300ms;
  `filter_by_search()` em `app.py`, ilike OR sobre `title`/`tags`/`body_html`)
- Click em tags para buscar automaticamente
- Infinite scroll (IntersectionObserver)
- Post card rendering dinâmico com temas
- Delete confirmation

**editor.js**:
- Markdown preview (marked.js)
- **Auto-save draft system** (localStorage, 1s)
- **Keyboard shortcuts**: Ctrl+S (save), Ctrl+P (preview)
- Image upload (drag-drop + click)
- Form submission com JSON
- Seleção de tema do post

**style.css**:
- CSS custom properties para temas (`--bg-color`, `--text-color`, `--accent`)
- **9 temas customizados** (.post-theme-{nome})
- Animações: shimmer, pulse, logo-pulse, hover effects
- Search bar com glow ao focar
- Tags clicáveis com hover scale

### Database Schema Quirk

Tag counting: `process_tags()` incrementa ao criar/editar e `decrement_tags()`
decrementa ao editar/deletar (linhas que zeram são removidas). **Manter o
count correto** ao mexer em tags. Post oculto (`hidden`) não conta: ocultar
decrementa, reexibir incrementa (`increment_tags`), e editar/apagar post oculto
não mexe nas contagens.

### Known Issues / TODO

✅ **Resolvido nesta sessão:**
- ✅ Search/filter por tags funcional
- ✅ Template 500.html criado
- ✅ Word-wrap correto (não quebra palavras)
- ✅ Scroll horizontal em posts largos
- ✅ Auto-save localStorage
- ✅ Keyboard shortcuts
- ✅ Sistema de temas por post
- ✅ Página "Sobre"
- ✅ CLI tools (reset password, list users, make admin)

❌ **Ainda pendente:**

O backlog vivo de fraquezas e foco de trabalho fica no AGENTS.md, seção
"Fraquezas Conhecidas & Foco de Trabalho" (os 4 itens antigos desta lista
foram corrigidos; CAPTCHA no registro segue pendente, ver SECURITY.md).

### Deployment Considerations

**Arquivos de Configuração:**
- `.env.example` - Template de variáveis de ambiente
- `SECURITY.md` - Guia completo de segurança (16 páginas)
- `tools/migrate_add_post_theme.py` - Script de migração para post_theme
- `tools/migrate_add_post_body_md.py` - Script de migração para body_md (fonte Markdown)

**Comandos de Deploy:**
```bash
# Instalar dependências (inclui Flask-Limiter, gunicorn)
pip install -r requirements.txt

# Configurar variáveis de ambiente
cp .env.example .env
# Editar .env com SECRET_KEY forte e DATABASE_URL

# Migrar database se necessário
python tools/migrate_add_post_theme.py
python tools/migrate_add_post_body_md.py

# Rodar com gunicorn (produção)
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

**Self-hosting (Thinkpad/VPS):**
- Nginx como reverse proxy
- Certificado SSL (Let's Encrypt)
- Systemd service para auto-restart
- PostgreSQL ao invés de SQLite
- Ver SECURITY.md para setup completo

### Portuguese UI

Interface em português brasileiro:
- "Preto/Branco" (tema)
- "Cadastrar Pseudônimo" (register)
- "Xampu" (admin - easter egg)
- Flash messages e confirmações em PT-BR
