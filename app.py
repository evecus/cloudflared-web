from flask import Flask, request, render_template_string
import subprocess
import os
import time
import re

app = Flask(__name__)
tunnel_process = None
LOG_FILE = "tunnel.log"
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
        :root { 
            --cf-orange: #f38020; 
            --cf-blue: #0051ad;
            --success: #22c55e; 
            --danger: #ef4444; 
        }
        body { 
            font-family: 'PingFang SC', 'Helvetica Neue', sans-serif; 
            background: linear-gradient(135deg, #eef2ff 0%, #e0e7ff 50%, #dbeafe 100%);
            margin: 0; display: flex; justify-content: center; align-items: center; min-height: 100vh;
        }
        .card { 
            background: rgba(255, 255, 255, 0.85); 
            backdrop-filter: blur(20px);
            border-radius: 32px; 
            padding: 40px; 
            width: 90%; max-width: 450px; 
            box-shadow: 0 25px 50px -12px rgba(0,0,0,0.1);
            text-align: center;
            border: 1px solid rgba(255, 255, 255, 0.4);
        }
        .icon-header { 
            font-size: 55px; 
            color: var(--cf-orange); 
            margin-bottom: 20px;
            filter: drop-shadow(0 5px 10px rgba(243, 128, 32, 0.3));
        }
        h2 { margin: 0; color: #1e293b; font-weight: 800; font-size: 24px; }
        .sub { color: #64748b; font-size: 14px; margin: 10px 0 25px; line-height: 1.5; }
        
        textarea { 
            width: 100%; padding: 18px; border-radius: 20px; 
            border: 2px solid #e2e8f0; outline: none; transition: 0.3s;
            box-sizing: border-box; font-family: 'Fira Code', monospace; 
            font-size: 13px; background: rgba(248, 250, 262, 0.8); resize: none;
            color: #334155;
        }
        textarea:focus { border-color: var(--cf-orange); background: #fff; box-shadow: 0 0 0 4px rgba(243, 128, 32, 0.1); }
        textarea:disabled { background: #f1f5f9; cursor: not-allowed; opacity: 0.7; }
        
        .btn-group { display: flex; gap: 12px; margin-top: 25px; flex-wrap: wrap; }
        button { 
            flex: 1; padding: 14px; border-radius: 16px; border: none; 
            cursor: pointer; font-weight: 700; font-size: 15px;
            display: flex; align-items: center; justify-content: center; gap: 8px; 
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        
        .save { background: #fff; color: #1e293b; border: 2px solid #e2e8f0; }
        .save:hover { background: #f8fafc; border-color: #cbd5e1; }
        
        .run { background: linear-gradient(135deg, var(--cf-orange), #faad14); color: white; }
        .run:hover { transform: translateY(-3px); box-shadow: 0 10px 20px rgba(243, 128, 32, 0.3); }
        
        .stop { background: #fee2e2; color: var(--danger); }
        .stop:hover { background: #fecaca; }

        .status-bar { 
            margin-top: 30px; padding: 18px; border-radius: 20px; 
            font-weight: 700; font-size: 14px; 
            display: flex; align-items: center; justify-content: center; gap: 10px; 
            animation: slideUp 0.5s ease;
        }
        .success { background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; }
        .fail { background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }
        .info { background: #f0f9ff; color: #0369a1; border: 1px solid #bae6fd; }
        
        @keyframes slideUp { from { opacity: 0; transform: translateY(15px); } to { opacity: 1; transform: translateY(0); } }
        
        .dot { width: 10px; height: 10px; background: currentColor; border-radius: 50%; position: relative; }
        .dot::after {
            content: ""; position: absolute; width: 100%; height: 100%;
            background: inherit; border-radius: 50%;
            animation: pulse 1.5s infinite;
        }
        @keyframes pulse { 0% { transform: scale(1); opacity: 0.8; } 100% { transform: scale(3); opacity: 0; } }
    </style>
</head>
<body>
    <div class="card">
        <div class="icon-header"><i class="fa-brands fa-cloudflare"></i></div>
        <h2>Cloudflared隧道管理面板</h2>
        <p class="sub">支持 Token 或 Docker 命令输入</p>
        
        <form method="post">
            <textarea name="raw_input" rows="4" placeholder="在此粘贴内容..." {{ 'disabled' if is_running }}>{{ current_token }}</textarea>
            
            <div class="btn-group">
                {% if not is_running %}
                    <button type="submit" name="action" value="save" class="save"><i class="fa-solid fa-cloud-arrow-up"></i> 保存</button>
                    <button type="submit" name="action" value="start" class="run"><i class="fa-solid fa-bolt"></i> 启动隧道</button>
                {% else %}
                    <button type="submit" name="action" value="stop" class="stop"><i class="fa-solid fa-power-off"></i> 断开隧道连接</button>
                {% endif %}
            </div>
        </form>

        {% if message %}
        <div class="status-bar {{ msg_class }}">
            {% if '成功' in message %}<div class="dot"></div>{% endif %}
            <i class="fa-solid {{ 'fa-circle-check' if '成功' in message else 'fa-circle-exclamation' }}"></i>
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
                message, msg_class = "Token已同步保存", "info"
            else:
                message, msg_class = "保存失败：输入内容为空", "fail"

        elif action == 'start' and not is_running:
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
                        current_token = token_to_run
                    else:
                        message, msg_class = "连接失败，请检查Token有效性", "fail"
            else:
                message, msg_class = "未检测到有效Token", "fail"

        elif action == 'stop':
            if tunnel_process:
                tunnel_process.terminate()
                tunnel_process.wait()
                tunnel_process = None
                is_running = False
                message = "隧道已安全断开"

    return render_template_string(
        HTML_TEMPLATE, 
        current_token=current_token, 
        message=message, 
        msg_class=msg_class, 
        is_running=is_running
    )

if __name__ == '__main__':
    saved = load_saved_token()
    if saved:
        log_f = open(LOG_FILE, "a")
        tunnel_process = subprocess.Popen(
            ['cloudflared', 'tunnel', '--no-autoupdate', 'run', '--token', saved],
            stdout=log_f, stderr=log_f, text=True
        )
    app.run(host='0.0.0.0', port=12222)
