from flask import Flask, request, render_template_string
import subprocess
import os
import time
import re

app = Flask(__name__)
tunnel_process = None

# --- 核心路径修改：指向挂载的 data 目录 ---
DATA_DIR = "/app/data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

TOKEN_PATH = os.path.join(DATA_DIR, "token")
LOG_FILE = os.path.join(DATA_DIR, "tunnel.log")

# --- 极美 UI 设计 (深色科技渐变 + 品牌图标) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cloudflared Manager Pro</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        :root { 
            --cf-orange: #F38020; 
            --success: #10B981; 
            --danger: #EF4444; 
        }
        body { 
            font-family: 'PingFang SC', system-ui, sans-serif; 
            /* 绚丽的深色背景 */
            background: linear-gradient(135deg, #1e1b4b 0%, #312e81 50%, #1e1b4b 100%);
            margin: 0; display: flex; justify-content: center; align-items: center; min-height: 100vh;
            color: #fff;
        }
        .container { 
            background: rgba(255, 255, 255, 0.08); 
            backdrop-filter: blur(20px);
            border-radius: 30px; 
            padding: 40px; 
            width: 90%; max-width: 450px; 
            box-shadow: 0 25px 50px rgba(0,0,0,0.5);
            text-align: center;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        .cf-logo { 
            font-size: 60px; 
            color: var(--cf-orange); 
            margin-bottom: 20px;
            filter: drop-shadow(0 0 15px rgba(243, 128, 32, 0.4));
        }
        h2 { margin: 0; font-weight: 800; font-size: 26px; letter-spacing: -1px; }
        .sub-desc { color: rgba(255,255,255,0.6); font-size: 13px; margin: 10px 0 30px; }
        
        textarea { 
            width: 100%; padding: 18px; border-radius: 20px; 
            border: 1px solid rgba(255,255,255,0.2); outline: none; transition: 0.3s;
            box-sizing: border-box; font-family: 'Fira Code', monospace; 
            font-size: 13px; background: rgba(0, 0, 0, 0.3); resize: none;
            color: #fff; line-height: 1.5;
        }
        textarea:focus { border-color: var(--cf-orange); background: rgba(0,0,0,0.5); }
        textarea:disabled { opacity: 0.5; cursor: not-allowed; background: rgba(255,255,255,0.05); }
        
        .btn-group { display: flex; gap: 12px; margin-top: 25px; }
        button { 
            flex: 1; padding: 14px; border-radius: 16px; border: none; 
            cursor: pointer; font-weight: 700; font-size: 15px;
            display: flex; align-items: center; justify-content: center; gap: 8px; 
            transition: 0.3s;
        }
        .btn-save { background: rgba(255,255,255,0.1); color: #fff; border: 1px solid rgba(255,255,255,0.1); }
        .btn-save:hover { background: rgba(255,255,255,0.2); }
        .btn-run { background: var(--cf-orange); color: white; }
        .btn-run:hover { transform: translateY(-3px); box-shadow: 0 10px 20px rgba(243, 128, 32, 0.4); }
        .btn-stop { background: var(--danger); color: white; }

        .status-msg { 
            margin-top: 25px; padding: 16px; border-radius: 18px; 
            font-weight: 600; font-size: 14px; display: flex; align-items: center; justify-content: center; gap: 10px;
            background: rgba(0,0,0,0.2); border: 1px solid rgba(255,255,255,0.05);
        }
        .status-success { color: #4ade80; border-color: rgba(74, 222, 128, 0.2); }
        .status-fail { color: #f87171; border-color: rgba(248, 113, 113, 0.2); }
        
        .pulse { width: 10px; height: 10px; background: #4ade80; border-radius: 50%; position: relative; }
        .pulse::after {
            content: ""; position: absolute; width: 100%; height: 100%;
            background: inherit; border-radius: 50%; animation: wave 1.5s infinite;
        }
        @keyframes wave { 0% { transform: scale(1); opacity: 0.8; } 100% { transform: scale(3); opacity: 0; } }
    </style>
</head>
<body>
    <div class="container">
        <div class="cf-logo"><i class="fa-brands fa-cloudflare"></i></div>
        <h2>Cloudflared隧道管理面板</h2>
        <p class="sub-desc">Token持久化保存</p>
        
        <form method="post">
            <textarea name="raw_input" rows="4" placeholder="粘贴 Token 或 Docker 命令..." {{ 'disabled' if is_running }}>{{ current_token }}</textarea>
            
            <div class="btn-group">
                {% if not is_running %}
                    <button type="submit" name="action" value="save" class="btn-save"><i class="fa-solid fa-save"></i> 保存</button>
                    <button type="submit" name="action" value="start" class="btn-run"><i class="fa-solid fa-play"></i> 启动隧道</button>
                {% else %}
                    <button type="submit" name="action" value="stop" class="btn-stop"><i class="fa-solid fa-stop"></i> 停止连接</button>
                {% endif %}
            </div>
        </form>

        {% if message %}
        <div class="status-msg {{ 'status-success' if '成功' in message else 'status-fail' if '失败' in message else '' }}">
            {% if '成功' in message %}<div class="pulse"></div>{% endif %}
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
    message, msg_class = "", ""
    current_token = load_saved_token()
    is_running = tunnel_process is not None and tunnel_process.poll() is None

    if request.method == 'POST':
        action = request.form.get('action')
        raw_input = request.form.get('raw_input', '').strip()

        if action == 'save' and not is_running:
            token = extract_token(raw_input)
            if token:
                with open(TOKEN_PATH, "w") as f: f.write(token)
                current_token = token
                message = "Token已保存"
            else:
                message = "保存失败：未检测到有效Token"

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
                        message, is_running = "cloudflared隧道连接成功", True
                        current_token = token_to_run
                    else:
                        message = "cloudflared隧道连接失败，请重试"
            else:
                message = "启动失败：缺少有效Token"

        elif action == 'stop':
            if tunnel_process:
                tunnel_process.terminate()
                tunnel_process.wait()
                tunnel_process = None
                is_running = False
                message = "cloudflared隧道已断开"

    return render_template_string(HTML_TEMPLATE, current_token=current_token, message=message, is_running=is_running)

if __name__ == '__main__':
    saved = load_saved_token()
    if saved:
        log_f = open(LOG_FILE, "a")
        tunnel_process = subprocess.Popen(
            ['cloudflared', 'tunnel', '--no-autoupdate', 'run', '--token', saved],
            stdout=log_f, stderr=log_f, text=True
        )
    app.run(host='0.0.0.0', port=12222)
