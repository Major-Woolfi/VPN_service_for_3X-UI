cd /root/bots/PhantomVPN_bot/ || exit 1

docker build -t phantomvpn_bot .
docker rm -f phantomvpn_bot 2>/dev/null || true
docker run -d --name phantomvpn_bot --restart always -p 2005:2005 -v "$(pwd)":/app phantomvpn_bot

echo "✅ Deployed! Logs: docker logs -f  phantomvpn_bot "
