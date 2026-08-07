# AGENTS.md

Guia para agentes de IA (e humanos) trabalhando neste repositório.

## Projeto: Xampu Para Ossos

Blog minimalista de poesia digital com estética cyberpunk/K-punk. Hobby pessoal
tratado com rigor profissional: a experiência do usuário final — em qualquer
dispositivo — vem em primeiro lugar. Nada de telas quebradas, estados sem
feedback, ou funcionalidades que só funcionam "na máquina do autor".

- Grid 3x3 estilo Instagram com infinite scroll; cards `inherit` alternam em
  xadrez W W W / B W B (CSS `nth-child`, ignora o tema global)
- 9 temas customizáveis por post + tema global Preto/Branco; leitor pode
  trocar o tema na página do post (localStorage, não altera o post)
- Apenas **admins** publicam/editam/deletam; usuário registrado é read-only
- Editor Markdown com live preview, auto-save (localStorage) e atalhos
- Sistema de teasers (auto / imagem / nenhum) e busca por tags
- Interface inteiramente em **português brasileiro**

## Comandos Essenciais

```bash
# Setup
python -m venv xenv            # o venv deste projeto chama-se xenv/
source xenv/bin/activate
pip install -r requirements.txt

# Banco de dados (SQLite em instance/xampuparaossos.db)
flask init-db                  # criar tabelas
flask seed-db                  # dados de exemplo (cria admin/admin123)
python migrate_add_post_theme.py  # migração legada, só se o banco for antigo

# Rodar (http://localhost:5000)
python run.py                  # debug via FLASK_DEBUG=True no .env

# Gestão de usuários
flask list-users
flask reset-admin-password
flask make-admin

# Importar acervo de textos de poesia/ para o banco (sem HTTP, ver --help)
python tools/import_posts.py
```

Não há suíte de testes. Valide mudanças rodando o app e exercitando o fluxo
afetado no navegador (desktop **e** mobile, ver seção UX abaixo).

## Arquitetura

### Stack
- **Backend**: Flask + SQLAlchemy (SQLite em dev, PostgreSQL planejado p/ prod)
- **Frontend**: Vanilla JS + Tailwind via CDN (`cdn.tailwindcss.com`)
- **Auth**: Flask-Login + Werkzeug PBKDF2
- **Segurança**: Bleach (sanitização HTML), Flask-WTF (CSRF), Flask-Limiter (rate limit)
- **Markdown**: marked.js no cliente — o HTML resultante é sanitizado no backend

### Arquivos-chave
```
app.py                    # App Flask inteira: modelos, rotas, CLI (arquivo único)
config.py                 # Config por ambiente (dev/prod/testing) — USADO por app.py
run.py                    # Entry point
tools/import_posts.py     # Importador do acervo poesia/ (docstring explica regras)
templates/                # Jinja2: base, index, post, editor, login, register,
                          # admin, sobre, 404, 500
static/css/style.css      # Estilos + 9 temas de post (.post-theme-{nome})
static/js/main.js         # Nav, tema global, busca, infinite scroll, delete
static/js/editor.js       # Editor: preview, auto-save, upload de teaser
static/js/post-view.js    # Zoom/auto-fit do poema na página do post
static/uploads/teasers/   # Uploads de usuários (UUID no nome)
instance/                 # SQLite + backups de banco
poesia/                   # Acervo de textos (fonte do importador) — conteúdo, não código
cf-ddns.sh                # DDNS Cloudflare p/ self-hosting (placeholders, não secrets)
xampuzord                 # Symlink p/ config nginx da máquina do autor — ignorar
```

### Modelo de dados (app.py)
- `User`: username, email, password_hash, settings (JSON), is_admin
- `Post`: title, body_html (sanitizado), tags (JSON `[{type, value}]`),
  font, post_theme, teaser_type, teaser_image, views, author_id
- `Tag`: agregado global (name, type, count) — `process_tags()` incrementa,
  `decrement_tags()` decrementa ao editar/deletar. **Manter o count correto**
  ao mexer em tags.

