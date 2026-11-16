# cloudflared-web (Rust 版)

一个用于管理 Cloudflare Tunnel（cloudflared）的轻量 Web 控制台，由原 Go 项目 [`cloudflared-web`](https://github.com/) 完整重写而来。功能与行为对齐原版：双语界面、Token 提取与持久化、隧道启动/停止、状态持久化与自动拉起、可选 Basic Auth。

## 功能

- **Web UI**：单页响应式卡片，中文 / English 一键切换；HTML 由纯 Rust 代码生成，无外部模板文件
- **Token 管理**：可直接粘贴 JWT，也可粘贴整条 Docker 命令，自动提取 `eyJh...` token 并写入 `DATA_DIR/token`
- **隧道管理**：调用 `cloudflared tunnel --no-autoupdate run --token <token>`；持续读取 stderr，出现 `Connected` / `Registered` / `Updated to new configuration` 即判定连接成功，7 秒内未成功则杀掉进程并展示原始错误
- **状态持久化**：运行状态写入 `DATA_DIR/state`；下次启动若为 `running` 且 token 存在，则自动拉起隧道
- **鉴权**：设置密码后启用 HTTP Basic Auth（用户名固定 `admin`），用户/密码比较使用常量时间算法

## 构建与运行

```bash
cargo build --release
./target/release/cloudflared-web \
  --port 12222 \
  --bin /usr/local/bin/cloudflared \
  --dir /app/data \
  --password your-password
```

浏览器中打开 `http://<host>:12222`。

## 配置

命令行参数优先级高于环境变量；仅当参数等于默认值时才会回退读取对应环境变量。

| 参数 | 环境变量 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--port` | `PORT` | `12222` | 监听端口 |
| `--bin` | `CLOUDFLARED_BIN` | `cloudflared` | cloudflared 二进制路径（默认从 PATH 查找） |
| `--dir` | `DATA_DIR` | `/app/data` | 数据目录（存放 `token`、`state`） |
| `--password` | `PASSWORD` | 空 | 设置后启用 Basic Auth；留空则不鉴权 |

Token 也可通过环境变量 `token` 或 `TOKEN` 提供（优先级：`token` > `TOKEN` > `DATA_DIR/token` 文件）。

## Docker

```bash
docker build -t cloudflared-web-rs .
docker run -d --name cfw \
  -p 12222:12222 \
  -v /path/to/cloudflared:/usr/local/bin/cloudflared:ro \
  -v cfw-data:/app/data \
  -e PASSWORD=your-password \
  cloudflared-web-rs
```

## 与原 Go 版的对齐点

| 行为 | Go 实现 | Rust 实现 |
| --- | --- | --- |
| Web 框架 | 标准库 `net/http` | `axum` + `tokio` |
| 模板 | `html/template` | 纯 Rust `format!` 拼接 + 手写 `html_escape`（防 XSS） |
| Token 提取 | 正则 `[eE]yJh[a-zA-Z0-9\-_]{50,}` | 同正则（编译一次复用） |
| 成功检测 | 扫描 stderr 关键字 + 7 秒超时 | 异步扫描 stderr 关键字 + 7 秒超时，并持续排空避免管道阻塞 |
| 鉴权 | `subtle.ConstantTimeCompare` | `subtle::ConstantTimeEq` |
| 配置优先级 | 显式参数 > 环境变量 > 默认值 | 同上 |

## CI

GitHub Actions 覆盖 `cargo fmt --check`、`cargo clippy --locked --all-targets -- -D warnings` 与 `cargo build --release --locked`。
