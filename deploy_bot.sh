#!/bin/bash

cd /root/bots/VPN_bot/ || exit 1

docker build -t VPN_bot .
docker rm -f VPN_bot 2>/dev/null || true
docker run -d --name VPN_bot --restart always -v "$(pwd)":/app VPN_bot

echo "✅ Deployed! Logs: docker logs -f  VPN_bot "
