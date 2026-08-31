# README.md
# Xampu Para Ossos (Boneshampoo)

Um blog minimalista de poesia digital com estética cyberpunk/K-punk. Interface tipo Instagram grid 3x3, temas customizados por post, editor Markdown, e sistema de teasers.

## Funcionalidades

- **Grid Layout Instagram**: Grid 3x3 com infinite scroll
- **Editor Markdown**: Editor com live preview e auto-save
- **Temas Customizados por Post**: 9 temas disponíveis (inherit, dark, light, cyberpunk, matrix, vaporwave, noir, sunset, ocean)
- **Tema Global**: Toggle Preto/Branco para navegação
- **Sistema de Tags**: Organizar posts por ano e gênero
- **Autenticação de Usuários**: Registro, login e gestão de posts
- **Admin Dashboard**: Monitorar posts, usuários e estatísticas
- **Teasers Customizáveis**: 3 modos (auto text, imagem upload, nenhum)
- **Funcionalidades UX**:
  - ✅ Auto-save drafts para localStorage
  - ✅ Keyboard shortcuts (Ctrl+S salvar, Ctrl+P preview)
  - ✅ Search/filter por título, tags e conteúdo em tempo real
  - ✅ Click em tags para filtrar
  - ✅ Contador de visualizações
  - ✅ Upload de imagens teaser (drag & drop)
  - ✅ Scroll horizontal para posts largos
  - ✅ Auto-wrap em `<pre><code>`
- **Feeds RSS/Atom**: global e por tag, corpo completo dos posts
- **Compartilhar**: X, WhatsApp e Instagram na página do post (Open Graph/Twitter Card + Web Share API)

## Tech Stack

- **Backend**: Flask (Python 3.10+)
- **Database**: SQLite with SQLAlchemy ORM
- **Frontend**: Vanilla JavaScript, Tailwind CSS
- **Authentication**: Flask-Login
- **Security**: Bleach for HTML sanitization, Werkzeug for password hashing
- **Feeds**: feedgen (RSS 2.0 + Atom 1.0)
- **Compartilhamento**: sem dependência — links de intent (X/WhatsApp) + Web Share API nativa (Instagram)

## Instalação

1. Clone o repositório:
```bash
git clone https://github.com/yourusername/boneshampoo.git
cd boneshampoo
```

2. Crie um ambiente virtual:
```bash
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac
```

3. Instale as dependências:
```bash
pip install -r requirements.txt
```

4. Inicialize o banco de dados:
```bash
flask init-db
flask seed-db  # Opcional: dados de exemplo (cria o admin padrão do seed)
```

5. **IMPORTANTE - Migração**: Se estiver atualizando de versão antiga, rode:
```bash
python tools/migrate_add_post_theme.py
python tools/migrate_add_post_body_md.py
```

6. Execute a aplicação:
```bash
python run.py
```

A aplicação estará disponível em `http://localhost:5000`

## Comandos CLI Úteis

### Gerenciamento de Usuários

**Listar todos os usuários:**
```bash
flask list-users
```
Mostra ID, username, email, status admin e número de posts.

**Resetar senha do admin:**
```bash
flask reset-admin-password
```
Encontra o primeiro admin e permite resetar a senha interativamente (senha não aparece ao digitar).

**Tornar usuário admin:**
```bash
flask make-admin
```
Pergunta o username e promove para admin (requer confirmação).

### Gerenciamento de Banco de Dados

**Inicializar banco:**
```bash
flask init-db
```

**Popular com dados de exemplo:**
```bash
flask seed-db
```
Cria o admin padrão do seed + 5 usuários + 20 posts de exemplo.

### Testes

```bash
python -m unittest discover -s tests -v
```
Suíte mínima (stdlib, sem dependências): `sanitize_html`, contagem de tags,
smoke das rotas, permissões, throttle de views e headers de segurança.

### CSS (Tailwind estático)

O Tailwind é compilado localmente (sem Play CDN). Ao mudar classes nos
templates ou JS:
```bash
npm install        # uma vez
npm run build:css  # regenera static/css/tailwind.css (versionado)
```

## Estrutura do Projeto

```
boneshampoo/
├── app.py                        # Aplicação Flask principal
├── config.py                     # Config por ambiente (dev/prod/testing)
├── run.py                        # Entry point
├── requirements.txt              # Dependências Python
├── tools/                        # Scripts utilitários
│   ├── import_posts.py          # Importador do acervo poesia/
│   ├── migrate_add_post_theme.py # Migração legada (post_theme)
│   └── migrate_add_post_body_md.py # Migração legada (body_md)
├── CLAUDE.md                     # Guia para Claude Code
├── templates/                    # Templates Jinja2
│   ├── base.html                # Template base com navbar
│   ├── index.html               # Homepage com grid 3x3
│   ├── post.html                # Visualização de post individual
│   ├── editor.html              # Editor de posts
│   ├── login.html               # Página de login
│   ├── register.html            # Página de registro
│   ├── admin.html               # Dashboard admin
│   ├── 404.html                 # Página de erro 404
│   └── 500.html                 # Página de erro 500
├── static/
│   ├── css/
│   │   └── style.css            # Estilos customizados + temas
│   ├── js/
│   │   ├── main.js              # JavaScript principal + search
│   │   └── editor.js            # Funcionalidade do editor
│   └── uploads/
│       └── teasers/             # Imagens de teaser (user upload)
├── instance/
│   └── xampuparaossos.db        # SQLite database
└── README.md
```

