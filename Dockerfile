# 使用特定的变量标识目标架构
FROM --platform=$TARGETPLATFORM python:3.10-slim

# 声明变量以便在构建中使用
ARG TARGETARCH

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# 根据 TARGETARCH (由 Buildx 自动传入) 下载对应版本
RUN if [ "$TARGETARCH" = "amd64" ]; then \
        URL="amd64"; \
    elif [ "$TARGETARCH" = "arm64" ]; then \
        URL="arm64"; \
    elif [ "$TARGETARCH" = "arm" ]; then \
        URL="arm"; \
    fi && \
    curl -L "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${URL}" -o /usr/local/bin/cloudflared && \
    chmod +x /usr/local/bin/cloudflared

WORKDIR /app
RUN pip install --no-cache-dir flask
COPY app.py .

EXPOSE 1450
CMD ["python", "app.py"]
