☁️ Cloudflared Pro Manager

[Python] [Docker] [License]

Cloudflared Pro Manager 是一个基于 Flask 开发的轻量级 Cloudflare Tunnel
管理面板。 它提供现代化界面设计、自动化 Token
管理逻辑，以及实时隧道状态监控功能。

------------------------------------------------------------------------

✨ 核心特性

-   🎨 现代化 UI 设计（Glassmorphism 毛玻璃风格 + 动态渐变背景）
-   🚀 双模式自动切换：
    -   环境变量模式（自动锁定 Token 配置）
    -   本地保存模式（支持持久化 Token）
-   🔡 JetBrains Mono 编程字体，提升 Token 显示体验
-   📊 实时日志监测，自动判断隧道连接状态
-   📱 响应式布局，完美适配移动端与桌面端

------------------------------------------------------------------------

🛠️ 快速开始

方式一：环境变量模式（推荐生产环境）

使用 Docker 运行，并通过 -e 传入 Cloudflare Tunnel Token：

docker run -d
–name cf-manager
–network=host
-e token=“你的_CLOUDFLARE_TOKEN”
–restart always
evecus/cloudflared-web:latest

特点： - 自动检测 token 环境变量 - 锁定输入框 - 使用卡片形式展示当前
Token - 适合服务器或长期运行环境

------------------------------------------------------------------------

方式二：本地保存模式（适合测试或调试）

未设置环境变量时，系统自动进入交互模式：

docker run -d
–name cf-manager
–network=host
-v /opt/cf-manager/data:/app/data
–restart always
evecus/cloudflared-web:latest

访问地址： http://localhost:12222

特点： - 支持网页输入 Token - 自动保存至 /app/data 目录 - 可重复修改

------------------------------------------------------------------------

📦 数据持久化说明

建议在生产环境中挂载数据目录：

-v /opt/cf-manager/data:/app/data

以确保 Token 和配置文件不会因容器重建而丢失。

------------------------------------------------------------------------

🔒 安全建议

-   请勿在公共网络环境暴露管理端口
-   建议通过反向代理 + HTTPS 使用
-   可结合 Cloudflare Zero Trust 进行访问控制

------------------------------------------------------------------------

📜 License

MIT License