## API Endpoints

- `GET /` - Homepage com 9 posts iniciais
- `GET /api/posts?page=<int>&tags=<json>` - Posts para infinite scroll; `tags` é a busca da search bar (casa por título, tags e conteúdo)
- `GET /post/<id>` - Visualizar post individual (1 view por post por sessão)
- `POST /post/new` - Criar novo post (requer autenticação)
- `POST /post/<id>/edit` - Editar post (requer ownership ou admin)
- `POST /post/<id>/delete` - Deletar post (requer ownership ou admin)
- `POST /api/upload/teaser` - Upload de imagem teaser (max 16MB)
- `GET /api/tags` - Todas as tags para autocomplete (top 50)
- `POST /api/user/settings` - Atualizar preferências do usuário
- `GET /admin` - Dashboard admin (requer is_admin=True)
- `GET /login` - Página de login
- `POST /login` - Autenticar usuário
- `GET /register` - Página de registro
- `POST /register` - Criar novo usuário
- `GET /logout` - Logout do usuário
- `POST /post/<id>/like` - Toggle de curtida anônima (JSON: visitor_id)
- `POST /post/<id>/comment` - Comentar (requer login)
- `POST /comment/<id>/delete` - Deletar comentário (admin)
- `GET/POST /depoimentos` - Guestbook de depoimentos (POST requer login)
- `POST /depoimento/<id>/delete` - Deletar depoimento (admin)
- `GET /feed.xml?tag=<opcional>` - Feed RSS 2.0 (global ou por tag, corpo completo)
- `GET /feed.atom?tag=<opcional>` - Feed Atom 1.0 (global ou por tag, corpo completo)

## Temas Disponíveis

Posts podem ter temas individuais independentes do tema global:

- **inherit** - Herda tema global (Preto/Branco)
- **dark** - Fundo preto, texto branco
- **light** - Fundo branco, texto preto
- **cyberpunk** - Roxo escuro (#1a0033) + Ciano + Magenta glow
- **matrix** - Verde matrix (#00ff00) no preto
- **vaporwave** - Gradiente rosa/roxo/azul
- **noir** - Cinza escuro estilo filme noir
- **sunset** - Gradiente laranja/amarelo
- **ocean** - Azul marinho (#001f3f) + Azul claro

Selecione o tema no editor ao criar/editar post.

## Funcionalidades Especiais

### Sistema de Teasers
- **Auto (padrão)**: Preview de texto truncado
- **Imagem**: Upload de imagem com overlay de título
- **Nenhum**: Apenas metadados (sem preview)

### Search/Filter
- Digite no search bar para filtrar por tags
- Clique em qualquer tag para buscar automaticamente
- ESC para limpar busca
- Contador de resultados em tempo real

### Editor
- Auto-save a cada 1 segundo
- Ctrl+S para salvar
- Ctrl+P para toggle preview
- Conteúdo automaticamente envolvido em `<pre><code>`
- Upload drag-and-drop para teasers

## Deployment (Planejado)

⚠️ **Ainda não implementado**. Para deployment futuro:

### Heroku
```bash
heroku create your-app-name
heroku config:set SECRET_KEY=your-secret-key
git push heroku main
```

### Considerações
- Trocar SQLite por PostgreSQL
- Setar `SECRET_KEY` em produção
- Habilitar HTTPS
- Adicionar rate limiting
- Implementar CAPTCHA no registro

## Segurança

### ✅ Implementado:
- ✅ **Rate Limiting**: 10/min login, 5/hora registro, 20/hora posts
- ✅ **Sanitização HTML** (Bleach) - previne XSS
- ✅ **Password hashing** (Werkzeug PBKDF2)
- ✅ **Ownership checks** em edit/delete
- ✅ **Validação de uploads** (tipo, tamanho, extensão)
- ✅ **Session cookies** seguras (Flask-Login)
- ✅ **Variáveis de ambiente** para SECRET_KEY e DATABASE_URL

### ⚠️ Configurações Obrigatórias para Produção:

**ANTES de hospedar, você DEVE:**
1. Gerar SECRET_KEY forte: `python -c "import secrets; print(secrets.token_hex(32))"`
2. Configurar HTTPS (Let's Encrypt/Certbot)
3. Migrar para PostgreSQL (não usar SQLite)
4. Setar `FLASK_DEBUG=False`
5. Usar Gunicorn (não `flask run`)

**Leia o guia completo**: [SECURITY.md](SECURITY.md)

### 📋 TODO Futuro:
- CAPTCHA no registro (Google reCAPTCHA)
- Headers de segurança (CSP, X-Frame-Options)
- Compressão de imagens no upload
- Logs centralizados

## Issues Conhecidos

Os itens antigos desta lista foram corrigidos. O backlog vivo de fraquezas e
foco de trabalho fica no [AGENTS.md](AGENTS.md), seção "Fraquezas Conhecidas &
Foco de Trabalho".

## Créditos

- **Conceito**: Blog de poesia digital K-punk/cyberpunk
- **Stack**: Flask + SQLAlchemy + Vanilla JS + Tailwind CSS
- **Markdown**: marked.js (client-side)
- **Desenvolvido com**: Claude Code (Anthropic)

## Licença

MIT License - use livremente para sua própria poesia cibernética! 🧴✨