# Changelog - Xampu Para Ossos

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