### Fluxo de criação de post
1. Editor converte Markdown → HTML no cliente (marked.js)
2. Backend sanitiza via `sanitize_html()` (bleach, allowlist) e envolve em
   `<pre><code>` se necessário — o visual "editor de código" é intencional
3. Tags viram JSON: `YYYY` → `type: year`, resto → `type: genre`

### Consistência visual (intencional, não "corrigir")
- `font-kerning: normal`, `text-rendering: optimizeSpeed`, line-height 1.2,
  tab-size 4 — estética de editor de texto (Sublime-like)
- Posts largos: `overflow-x: auto` + zoom/auto-fit em `post-view.js`
- Temas de post via classes `.post-theme-{nome}` com CSS custom properties

## Convenções de Código

- **Idioma**: UI, flash messages e docs em PT-BR. Código e identificadores em
  inglês. Comentários em PT-BR quando explicam decisões (padrão atual do app.py).
- **Mudanças mínimas**: corrija o que foi pedido, sem refatorações oportunistas.
  Três linhas parecidas são melhores que uma abstração prematura.
- **Arquivos `*-backup.*`**: snapshots históricos. Nunca editar nem referenciar;
  candidatos a remoção futura.
- **`templates/complete.html` e `templates/main.html`**: órfãos, não são
  renderizados por nenhuma rota. Não usar como referência de padrão.
- **Sem placeholders**: nunca deixar `// resto igual` — entregue o arquivo completo.
- Ao mudar comportamento documentado aqui, no README ou no CLAUDE.md,
  **atualize os três** na mesma mudança.

## Princípios de UX (a missão deste projeto)

O usuário final não deve se frustrar. Antes de considerar qualquer mudança de
UI pronta:

1. **Mobile e desktop, sempre**: breakpoints atuais são `md:` (768px) do
   Tailwind. Teste todo fluxo novo em viewport estreito (~375px) e largo.
   Grid: `grid-cols-1 md:grid-cols-3`, com toggle **▦ 3 colunas** no mobile
   (botão `gridToggle` na index, `#postGrid.mosaic-3`, preferência em
   localStorage `gridCols`). Navbar: hamburger (`navToggle`) abaixo de `md`.
2. **Touch**: alvos de toque ≥ 44px de altura (o padrão atual `py-2` no mobile
   atende; manter). Não depender de hover para ações essenciais.
3. **Feedback em toda ação**: loading, erro e sucesso visíveis — seguir o
   padrão do upload de teaser (`uploadProgress`) e das flash messages.
4. **Não quebrar poesia**: whitespace é conteúdo. Qualquer mudança em
   renderização de `body_html` precisa preservar quebras de linha, indentação
   e `<pre><code>`. Teste com poema de versos longos e poesia visual.
5. **Acessibilidade básica**: `aria-label`/`aria-expanded` em botões de
   controle (padrão já iniciado na navbar e no zoom). Manter e expandir.
6. **Estado persistido**: tema e rascunho vivem em localStorage — não regredir.

## Segurança (invariantes — não remover)

- HTML de posts **sempre** passa por `sanitize_html()` (bleach, sem atributo
  `style`, protocolos http/https/mailto apenas)
- CSRF: formulários com `csrf_token()`, fetch com header `X-CSRFToken`
  (lido do `<meta name="csrf-token">`)
- Rate limits: login 10/min, registro 5/h, posts 20/h, upload 10/min
- Uploads: validação de extensão + verificação de bytes via PIL + UUID no nome
- Ownership: **escrita restrita a admins** — criar/editar/deletar posts e
  upload de teaser exigem `is_admin` (usuário comum é read-only; o registro
  segue aberto)
- Produção: `FLASK_ENV=production` recusa subir com SECRET_KEY fraca;
  cookies Secure via `ProductionConfig`. Guia completo em `SECURITY.md`.

## Fraquezas Conhecidas & Foco de Trabalho

Ordenado por prioridade. Ao corrigir um item, mova-o para o changelog e
atualize esta lista.

### P0 — Experiência quebrada ou enganosa
1. **Filtro por tags do backend é O(N) em Python**: `/api/posts` com `tags`
   carrega TODOS os posts e fatia em memória (app.py:~245). Funciona hoje,
   escala mal. Migrar para filtro SQL (ou FTS) ao crescer.
