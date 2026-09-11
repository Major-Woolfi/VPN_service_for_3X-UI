cd /root/bots/vpn_bot/ || exit 1

docker build -t vpn_bot .
docker rm -f vpn_bot 2>/dev/null || true
docker run -d --name vpn_bot --restart always -p 2005:2005 -v "$(pwd)":/app vpn_bot

echo "✅ Deployed! Logs: docker logs -f  vpn_bot "
