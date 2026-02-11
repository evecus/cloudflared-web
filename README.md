docker run -d \
  --name cf-manager \
  --restart always \
  -p 1450:1450 \
  -v /cf-config:/app \
  ghcr.io/evecus/cloudflared-web:latest
