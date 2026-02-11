from flask import Flask, request, render_template_string
import subprocess
import os
import time
import re

app = Flask(__name__)
tunnel_process = None
LOG_FILE = "tunnel.log"
# 预留挂载目录下的 token 文件路径
TOKEN_PATH = "token" 

# --- 界面设计 ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cloudflared Dashboard</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        :root { --primary: #6366f1; --success: #22c55e; --danger: #ef4444; }
        body { font-family: 'PingFang SC', sans-serif; background: #f0f2f5; margin: 0; display: flex; justify-content: center; align-items: center; min-height: 100vh; }
        .card { background: white; border-radius: 24px; padding: 35px; width: 90%; max-width: 440px; box-shadow: 0 20px 40px rgba(0,0,0,0.05); text-align: center; }
        .icon-header { font-size: 40px; color: var(--primary); margin-bottom: 10px; }
        h2 { margin: 0; color: #1e293b; }
        .sub { color: #94a3b8; font-size: 13px; margin-bottom: 20px; }
        textarea { width: 100%; padding: 15px; border-radius: 15px; border: 2px solid #f1f5f9; outline: none; box-sizing: border-box; font-family: monospace; font-size: 12px; background: #f8fafc; resize: none; }
        textarea:disabled { background: #e2e8f0; cursor: not-allowed; color: #64748b; }
        .btn-group { display: flex; gap: 10px; margin-top: 15px; flex-wrap: wrap; }
        button { flex: 1; min-width: 100px; padding: 12px; border-radius: 12px; border: none; cursor: pointer; font-weight: 600; transition: 0.3s; display: flex; align-items: center; justify-content: center; gap: 5px; }
        .run { background: var(--primary); color: white; }
        .stop { background: #fee2e2; color: var(--danger); }
        .save { background: #f1f5f9; color: #1e293b; border: 1px solid #e2e8f0; }
        button:disabled { opacity: 0.5; cursor: not-allowed; }
        .status-bar { margin-top: 20px; padding: 15px; border-radius: 15px; font-weight: 600; font-size: 14px; display: flex; align-items: center; justify-content: center; gap: 8px; }
        .success { background: #dcfce7; color: #15803d; }
        .fail { background: #fef2f2; color: #991b1b; }
        .info { background: #f1f5f9; color: #475569; }
        .dot { width: 8px; height: 8px; background: currentColor; border-radius: 50%; animation: blink 1s infinite; }
        @keyframes blink { 0% { opacity: 1; } 50% { opacity: 0.3; } 100% { opacity: 1; } }
    </style>
</head>
<body>
    <div class="card">
        <div class="icon-header"><i class="fa-solid fa-server"></i></div>
        <h2>隧道管理面板</h2>
        <p class="sub">运行时将锁定输入框，保护配置安全</p>
        
        <form method="post">
            <textarea name="raw_input" rows="4" placeholder="粘贴 Token 或 Docker 命令..." {{ 'disabled' if is_running }}>{{ current_token }}</textarea>
            
            <div class="btn-group">
                {% if not is_running %}
                    <button type="submit" name="action" value="save" class="save"><i class="fa-solid fa-floppy-disk"></i> 保存配置</button>
                    <button type="submit" name="action" value="start" class="run"><i class="fa-solid fa-play"></i> 启动隧道</button>
                {% else %}
                    <button type="submit" name="action" value="stop" class="stop"><i class="fa-solid fa-stop"></i> 停止隧道</button>
                {% endif %}
            </div>
        </form>

        {% if message %}
        <div class="status-bar {{ msg_class }}">
            {% if '成功' in message %}<div class="dot"></div>{% endif %}
            {{ message }}
        </div>
        {% endif %}
    </div>
</body>
</html>
"""

def extract_token(text):
    cleaned = re.sub(r'[\\\n\r\t\s]', '', text)
    match = re.search(r'[eE]yJh[a-zA-Z0-9\-_]{50,}', cleaned)
    return match.group(0) if match else cleaned

def load_saved_token():
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, "r") as f:
            return f.read().strip()
    return ""

@app.route('/', methods=['GET', 'POST'])
def index():
    global tunnel_process
    message, msg_class = "", "info"
    # 页面初始加载已保存的 Token
    current_token = load_saved_token()
    is_running = tunnel_process is not None and tunnel_process.poll() is None

    if request.method == 'POST':
        action = request.form.get('action')
        raw_input = request.form.get('raw_input', '').strip()

        if action == 'save' and not is_running:
            if raw_input:
                token = extract_token(raw_input)
                with open(TOKEN_PATH, "w") as f:
                    f.write(token)
                current_token = token
                message, msg_class = "配置已成功保存到挂载目录", "info"
            else:
                message, msg_class = "请输入有效内容后再保存", "fail"

        elif action == 'start' and not is_running:
            # 优先使用当前输入的内容，如果为空则使用已保存的
            token_to_run = extract_token(raw_input) if raw_input else current_token
            
            if token_to_run:
                with open(LOG_FILE, "w") as f: f.write("")
                log_f = open(LOG_FILE, "a")
                tunnel_process = subprocess.Popen(
                    ['cloudflared', 'tunnel', '--no-autoupdate', 'run', '--token', token_to_run],
                    stdout=log_f, stderr=log_f, text=True
                )
                time.sleep(4)
                with open(LOG_FILE, "r") as f:
                    logs = f.read()
                    if "Connected" in logs or "Registered" in logs:
                        message, msg_class, is_running = "cloudflared隧道连接成功", "success", True
                        current_token = token_to_run # 运行成功同步显示
                    else:
                        message, msg_class = "cloudflared隧道连接失败，请检查Token", "fail"
            else:
                message, msg_class = "没有可用的 Token，请先输入或保存", "fail"

        elif action == 'stop':
            if tunnel_process:
                tunnel_process.terminate()
                tunnel_process.wait()
                tunnel_process = None
                is_running = False
                message = "cloudflared隧道已断开，输入框已解锁"

    return render_template_string(
        HTML_TEMPLATE, 
        current_token=current_token, 
        message=message, 
        msg_class=msg_class, 
        is_running=is_running
    )

if __name__ == '__main__':
    # 启动时自动检查是否有保存的文件并尝试静默启动
    saved = load_saved_token()
    if saved:
        log_f = open(LOG_FILE, "a")
        tunnel_process = subprocess.Popen(
            ['cloudflared', 'tunnel', '--no-autoupdate', 'run', '--token', saved],
            stdout=log_f, stderr=log_f, text=True
        )
    app.run(host='0.0.0.0', port=12222)
