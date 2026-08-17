# Changelog - Xampu Para Ossos

## [Unreleased] - 2026-08-16

### ✅ Fixes

#### Botões "invisíveis" no toque/hover (ex: toggle de mosaico no mobile)
- Causa: o Tailwind Play CDN regenera `hover:bg-current`
  (`background-color: currentColor`) a cada mutação do DOM e o re-anexa
  **depois** do nosso `style.css`; combinado com a nossa regra
  `hover:text-inverse` (cor = `var(--bg-color)`), fundo e texto ficavam da
  mesma cor no hover "grudento" do toque mobile — o botão sumia visualmente
  mas continuava clicável
- Fix: `!important` nas duas regras de hover invertido em `style.css`
  (corrige todos os botões `hover:bg-current hover:text-inverse` de uma vez)

#### Tags dos cards escondidas no mobile
- Pills de tag dos cards (3 tipos de teaser, em `index.html` e no
  `createPostCard` do `main.js`) agora usam `hidden md:flex` — mobile mostra
  só o conteúdo; desktop inalterado
- Bump de cache `?v=20260816` em `base.html` (style.css + main.js)

### 🧹 Higiene do repositório (organização pré-commit)
- Removidos arquivos mortos: `*-backup.js/css/html`, `templates/complete.html`,
  `templates/main.html`, imagens de referência duplicadas em `static/images/`
  (git preserva o histórico)
- `migrate_add_post_theme.py` movido para `tools/`
- `.claude/` adicionado ao `.gitignore`
- Docs sincronizadas (README/CLAUDE/AGENTS): listas antigas de "issues
  conhecidos" substituídas por ponteiro para o backlog vivo no AGENTS.md;
  itens P2 12-14 resolvidos e removidos

## [Unreleased] - 2026-08-08

### ✅ Features

#### Interações passivas: curtidas, comentários e depoimentos
- **Curtidas anônimas**: botão ♡/♥ na página do post; toggle por visitante
  (UUID em localStorage, constraint `UNIQUE(post_id, visitor_id)` no banco);
  contador atualiza sem reload; rate limit 30/min
- **Comentários**: só usuários logados; publicam direto (decisão de design:
  sem fila de moderação — admin deleta depois via botão inline); texto puro
  escapado pelo Jinja (sem XSS), quebras de linha preservadas; rate limit 10/h
- **Depoimentos**: página `/depoimentos` (guestbook) para usuários logados;
  link novo na navbar no lugar do "CATEGORIAS" morto (`href="#"`)
- Novos modelos: `Like`, `Comment`, `Testimonial` (cascade: morrem com o post)
- **Deploy exige `flask init-db` antes do restart** (cria as tabelas novas)

#### Conta admin oficial: `xampuzordmin`
- Seed (`flask seed-db`) e docs agora criam o admin `xampuzordmin` (senha
  padrão no código) no lugar de `admin/admin123`; conta de produção renomeada
- **Nota**: a senha do seed é pública por estar no repo — produção deve usar
  senha própria via `flask reset-admin-password`

#### Higiene do repositório (para portfólio público)
- `ref/`, `refs/` e o symlink `xampuzord` saíram do versionamento
  (`.gitignore`); arquivos locais preservados
- Docs sanitizadas: caminhos reais da infra (socket, sites-enabled) removidos
  de AGENTS.md/CHANGELOG — o runbook detalhado vive na máquina host

## [Unreleased] - 2026-08-07

### ✅ Features e mudanças de comportamento

#### Mosaico xadrez W/B no grid
- Cards `post-theme-inherit` alternam no padrão **W W W / B W B** (posições 4
  e 6 de cada 6 cards são pretas), só quando o grid está em 3 colunas
  (desktop md+ ou mosaico mobile)
- Implementado em CSS puro com `nth-child` — cobre paginação e busca sem JS;
  as vars `--bg-color`/`--text-color` são sobrescritas no card, então o padrão
  **ignora o tema global** (W sempre branco, B sempre preto)
- Cards com tema próprio (cyberpunk, matrix...) mantêm seu tema no grid

#### Seletor de tema para o leitor (página do post)
- Dropdown "Tema:" junto aos controles de zoom: o leitor troca entre os 9
  temas só para a própria leitura — **não altera o post salvo**
- Preferência em localStorage (`readerPostTheme`); opção "Do autor" restaura
  o tema escolhido pelo autor (padrão)

#### Permissões: usuário comum passa a ser read-only
- **Antes**: qualquer conta registrada podia criar posts e editar/deletar os
  próprios — na prática, qualquer visitante publicava no blog
