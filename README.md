# ☁️ Cloudflared Pro Manager

[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-ready-emerald)](https://www.docker.com/)
[![License](https://img.shields.io/badge/license-MIT-purple.svg)](LICENSE)

**Cloudflared Pro Manager** 是一个基于 Flask 开发的轻量化隧道管理面板。它拥有现代化的响应式界面、自动化的环境变量处理逻辑，并针对移动端和桌面端进行了深度视觉优化。

---

## ✨ 核心特性

* 🎨 **现代化视觉设计**：采用毛玻璃质感 (Glassmorphism) 与动态渐变背景。
* 🚀 **双模式自动切换**：
    * **环境变量模式**：检测到 `token` 变量时自动锁定配置，隐藏输入框并改用精致卡片展示。
    * **本地保存模式**：支持手动输入并持久化保存 Token 至本地文件。
* 🔡 **极致代码观感**：集成 **JetBrains Mono** 编程字体，让 Token 展示具备专业代码质感。
* 📊 **智能状态监测**：实时扫描隧道日志，精准反馈连接成功或失败状态。
* 📱 **响应式布局**：针对手机端优化，大按钮设计方便触控操作。

---

## 🛠️ 快速开始

### 1. 环境变量部署 (推荐)
使用 Docker 运行是最简单的方式。通过 `-e` 传入 Token 即可直接启动：

```bash
docker run -d \
  --name cf-manager \
  --network=host \
  -v /opt/cf-manager/data:/app/data \
  -e token="你的_CLOUDFLARE_TOKEN" \
  --restart always \
  evecus/cloudflared-web:latest

### 2. 本地保存模式 (灵活调试)
如果你启动时未设置环境变量，面板将开启本地交互模式

```bash
docker run -d \
  --name cf-manager \
  --network=host \
  -v /opt/cf-manager/data:/app/data \
  --restart always \
  evecus/cloudflared-web:latest

访问地址：http://localhost:12222
