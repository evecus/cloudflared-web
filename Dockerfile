# 阶段 1: 编译
FROM --platform=$BUILDPLATFORM golang:1.21-alpine AS builder
WORKDIR /build
COPY main.go .
# 强制开启 CGO_ENABLED=0 以获得静态二进制文件，确保在 alpine 运行不报错
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o tunnel-manager main.go

# 阶段 2: 最终运行镜像
FROM alpine:latest
ARG TARGETARCH

RUN apk add --no-cache ca-certificates curl

# [span_5](start_span)下载对应架构的 cloudflared[span_5](end_span)
RUN if [ "$TARGETARCH" = "amd64" ]; then URL="amd64"; \
    elif [ "$TARGETARCH" = "arm64" ]; then URL="arm64"; \
    elif [ "$TARGETARCH" = "arm" ]; then URL="arm"; fi && \
    curl -L "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${URL}" -o /usr/local/bin/cloudflared && \
    chmod +x /usr/local/bin/cloudflared

WORKDIR /app
COPY --from=builder /build/tunnel-manager .

EXPOSE 12222
CMD ["./tunnel-manager"]
