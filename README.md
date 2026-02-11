docker run -d \
  --name cf-manager \
  --restart always \
  --network host \
  -v /cf-config:/app \
  ghcr.io/evecus/cloudflared-web:latest


  port:12222
