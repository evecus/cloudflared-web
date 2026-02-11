from flask import Flask, request, render_template_string
import subprocess
import os
import signal

app = Flask(__name__)
tunnel_process = None
LOG_FILE = "tunnel.log"

# HTML 模板：增加了自动刷新和更好的样式
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cloudflared Manager</title>
    <style>
        body { font-family: -apple-system, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; line-height: 1.6; }
        .card { border: 1px solid #ddd; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        input { padding: 12px; width: 80%; border: 1px solid #ccc; border-radius: 4px; margin-bottom: 15px; font-family: monospace; }
        .controls { margin: 20px 0; }
        button { padding: 10px 25px; cursor: pointer; border: none; border-radius: 4px; font-weight: bold; transition: 0.3s; }
        .btn-start { background-color: #28a745; color: white; }
        .btn-start:hover { background-color: #218838; }
        .btn-stop { background-color: #dc3545; color: white; margin-left: 10px; }
        .btn-stop:hover { background-color: #c82333; }
        .status { font-size: 1.2em; margin-bottom: 10px; }
        .status.on { color: #28a745; }
        .status.off { color: #dc3545; }
        pre { background: #2d2d2d; color: #ccc; padding: 15px; height: 400px; overflow-y: auto; border-radius: 4px; font-size: 13px; line-height: 1.4; }
        h2 { margin-top: 0; color: #333; }
    </style>
</head>
<body>
    <div class="card">
        <h2>Cloudflared 隧道管理</h2>
        
        <form method="post">
            <input type="text" name="token" placeholder="在此粘贴你的 Cloudflare Tunnel Token" value="{{ token }}">
            <div class="controls">
                <button type="submit" name="action" value="start" class="btn-start">▶ 运行</button>
                <button type="submit" name="action" value="stop" class="btn-stop">■ 停止</button>
            </div>
        </form>

        <div class="status {{ 'on' if '运行' in status else 'off' }}">
            当前状态: {{ status }}
        </div>

        <h3>运行日志:</h3>
        <pre id="log-container">{{ logs }}</pre>
    </div>

    <script>
        // 自动滚动日志到底部
        const logBox = document.getElementById('log-container');
        logBox.scrollTop = logBox.scrollHeight;

        // 如果正在运行，每 3 秒刷新一次页面以获取最新日志
        {% if '运行' in status %}
        setTimeout(() => {
            window.location.reload();
        }, 3000);
        {% endif %}
    </script>
</body>
</html>
"""

@app.route('/', methods=['GET', 'POST'])
def index():
    global tunnel_process
    token = request.form.get('token', '')

    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'start' and token:
            # 1. 如果已有进程，先彻底关闭
            if tunnel_process and tunnel_process.poll() is None:
                tunnel_process.terminate()
                tunnel_process.wait()
            
            # 2. 清空并准备日志文件
            with open(LOG_FILE, "w") as f:
                f.write("--- 正在启动 Cloudflared ---\n")
            
            # 3. 启动进程：使用正确的子命令逻辑
            # 命令格式: cloudflared tunnel run --token <TOKEN>
            log_f = open(LOG_FILE, "a")
            try:
                tunnel_process = subprocess.Popen(
                    ['cloudflared', 'tunnel', 'run', '--token', token.strip()],
                    stdout=log_f,
                    stderr=log_f,
                    text=True
                )
            except Exception as e:
                with open(LOG_FILE, "a") as f:
                    f.write(f"启动异常: {str(e)}")

        elif action == 'stop':
            if tunnel_process:
                tunnel_process.terminate()
                tunnel_process.wait()
                tunnel_process = None
                with open(LOG_FILE, "a") as f:
                    f.write("\n--- 服务已手动停止 ---\n")

    # 获取当前状态
    is_running = tunnel_process and tunnel_process.poll() is None
    status_text = "🟢 正在运行" if is_running else "🔴 已停止"
    
    # 读取日志
    logs = ""
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r") as f:
                logs = f.read()
        except:
            logs = "无法读取日志文件"

    return render_template_string(
        HTML_TEMPLATE, 
        status=status_text, 
        token=token, 
        logs=logs
    )

if __name__ == '__main__':
    # 按照你的要求，固定端口 1450
    app.run(host='0.0.0.0', port=1450, debug=False)
