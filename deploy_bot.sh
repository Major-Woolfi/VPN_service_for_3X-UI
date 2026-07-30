cd /root/bots/VPN_bot_for_3X-UI_bot/ || exit 1

docker build -t vpn_bot_for_3x-ui_bot .
docker rm -f vpn_bot_for_3x-ui_bot 2>/dev/null || true
docker run -d --name vpn_bot_for_3x-ui_bot --restart always -v "$(pwd)":/app vpn_bot_for_3x-ui_bot

echo "✅ Deployed! Logs: docker logs -f  vpn_bot_for_3x-ui_bot "
