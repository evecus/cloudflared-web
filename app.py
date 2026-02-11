from flask import Flask, request, render_template_string
import subprocess
import os
import time

app = Flask(__name__)
tunnel_process = None
LOG_FILE = "tunnel.log"

# --- HTML 界面设计 ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cloudflared 控制面板</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        :root {
            --primary: #6366f1;
            --success: #22c55e;
            --danger: #ef4444;
            --bg: #f8fafc;
        }
        body { 
            font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif; 
            background: var(--bg);
            margin: 0; display: flex; justify-content: center; align-items: center; height: 100vh;
        }
        .container {
            background: rgba(255, 255, 255, 0.8);
            backdrop-filter: blur(10px);
            border-radius: 24px;
            padding: 40px;
            width: 90%; max-width: 450px;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
            text-align: center;
        }
        .logo { font-size: 48px; color: var(--primary); margin-bottom: 20px; }
        h2 { margin: 10px 0; color: #1e293b; }
        .input-group { margin: 30px 0; position: relative; }
        input {
            width: 100%; padding: 12px 15px; border-radius: 12px;
            border: 2px solid #e2e8f0; outline: none; transition: 0.3s;
            box-sizing: border-box; font-family: monospace;
        }
        input:focus { border-color: var(--primary); box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.1); }
        
        .btn-group { display: flex; gap: 15px; justify-content: center; }
        button {
            padding: 12px 28px; border-radius: 12px; border: none;
            cursor: pointer; font-weight: 600; display: flex; align-items: center; gap: 8px;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .run-btn { background: linear-gradient(135deg, #6366f1, #a855f7); color: white; }
        .run-btn:hover { transform: translateY(-2px); box-shadow: 0 10px 15px -3px rgba(99, 102, 241, 0.4); }
        .stop-btn { background: #fee2e2; color: #ef4444; }
        .stop-btn:hover { background: #fecaca; }

        .status-card {
            margin-top: 30px; padding: 20px; border-radius: 16px;
            font-size: 16px; font-weight: bold;
            display: flex; align-items: center; justify-content: center; gap: 10px;
        }
        .status-success { background: #dcfce7; color: #15803d; border: 1px solid #bbf7d0; }
        .status-fail { background: #fee2e2; color: #b91c1c; border: 1px solid #fecaca; }
        .status-info { background: #f1f5f9; color: #475569; border: 1px solid #e2e8f0; }
        
        .pulse {
            width: 10px; height: 10px; border-radius: 50%;
            background: currentColor; animation: pulse-animation 2s infinite;
        }
        @keyframes pulse-animation {
            0% { box-shadow: 0 0 0 0px rgba(34, 197, 94, 0.4); }
            100% { box-shadow: 0 0 0 10px rgba(34, 197, 94, 0); }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="logo"><i class="fa-solid fa-cloud-bolt"></i></div>
        <h2>Cloudflared 隧道管理</h2>
        <p style="color: #64748b; font-size: 14px;">请输入 Token 启动加密通道</p>

        <form method="post">
            <div class="input-group">
                <input type="text" name="token" placeholder="Tunnel Token..." value="{{ token }}" autocomplete="off">
            </div>
            <div class="btn-group">
                <button type="submit" name="action" value="start" class="run-btn">
                    <i class="fa-solid fa-play"></i> 运行
                </button>
                <button type="submit" name="action" value="stop" class="stop-btn">
                    <i class="fa-solid fa-power-off"></i> 停止
                </button>
            </div>
        </form>

        {% if message %}
        <div class="status-card {{ msg_class }}">
            {% if '成功' in message %}<div class="pulse"></div>{% endif %}
            <i class="{{ icon }}"></i> {{ message }}
        </div>
        {% endif %}
    </div>
</body>
</html>
"""

def check_tunnel_status():
    """检查日志文件确定连接是否成功"""
    if not os.path.exists(LOG_FILE):
        return "wait"
    with open(LOG_FILE, "r") as f:
        content = f.read()
        if "Connected" in content or "Registered" in content:
            return "success"
        if "error" in content.lower() or "failed" in content.lower():
            return "fail"
    return "wait"

@app.route('/', methods=['GET', 'POST'])
def index():
    global tunnel_process
    message = ""
    msg_class = "status-info"
    icon = "fa-solid fa-circle-info"
    token = request.form.get('token', '')

    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'start' and token:
            if tunnel_process:
                tunnel_process.terminate()
            
            with open(LOG_FILE, "w") as f: f.write("")
            log_f = open(LOG_FILE, "a")
            
            tunnel_process = subprocess.Popen(
                ['cloudflared', 'tunnel', 'run', '--token', token.strip()],
                stdout=log_f, stderr=log_f, text=True
            )
            
            # 给一点点启动时间然后检测
            time.sleep(2)
            res = check_tunnel_status()
            if res == "success":
                message = "Cloudflared 隧道连接成功"
                msg_class = "status-success"
                icon = "fa-solid fa-check-circle"
            else:
                message = "Cloudflared 隧道连接失败，请重试"
                msg_class = "status-fail"
                icon = "fa-solid fa-circle-xmark"

        elif action == 'stop':
            if tunnel_process:
                tunnel_process.terminate()
                tunnel_process.wait()
                tunnel_process = None
                message = "Cloudflared 隧道已断开"
                msg_class = "status-info"
                icon = "fa-solid fa-link-slash"
            else:
                message = "隧道当前未运行"

    return render_template_string(HTML_TEMPLATE, token=token, message=message, msg_class=msg_class, icon=icon)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=1450)