2. **`window.currentUser` nunca é definido**: o save de preferências em
   `/api/user/settings` (main.js:~50) é código morto. Definir a flag no
   `base.html` ou remover o caminho morto.
3. **Round-trip Markdown no editor**: ao editar, o textarea recebe `body_html`
   (HTML) e na submissão passa de novo pelo `marked.parse`. Funciona por
   sorte (HTML passa intacto), mas é frágil e confunde. Decidir: guardar o
   Markdown fonte (coluna nova) ou documentar que edição é sobre HTML.

### P1 — Profissionalização
5. **Sem testes**: zero cobertura. Mínimo viável: smoke tests das rotas
   (Flask test client) + teste de `sanitize_html` e `process/decrement_tags`.
6. **`html lang="en"`** em `base.html` com UI em PT-BR — acessibilidade/SEO.
7. **Mensagens misturadas PT/EN**: "Username already exists", "You can only
   edit your own posts" etc. Padronizar PT-BR.
8. **Views infladas**: `view_post` incrementa a cada request (refresh, bots,
   o próprio autor). Considerar throttle por sessão.
9. **Autocomplete de tags**: `/api/tags` existe, UI nunca foi conectada.
10. **Deprecations**: `datetime.utcnow` e `Query.get()` geram warnings em
    SQLAlchemy 2 / Python 3.12+.
11. **Tailwind Play CDN** não é para produção (aviso no console, flash de
    estilo). Gerar CSS estático no build de deploy.

### P2 — Higiene do repositório
12. **Arquivos mortos**: `templates/complete.html`, `templates/main.html`,
    `index-backup.html`, `editor-backup.html`, `*-backup.js/css`. Remover
    (git preserva o histórico).
13. **`xampuzord`**: symlink p/ `/etc/nginx/...` da máquina do autor — quebrado
    em qualquer outro clone. Mover a config para dentro do repo (ex: `deploy/`)
    e referenciá-la.
14. **Docs desatualizadas**: README e CLAUDE.md ainda dizem "config.py não é
    usado" e "tag count não decrementa" — ambos já corrigidos no código.
    Sincronizar.
15. **Sem headers de segurança** (CSP, X-Frame-Options) e sem CAPTCHA no
    registro — já listados no SECURITY.md como TODO.

## Deployment

Self-hosting (Thinkpad) com Cloudflare → Nginx → Gunicorn (systemd). Ver
SECURITY.md para o passo a passo completo.

**Arquitetura real em produção** (após o incidente de 2026-08-07):

```
navegador → Cloudflare → nginx :443 (/etc/nginx/sites-enabled/xampuzord)
  location /static/ → alias direto p/ static/ do repo (expires 30d)
  location /        → proxy_pass http://unix:/run/xampuzord/xampuzord.sock
                            └─ xampuzord.service (systemd) → gunicorn app:app
```

**Fluxo de deploy de mudanças**:
```bash
sudo systemctl restart xampuzord   # recarrega Python + templates
# bump do ?v= em base.html se mudou CSS/JS; Ctrl+F5 / Purge no Cloudflare
```

**Invariantes duras (lição do incidente)**:
- O systemd é o **único** dono do app. **Nunca** subir gunicorn manual em
  porta de produção (`-b 127.0.0.1:5000`) — uma instância órfã assim serviu
  código velho por semanas enquanto reiniciávamos o serviço errado.
- Se o site "não atualiza", comparar as pontas antes de culpar cache:
  `curl localhost:5000`, `curl --unix-socket /run/xampuzord/xampuzord.sock`,
  `curl https://www.xampuparaossos.com.br` — a que diverge é a culpada.
- `.env` com `SECRET_KEY` forte, `FLASK_ENV=production`, `DATABASE_URL`
- PostgreSQL em produção (SQLite é só dev)
- `cf-ddns.sh` roda via cron na máquina host (contém placeholders, não secrets)
- Nginx serve `/static/` com `expires 30d`: ao mudar CSS/JS, **bump do `?v=`**
  no link/script do `base.html` (padrão: data, ex `?v=20260807`) para furar o
  cache do navegador/Cloudflare.
