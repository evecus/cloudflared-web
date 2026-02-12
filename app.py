from flask import Flask, request, render_template_string
import subprocess
import os
import time
import re

app = Flask(__name__)
tunnel_process = None

# --- 路径与环境配置 ---
DATA_DIR = "/app/data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

TOKEN_PATH = os.path.join(DATA_DIR, "token")
LOG_FILE = os.path.join(DATA_DIR, "tunnel.log")

# 环境变量检测 (支持 'token' 或 'TOKEN')
ENV_TOKEN_VAL = os.getenv('token') or os.getenv('TOKEN')

# --- 界面设计 ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cloudflared Pro Manager</title>
    <link rel="icon" href="https://www.cloudflare.com/favicon.ico" type="image/x-icon">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    
    <style>
        :root { 
            --cf-orange: #F38020; 
            --primary: #6366f1;
            --accent: #a855f7;
            --success: #10B981;
            --danger: #EF4444;
            --font-mono: 'JetBrains Mono', monospace;
        }

        body { 
            font-family: 'PingFang SC', system-ui, sans-serif; 
            background: linear-gradient(135deg, #f5f7ff 0%, #f0f4ff 100%);
            margin: 0; display: flex; justify-content: center; align-items: center; min-height: 100vh;
            color: #1e293b;
        }

        .container { 
            background: rgba(255, 255, 255, 0.95); 
            backdrop-filter: blur(20px);
            border-radius: 32px; padding: 40px; width: 92%; max-width: 440px; 
            box-shadow: 0 25px 50px -12px rgba(99, 102, 241, 0.15);
            text-align: center; border: 1px solid rgba(255, 255, 255, 0.8);
        }

        .cf-logo { font-size: 56px; color: var(--cf-orange); margin-bottom: 10px; filter: drop-shadow(0 4px 10px rgba(243, 128, 32, 0.2)); }
        h2 { margin: 0; font-size: 24px; font-weight: 800; color: #1e293b; }
        
        .mode-badge { 
            display: inline-flex; align-items: center; gap: 6px; padding: 6px 14px; border-radius: 50px;
            font-size: 12px; font-weight: 700; margin: 15px 0 25px;
        }
        .mode-env { background: #e0e7ff; color: #4338ca; }
        .mode-local { background: #f1f5f9; color: #475569; }

        /* 3. Token 输入与展示区域美化 */
        textarea { 
            width: 100%; padding: 18px; border-radius: 20px; border: 2px solid #e2e8f0; 
            outline: none; box-sizing: border-box; font-family: var(--font-mono); 
            background: #f8fafc; resize: none; color: #334155; font-size: 13px; transition: 0.3s;
        }
        textarea:focus { border-color: var(--primary); background: #fff; box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.1); }
        textarea:disabled { background: #f1f5f9; color: #94a3b8; cursor: not-allowed; }

        .env-display-card {
            background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
            border-radius: 20px; padding: 20px; color: white; text-align: left;
            margin-bottom: 25px; box-shadow: 0 10px 20px rgba(99, 102, 241, 0.2);
        }
        .env-label { font-size: 11px; opacity: 0.8; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; }
        .env-value { 
            font-family: var(--font-mono); font-size: 13px; margin-top: 10px; 
            word-break: break-all; background: rgba(0,0,0,0.15); padding: 12px; border-radius: 12px;
            line-height: 1.5; color: #e0e7ff;
        }

        .btn-group { display: flex; gap: 12px; margin-top: 10px; }
        button { 
            flex: 1; padding: 14px; border-radius: 16px; border: none; cursor: pointer; 
            font-weight: 700; font-size: 15px; transition: all 0.3s;
            display: flex; align-items: center; justify-content: center; gap: 8px;
        }
        
        .btn-save { background: #fff; color: var(--primary); border: 2px solid #eef2ff; }
        .btn-save:hover { background: #f5f7ff; transform: translateY(-2px); }

        .btn-run { background: var(--cf-orange); color: white; box-shadow: 0 8px 16px rgba(243, 128, 32, 0.25); }
        .btn-run:hover { transform: translateY(-2px); box-shadow: 0 12px 20px rgba(243, 128, 32, 0.35); }

        .btn-stop { background: #fee2e2; color: var(--danger); width: 100%; flex: none; }
        .btn-stop:hover { background: #fecaca; transform: translateY(-2px); }
        
        .status-msg { 
            margin-top: 25px; padding: 16px; border-radius: 16px; font-size: 13px; 
            display: flex; align-items: center; justify-content: center; gap: 8px; font-weight: 700;
        }
        .s-success { background: #dcfce7; color: #15803d; border: 1px solid #bbf7d0; }
        .s-fail { background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }
        .dot { width: 8px; height: 8px; background: currentColor; border-radius: 50%; animation: blink 1s infinite; }
        @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
    </style>
</head>
<body>
    <div class="container">
        <div class="cf-logo"><i class="fa-brands fa-cloudflare"></i></div>
        <h2>隧道管理面板</h2>
        
        <div class="mode-badge {{ 'mode-env' if env_active else 'mode-local' }}">
            {% if env_active %}
                <i class="fa-solid fa-bolt-lightning"></i> 环境变量模式已启用
            {% else %}
                <i class="fa-solid fa-database"></i> 本地保存模式已启用
            {% endif %}
        </div>
        
        <form method="post">
            {% if env_active %}
                <div class="env-display-card">
                    <div class="env-label">当前运行 Token</div>
                    <div class="env-value">{{ current_token }}</div>
                </div>
            {% else %}
                <div class="input-box" style="margin-bottom: 20px;">
                    <textarea name="raw_input" rows="5" placeholder="粘贴 Token 或 Docker 命令..." {{ 'disabled' if is_running }}>{{ current_token }}</textarea>
                </div>
            {% endif %}
            
            <div class="btn-group">
                {% if not is_running %}
                    {% if not env_active %}
                    <button type="submit" name="action" value="save" class="btn-save"><i class="fa-solid fa-floppy-disk"></i> 保存配置</button>
                    {% endif %}
                    <button type="submit" name="action" value="start" class="btn-run" style="{{ 'width:100%; flex:none;' if env_active }}"><i class="fa-solid fa-play"></i> 启动隧道</button>
                {% else %}
                    <button type="submit" name="action" value="stop" class="btn-stop"><i class="fa-solid fa-stop"></i> 断开连接</button>
                {% endif %}
            </div>
        </form>

        {% if message %}
        <div class="status-msg {{ 's-success' if '成功' in message else 's-fail' }}">
            {% if '成功' in message %}<div class="dot"></div>{% endif %}
            {{ message }}
        </div>
        {% endif %}
    </div>
</body>
</html>
"""

# --- 后端逻辑 ---
def extract_token(text):
    if not text: return ""
    cleaned = re.sub(r'[\\\n\r\t\s]', '', text)
    match = re.search(r'[eE]yJh[a-zA-Z0-9\-_]{50,}', cleaned)
    return match.group(0) if match else cleaned

def get_current_token():
    if ENV_TOKEN_VAL:
        return extract_token(ENV_TOKEN_VAL)
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, "r") as f:
            return f.read().strip()
    return ""

def check_status():
    if not os.path.exists(LOG_FILE): return False
    with open(LOG_FILE, "r") as f:
        content = f.read()
        # 兼容最新日志格式
        if any(x in content for x in ["Connected", "Registered", "Updated to new configuration"]):
            return True
    return False

@app.route('/', methods=['GET', 'POST'])
def index():
    global tunnel_process
    message = ""
    current_token = get_current_token()
    is_running = tunnel_process is not None and tunnel_process.poll() is None

    if request.method == 'POST':
        action = request.form.get('action')
        raw_input = request.form.get('raw_input', '').strip()

        if action == 'save' and not ENV_TOKEN_VAL:
            token = extract_token(raw_input)
            if token:
                with open(TOKEN_PATH, "w") as f: f.write(token)
                current_token = token
                message = "配置保存成功"
            else:
                message = "未发现有效 Token"

        elif action == 'start' and not is_running:
            token_to_run = extract_token(raw_input) if (raw_input and not ENV_TOKEN_VAL) else current_token
            if token_to_run:
                with open(LOG_FILE, "w") as f: f.write("") 
                tunnel_process = subprocess.Popen(
                    ['cloudflared', 'tunnel', '--no-autoupdate', 'run', '--token', token_to_run],
                    stdout=open(LOG_FILE, "a"), stderr=subprocess.STDOUT, text=True
                )
                time.sleep(5) 
                if check_status():
                    message, is_running = "cloudflared隧道连接成功", True
                else:
                    message = "连接超时，请检查Token或网络"
            else:
                message = "启动失败：缺少 Token"

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
        is_running=is_running,
        env_active=(ENV_TOKEN_VAL is not None)
    )

if __name__ == '__main__':
    # 启动时自动检查是否有 Token 并尝试运行
    t = get_current_token()
    if t:
        tunnel_process = subprocess.Popen(
            ['cloudflared', 'tunnel', '--no-autoupdate', 'run', '--token', t],
            stdout=open(LOG_FILE, "a"), stderr=subprocess.STDOUT, text=True
        )
    app.run(host='0.0.0.0', port=12222)
