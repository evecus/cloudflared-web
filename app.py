from flask import Flask, request, render_template_string
import subprocess
import os
import time
import re

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
    <title>Cloudflared Manager</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        :root {
            --primary: #6366f1;
            --primary-light: #a855f7;
            --success: #22c55e;
            --danger: #ef4444;
            --bg: #f0f2f5;
        }
        body { 
            font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif; 
            background: linear-gradient(135deg, #e0e7ff 0%, #f3e8ff 100%);
            margin: 0; display: flex; justify-content: center; align-items: center; min-height: 100vh;
        }
        .container {
            background: rgba(255, 255, 255, 0.9);
            backdrop-filter: blur(20px);
            border-radius: 30px;
            padding: 40px;
            width: 90%; max-width: 480px;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.1);
            text-align: center;
            border: 1px solid rgba(255, 255, 255, 0.3);
        }
        .icon-box { 
            width: 80px; height: 80px; background: white; border-radius: 20px;
            display: flex; align-items: center; justify-content: center;
            margin: 0 auto 20px; font-size: 40px; color: var(--primary);
            box-shadow: 0 10px 15px -3px rgba(99, 102, 241, 0.2);
        }
        h2 { margin: 10px 0; color: #1e293b; font-weight: 800; }
        .desc { color: #64748b; font-size: 14px; margin-bottom: 25px; }
        
        .input-group { margin-bottom: 25px; }
        textarea {
            width: 100%; padding: 15px; border-radius: 15px;
            border: 2px solid #e2e8f0; outline: none; transition: 0.3s;
            box-sizing: border-box; font-family: monospace; font-size: 13px;
            background: #f8fafc; resize: none;
        }
        textarea:focus { border-color: var(--primary); background: white; box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.1); }
        
        .btn-group { display: flex; gap: 15px; }
        button {
            flex: 1; padding: 14px; border-radius: 15px; border: none;
            cursor: pointer; font-weight: 700; display: flex; align-items: center; justify-content: center; gap: 8px;
            transition: all 0.3s ease; font-size: 16px;
        }
        .run-btn { background: linear-gradient(135deg, var(--primary), var(--primary-light)); color: white; }
        .run-btn:hover { transform: translateY(-3px); box-shadow: 0 12px 20px -5px rgba(99, 102, 241, 0.4); }
        .stop-btn { background: #f1f5f9; color: #64748b; }
        .stop-btn:hover { background: #e2e8f0; color: #1e293b; }

        .status-card {
            margin-top: 30px; padding: 18px; border-radius: 18px;
            font-size: 15px; font-weight: 600;
            display: flex; align-items: center; justify-content: center; gap: 12px;
            animation: slideUp 0.4s ease-out;
        }
        .status-success { background: #f0fdf4; color: #166534; border: 1px solid #bbf7d0; }
        .status-fail { background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }
        .status-info { background: #f8fafc; color: #475569; border: 1px solid #e2e8f0; }
        
        @keyframes slideUp { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        
        .pulse {
            width: 12px; height: 12px; border-radius: 50%;
            background: #22c55e; position: relative;
        }
        .pulse::after {
            content: ""; position: absolute; width: 100%; height: 100%;
            background: inherit; border-radius: 50%;
            animation: pulse-ring 1.5s cubic-bezier(0.24, 0, 0.38, 1) infinite;
        }
        @keyframes pulse-ring { 0% { transform: scale(1); opacity: 0.6; } 100% { transform: scale(3); opacity: 0; } }
    </style>
</head>
<body>
    <div class="container">
        <div class="icon-box"><i class="fa-solid fa-rocket"></i></div>
        <h2>隧道控制台</h2>
        <p class="desc">支持粘贴原始 Docker 命令或纯 Token</p>

        <form method="post">
            <div class="input-group">
                <textarea name="raw_input" rows="3" placeholder="在此粘贴 Token 或 Docker 命令...">{{ raw_input }}</textarea>
            </div>
            <div class="btn-group">
                <button type="submit" name="action" value="start" class="run-btn">
                    <i class="fa-solid fa-play"></i> 启动隧道
                </button>
                <button type="submit" name="action" value="stop" class="stop-btn">
                    <i class="fa-solid fa-stop"></i> 停止
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

def extract_token(text):
    """自动从各种输入中提取 Token"""
    # 匹配以 eyJhI 形状开头的 Base64 字符串
    match = re.search(r'eyJhS[a-zA-Z0-9\-_]{30,}', text)
    if match:
        return match.group(0)
    return text.strip()

def check_tunnel_status():
    if not os.path.exists(LOG_FILE): return "wait"
    with open(LOG_FILE, "r") as f:
        content = f.read()
        if "Connected" in content or "Registered" in content: return "success"
        if "error" in content.lower() or "failed" in content.lower(): return "fail"
    return "wait"

@app.route('/', methods=['GET', 'POST'])
def index():
    global tunnel_process
    message, msg_class, icon = "", "status-info", "fa-solid fa-info-circle"
    raw_input = request.form.get('raw_input', '')

    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'start' and raw_input:
            token = extract_token(raw_input)
            
            if tunnel_process:
                tunnel_process.terminate()
            
            with open(LOG_FILE, "w") as f: f.write("")
            log_f = open(LOG_FILE, "a")
            
            tunnel_process = subprocess.Popen(
                ['cloudflared', 'tunnel', 'run', '--token', token],
                stdout=log_f, stderr=log_f, text=True
            )
            
            # 等待检测
            time.sleep(3)
            res = check_tunnel_status()
            if res == "success":
                message, msg_class, icon = "cloudflared隧道连接成功", "status-success", "fa-solid fa-check-circle"
            else:
                message, msg_class, icon = "cloudflared隧道连接失败，请重试", "status-fail", "fa-solid fa-circle-exmark"

        elif action == 'stop':
            if tunnel_process:
                tunnel_process.terminate()
                tunnel_process.wait()
                tunnel_process = None
                message, msg_class, icon = "cloudflared隧道已断开", "status-info", "fa-solid fa-link-slash"
            else:
                message = "隧道当前未运行"

    return render_template_string(HTML_TEMPLATE, raw_input=raw_input, message=message, msg_class=msg_class, icon=icon)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=12222)