- **Agora**: criar/editar/deletar posts e upload de teaser exigem `is_admin`;
  registro segue aberto (conta existe para futuras features), mas usuário
  comum só lê. Backend retorna 403 (JSON) ou redirect com flash em PT-BR
- UI: "+ Novo Post" (navbar) e botões Editar/Deletar (página do post) só
  aparecem para admins
- Promoção a admin segue via `flask make-admin`

### 🚨 Incidente de infraestrutura (documentado para não repetir)

**Sintoma**: mudanças deployadas não apareciam no ar, mesmo com
`systemctl restart xampuzord` e Purge Everything no Cloudflare.

**Causa raiz (dupla)**:
1. Existia uma **instância órfã do gunicorn** (iniciada manualmente, fora do
   systemd) escutando em `127.0.0.1:5000`, com código e templates antigos em
   memória.
2. A config ativa do nginx fazia `proxy_pass` para essa porta — ou seja,
   **toda a produção era servida pela órfã**. O serviço systemd (unix socket)
   estava correto, mas fora do caminho do tráfego.

Agravante: a config do nginx versionada no repo apontava um terceiro caminho
(um socket inexistente). Três fontes divergentes de verdade.

**Resolução**: `proxy_pass` repontado para o socket do systemd, validação +
reload do nginx, órfã encerrada. Verificado comparando as respostas de cada
ponta (porta direta, socket do serviço, URL pública) — a que divergia era a
culpada.

**Lição**: um único dono para o app (systemd), uma única fonte da config
nginx (repo), e nunca subir gunicorn manual "só para testar" em porta de
produção. Ver AGENTS.md > Deployment.

## [Unreleased] - 2026-08-06

### ✅ Correções

#### Mosaico 3 colunas opcional no mobile (estilo Instagram 3xM)
- Botão **▦ 3 colunas** acima do grid, visível apenas no mobile (`md:hidden`),
  alterna entre 1 coluna (padrão) e o mosaico 3xM igual ao desktop
- Preferência persistida em `localStorage` (`gridCols`), mesmo padrão do tema
  global; o rótulo do botão reflete o estado ("▦ 3 colunas" / "▤ 1 coluna")
- Implementação: `#postGrid.mosaic-3` força `grid-template-columns` via media
  query `max-width: 767px` (não interfere no desktop)
- Cache-busting: `?v=` no CSS/JS do `base.html` (nginx serve estáticos com
  `expires 30d`) — bump da data a cada mudança em CSS/JS

#### Header desktop invisível + novo logo
- **Causa raiz**: `style.css` definia `.hidden { display: none !important }`,
  que vencia o `md:flex` do Tailwind e mantinha o menu (`navMenu`) oculto
  em qualquer largura — no desktop só o logo aparecia. A utilidade local foi
  removida (o Tailwind gera a sua própria `.hidden`).
- **Hover dos botões corrigido**: o padrão `hover:bg-current hover:text-inverse`
  nunca funcionou (`text-inverse` não existe no Tailwind e `currentColor`
  acompanharia a cor nova do texto → texto invisível no hover). Substituído
  por regras em `style.css` usando `--text-color`/`--bg-color` — vale para
  todos os templates, nos dois temas globais.
- **Logo novo**: emoji 🧴 substituído pelo ícone pixel-art da caveira
  (`static/images/wp-icon.png`, extraído de `graphics/wp-icon-build.png` com
  remoção do halo semi-opaco), com `image-rendering: pixelated`.

#### Busca por tags agora é server-side de verdade
- **Antes**: a busca só escondia/mostrava os cards já carregados no cliente —
  posts fora das páginas do infinite scroll pareciam não existir
  (`searchTags` era sempre `[]` e nunca ia ao `/api/posts`).
- **Agora**: `main.js` envia a query ao `/api/posts?tags=[...]`, reconstrói
  o grid do zero e o infinite scroll continua paginando dentro do filtro
  ativo. ESC e click em tag usam o mesmo caminho. Contador de resultados
  reflete os posts carregados do filtro.
- **Backend**: o filtro de tags do `/api/posts` passou de match exato para
  substring case-insensitive ("ciber" casa "cybernetic"), igualando o
  comportamento que o usuário já conhecia da busca antiga.
- Documentação de agentes criada: `AGENTS.md` com arquitetura, convenções,
  princípios de UX e backlog priorizado de fraquezas.

## [Unreleased] - 2026-05-14

### 🎨 Features Principais Adicionadas

