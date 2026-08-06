#!/bin/bash
# Cloudflare DDNS - atualiza registro A quando IP muda
# Instalar: chmod +x /usr/local/bin/cf-ddns.sh
# Cron:     */5 * * * * /usr/local/bin/cf-ddns.sh >> /var/log/cf-ddns.log 2>&1

CF_TOKEN="SEU_API_TOKEN_AQUI"
ZONE_ID="SEU_ZONE_ID_AQUI"
RECORD_NAME="xampuparaossos.com.br"
LOG_TAG="cf-ddns"

current_ip=$(curl -s https://ifconfig.me)

if [ -z "$current_ip" ]; then
    echo "$(date) [$LOG_TAG] ERRO: não foi possível obter IP público" >&2
    exit 1
fi

record_json=$(curl -s -X GET \
    "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records?type=A&name=$RECORD_NAME" \
    -H "Authorization: Bearer $CF_TOKEN" \
    -H "Content-Type: application/json")

record_ip=$(echo "$record_json" | python3 -c \
    "import sys,json; r=json.load(sys.stdin)['result']; print(r[0]['content']) if r else print('')" 2>/dev/null)

record_id=$(echo "$record_json" | python3 -c \
    "import sys,json; r=json.load(sys.stdin)['result']; print(r[0]['id']) if r else print('')" 2>/dev/null)

if [ "$current_ip" = "$record_ip" ]; then
    echo "$(date) [$LOG_TAG] IP inalterado: $current_ip"
    exit 0
fi

update=$(curl -s -X PUT \
    "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records/$record_id" \
    -H "Authorization: Bearer $CF_TOKEN" \
    -H "Content-Type: application/json" \
    --data "{\"type\":\"A\",\"name\":\"$RECORD_NAME\",\"content\":\"$current_ip\",\"ttl\":120,\"proxied\":true}")

success=$(echo "$update" | python3 -c \
    "import sys,json; print(json.load(sys.stdin).get('success', False))" 2>/dev/null)

if [ "$success" = "True" ]; then
    echo "$(date) [$LOG_TAG] IP atualizado: $record_ip -> $current_ip"
else
    echo "$(date) [$LOG_TAG] ERRO ao atualizar: $update" >&2
    exit 1
fi
