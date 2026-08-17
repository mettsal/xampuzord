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

# Banco SQLite: instance/xampuparaossos.db
```

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
GET  /api/posts?page=N&tags=[]  → Infinite scroll pagination
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
- **Search/filter por tags** em tempo real (debounce 300ms)
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
count correto** ao mexer em tags.

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
