# 阶段 1: 原生交叉编译 (极其快速)
FROM --platform=$BUILDPLATFORM golang:1.21-alpine AS builder
WORKDIR /build
COPY main.go .

ARG TARGETOS
ARG TARGETARCH

# 利用 Go 原生交叉编译，不走 QEMU 模拟 [cite: 1]
RUN CGO_ENABLED=0 GOOS=$TARGETOS GOARCH=$TARGETARCH \
    go build -ldflags="-s -w" -o tunnel-manager main.go

# 阶段 2: 最终精简镜像
FROM alpine:latest
ARG TARGETARCH

RUN apk add --no-cache ca-certificates curl

# 下载对应架构的 cloudflared [cite: 1, 2, 3, 4, 5]
RUN if [ "$TARGETARCH" = "amd64" ]; then URL="amd64"; \
    elif [ "$TARGETARCH" = "arm64" ]; then URL="arm64"; \
    elif [ "$TARGETARCH" = "arm" ]; then URL="arm"; fi && \
    curl -L "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${URL}" -o /usr/local/bin/cloudflared && \
    chmod +x /usr/local/bin/cloudflared

WORKDIR /app
COPY --from=builder /build/tunnel-manager .
RUN mkdir -p /app/data

EXPOSE 12222
CMD ["./tunnel-manager"]
