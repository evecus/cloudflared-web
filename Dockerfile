# 阶段 1: 编译 Go
FROM golang:1.21-alpine AS builder
WORKDIR /build
COPY main.go .
RUN go build -ldflags="-s -w" -o tunnel-manager main.go

# 阶段 2: 最终镜像
FROM alpine:latest
ARG TARGETARCH

# [span_3](start_span)安装运行环境所需的最小依赖[span_3](end_span)
RUN apk add --no-cache ca-certificates curl

# [span_4](start_span)[span_5](start_span)下载 cloudflared 二进制[span_4](end_span)[span_5](end_span)
RUN if [ "$TARGETARCH" = "amd64" ]; then URL="amd64"; \
    elif [ "$TARGETARCH" = "arm64" ]; then URL="arm64"; \
    else URL="arm"; fi && \
    curl -L "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${URL}" -o /usr/local/bin/cloudflared && \
    chmod +x /usr/local/bin/cloudflared

WORKDIR /app
COPY --from=builder /build/tunnel-manager .

EXPOSE 12222
CMD ["./tunnel-manager"]
