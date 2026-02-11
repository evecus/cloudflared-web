FROM python:3.10-slim

WORKDIR /app
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# 自动识别架构下载对应的 cloudflared
RUN ARCH=$(uname -m) && \
    if [ "$ARCH" = "x86_64" ]; then URL="amd64"; \
    elif [ "$ARCH" = "aarch64" ]; then URL="arm64"; \
    else URL="arm"; fi && \
    curl -L "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${URL}" -o /usr/local/bin/cloudflared && \
    chmod +x /usr/local/bin/cloudflared

COPY app.py .
RUN pip install flask

EXPOSE 1450
CMD ["python", "app.py"]
