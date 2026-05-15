# 🔐 Guia de Segurança - Xampu Para Ossos

Este guia detalha as medidas de segurança implementadas e as configurações necessárias para hospedar o blog com segurança na internet.

## ✅ Medidas de Segurança Implementadas

### 1. **Rate Limiting**
Proteção contra ataques de força bruta e spam:

| Endpoint | Limite | Objetivo |
|----------|--------|----------|
| `/login` | 10 por minuto | Prevenir brute force de senhas |
| `/register` | 5 por hora | Prevenir criação massiva de contas |
| `/post/new` | 20 por hora | Prevenir spam de posts |
| `/api/upload/teaser` | 10 por minuto | Prevenir abuso de upload |
| Global | 200/dia, 50/hora | Limite geral |

### 2. **Autenticação Segura**
- ✅ Senhas hasheadas com **Werkzeug PBKDF2** (não armazena plaintext)
- ✅ Flask-Login para gestão de sessões
- ✅ Session cookies com HTTPOnly
- ✅ Ownership checks em operações sensíveis

### 3. **Sanitização de Conteúdo**
- ✅ **Bleach** sanitiza todo HTML de posts (previne XSS)
- ✅ Whitelist de tags HTML permitidas
- ✅ Validação de uploads (tipo, tamanho, extensão)
- ✅ Filenames seguros com `secure_filename()`

### 4. **Validação de Uploads**
- ✅ Tamanho máximo: 16MB
- ✅ Extensões permitidas: PNG, JPG, JPEG, GIF, WEBP
- ✅ Renomeação com UUID (evita path traversal)
- ✅ Validação de MIME type

### 5. **Controle de Acesso**
- ✅ `@login_required` em rotas protegidas
- ✅ Verificação de ownership (só autor ou admin pode editar/deletar)
- ✅ Role-based access (admin dashboard)

## ⚠️ Configurações OBRIGATÓRIAS para Produção

### 1. **SECRET_KEY**

**NUNCA use a chave padrão em produção!**

Gere uma chave forte:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Configure como variável de ambiente:
```bash
export SECRET_KEY="sua-chave-gerada-aqui"
```

### 2. **HTTPS Obrigatório**

Configure SSL/TLS no seu servidor. Opções:

**Opção A: Nginx como reverse proxy**
```nginx
server {
    listen 443 ssl;
    server_name seu-dominio.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Host $host;
    }
}
```

**Opção B: Certificado Let's Encrypt (gratuito)**
```bash
sudo apt-get install certbot python3-certbot-nginx
sudo certbot --nginx -d seu-dominio.com
```

### 3. **Banco de Dados PostgreSQL**

Não use SQLite em produção! Configure PostgreSQL:

```bash
# Instalar PostgreSQL
sudo apt-get install postgresql postgresql-contrib

# Criar database e usuário
sudo -u postgres createdb xampuparaossos
sudo -u postgres createuser xampuuser -P

# Configurar DATABASE_URL
export DATABASE_URL="postgresql://xampuuser:senha@localhost:5432/xampuparaossos"
```

### 4. **Variáveis de Ambiente**

Crie arquivo `.env` (NÃO commite no git!):

```bash
SECRET_KEY=sua-chave-forte-aqui
DATABASE_URL=postgresql://user:pass@host:5432/db
FLASK_ENV=production
FLASK_DEBUG=False
```

Carregue com python-dotenv (já instalado):
```python
from dotenv import load_dotenv
load_dotenv()
```

### 5. **Firewall e Portas**

Configure firewall para permitir apenas portas necessárias:

```bash
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable
```

### 6. **Processo de Deploy com Gunicorn**

Use Gunicorn em produção (NÃO `flask run`):

```bash
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

Ou com systemd service:
```ini
# /etc/systemd/system/xampuparaossos.service
[Unit]
Description=Xampu Para Ossos Blog
After=network.target

[Service]
User=www-data
WorkingDirectory=/var/www/boneshampoo
Environment="PATH=/var/www/boneshampoo/venv/bin"
EnvironmentFile=/var/www/boneshampoo/.env
ExecStart=/var/www/boneshampoo/venv/bin/gunicorn -w 4 -b 127.0.0.1:5000 app:app

[Install]
WantedBy=multi-user.target
```

## 🛡️ Checklist de Segurança Pré-Deploy

### Obrigatório:
- [ ] Gerar SECRET_KEY forte e única
- [ ] Configurar HTTPS com certificado válido
- [ ] Migrar para PostgreSQL (não usar SQLite)
- [ ] Setar `FLASK_DEBUG=False`
- [ ] Setar `FLASK_ENV=production`
- [ ] Configurar firewall (ufw/iptables)
- [ ] Usar Gunicorn (não flask run)
- [ ] Configurar backup automático do banco
- [ ] Testar rate limiting funcionando
- [ ] Verificar que .env não está no git

### Recomendado:
- [ ] Implementar CAPTCHA no registro (futuro)
- [ ] Configurar logs centralizados
- [ ] Monitoring (Sentry, etc)
- [ ] Backup automático de uploads
- [ ] CDN para static files
- [ ] Compressão de imagens no upload
- [ ] Headers de segurança (CSP, X-Frame-Options, etc)

## 📊 Monitoramento

### Logs de Segurança

Monitore tentativas de ataque:
```bash
# Rate limit violations
grep "429" /var/log/nginx/access.log

# Failed login attempts
grep "Invalid credentials" application.log
```

### Alertas Recomendados

Configure alertas para:
- Múltiplas tentativas de login falhadas
- Rate limit atingido repetidamente
- Uploads muito grandes
- Erros 500 frequentes

## 🚨 Vulnerabilidades Conhecidas

### Médio Risco:
1. **config.py não usado**: Configurações hardcoded em app.py (use variáveis de ambiente)
2. **Tag count não decrementa**: Bug ao deletar posts (não é segurança crítica)
3. **Sem CAPTCHA**: Registro vulnerável a bots (implementar Google reCAPTCHA)

### Baixo Risco:
1. **Infinite scroll não para**: UX issue, não segurança
2. **Search não persiste**: UX issue, não segurança

## 🔍 Auditoria de Segurança

### Ferramentas Recomendadas:

```bash
# Vulnerabilidades em dependências Python
pip install safety
safety check

# Análise estática de código
pip install bandit
bandit -r . -f json -o security-report.json

# Scan de portas abertas
nmap -sV seu-dominio.com
```

## 📞 Reportar Vulnerabilidade

Se encontrar uma vulnerabilidade de segurança, **NÃO abra uma issue pública**.

Contate de forma privada:
- Email: (adicionar email de contato)
- GitHub Security Advisory

## 📚 Recursos Adicionais

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Flask Security Best Practices](https://flask.palletsprojects.com/en/latest/security/)
- [Mozilla Web Security](https://infosec.mozilla.org/guidelines/web_security)

---

**Última atualização**: 2026-05-11
**Versão do guia**: 1.0