#### Sistema de Temas Customizados por Post
- Implementado 9 temas (inherit, dark, light, cyberpunk, matrix, vaporwave, noir, sunset, ocean)
- Campo `post_theme` no modelo Post
- Dropdown de seleção no editor
- CSS isolado por tema com custom properties
- Preview visual dos temas na página "Sobre"

#### Search/Filter por Tags
- Busca em tempo real com debounce (300ms)
- Click em tags para filtrar automaticamente
- ESC para limpar busca
- Contador de resultados ("X posts encontrados")
- Animações suaves de fade in/out

#### Sistema de Segurança
- **Rate Limiting** (Flask-Limiter):
  - Login: 10/minuto (anti brute-force)
  - Registro: 5/hora (anti spam)
  - Posts: 20/hora
  - Uploads: 10/minuto
- Variáveis de ambiente (SECRET_KEY, DATABASE_URL)
- `.env.example` criado
- SECURITY.md com guia completo (16 páginas)

#### CLI Tools de Gestão
- `flask list-users` - Lista todos usuários
- `flask reset-admin-password` - Reset interativo de senha
- `flask make-admin` - Promover usuário para admin

#### Página "Sobre"
- História e filosofia do projeto
- Lista de funcionalidades
- Tech stack detalhado
- Preview visual dos 9 temas
- Tutorial de uso

### ✅ Melhorias e Correções

#### Typography & Layout
- **Word-wrap correto**: Não quebra palavras no meio
- **Scroll horizontal**: Posts largos têm scroll, previews não
- **Auto-wrap**: Conteúdo automaticamente envolvido em `<pre><code>`
- **Alinhamento**: Previews no grid agora à esquerda (não centralizadas)

#### Editor
- Auto-save já implementado (verificado)
- Keyboard shortcuts já implementados (verificado)
- Seleção de tema integrada
- Upload de teasers funcional

#### Templates
- `500.html` criado
- `sobre.html` criado
- Link "SOBRE" na navbar funcional

### 📝 Documentação

#### Novos Arquivos
- `SECURITY.md` - Guia completo de segurança para produção
- `CHANGELOG.md` - Este arquivo
- `.env.example` - Template de configuração
- `migrate_add_post_theme.py` - Script de migração

#### Atualizados
- `README.md` - Seção de segurança expandida, comandos CLI documentados
- `CLAUDE.md` - Atualizado com todas as novas features

### 🔧 Arquivos Modificados

#### Backend (`app.py`)
- Adicionado Flask-Limiter
- Rate limiting em endpoints críticos
- Variáveis de ambiente (SECRET_KEY, DATABASE_URL)
- Campo `post_theme` no modelo Post
- Auto-wrap de conteúdo em `<pre><code>`
- CLI commands: `list-users`, `reset-admin-password`, `make-admin`
- Rota `/sobre` adicionada

#### Frontend (`main.js`)
- Search/filter por tags implementado
- Click em tags para buscar
- Post cards com temas aplicados
- Feedback visual (contador de resultados)

#### Frontend (`editor.js`)
- Seleção de tema no editor
- Tema incluído no auto-save
- Tema no payload de criação/edição

#### Estilos (`style.css`)
- 9 temas customizados (.post-theme-{nome})
- Word-wrap correto em todos elementos
- Scroll horizontal em `.post-content`
- Search bar com glow ao focar
- Tags com hover scale

#### Dependências (`requirements.txt`)
- Adicionado: `Flask-Limiter==3.5.0`

### 🐛 Issues Conhecidos (Não Resolvidos)

1. Tag count não decrementa ao deletar post
2. Tag autocomplete UI não conectado (API existe)
3. Infinite scroll não detecta fim dos posts
4. config.py não é usado (configs hardcoded em app.py)

### 📊 Estatísticas desta Sessão

- **Arquivos criados**: 7 (SECURITY.md, CHANGELOG.md, .env.example, 500.html, sobre.html, migrate_add_post_theme.py, e outros)
- **Arquivos modificados**: 9 (app.py, main.js, editor.js, style.css, README.md, CLAUDE.md, requirements.txt, base.html, templates)
- **Linhas de código adicionadas**: ~1500+
- **Features principais**: 5 (Temas, Search, Security, CLI, Sobre)
- **Bugs corrigidos**: 4 (word-wrap, scroll, 500 template, alinhamento)

### 🚀 Próximos Passos Sugeridos

1. Tag autocomplete UI (API já existe)
2. CAPTCHA no registro
3. Detecção de fim em infinite scroll
4. Usar config.py ao invés de hardcode
5. Compressão de imagens no upload
6. Headers de segurança (CSP, X-Frame-Options)

---

**Desenvolvido com Claude Code (Anthropic)**
