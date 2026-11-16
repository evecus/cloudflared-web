# ---------- 构建阶段 ----------
FROM rust:1.83-slim AS builder
WORKDIR /build
COPY Cargo.toml Cargo.lock ./
COPY src ./src
RUN cargo build --release --locked

# ---------- 运行阶段 ----------
FROM debian:bookworm-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*

COPY --from=builder /build/target/release/cloudflared-web /usr/local/bin/cloudflared-web

# 将 cloudflared 二进制放到 /usr/local/bin/cloudflared（也可通过 CLOUDFLARED_BIN 指定其他路径）
# 例如：docker run -v /path/to/cloudflared:/usr/local/bin/cloudflared ...

RUN mkdir -p /app/data
ENV PORT=12222 \
    DATA_DIR=/app/data \
    CLOUDFLARED_BIN=/usr/local/bin/cloudflared
EXPOSE 12222

ENTRYPOINT ["cloudflared-web"]
