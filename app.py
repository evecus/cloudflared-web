from flask import Flask, request, render_template_string
import subprocess
import os
import time
import re

app = Flask(__name__)
tunnel_process = None

# 路径配置
DATA_DIR = "/app/data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

TOKEN_PATH = os.path.join(DATA_DIR, "token")
LOG_FILE = os.path.join(DATA_DIR, "tunnel.log")

# 环境变量检测 (支持 'token' 或 'TOKEN')
ENV_TOKEN_VAL = os.getenv('token') or os.getenv('TOKEN')

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cloudflared Manager</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        :root { --cf-orange: #F38020; --success: #10B981; --danger: #EF4444; }
        body { 
            font-family: 'PingFang SC', system-ui, sans-serif; 
            /* 清新渐变背景 */
            background: linear-gradient(135deg, #e0f2fe 0%, #f0fdf4 100%);
            margin: 0; display: flex; justify-content: center; align-items: center; min-height: 100vh;
        }
        .container { 
            background: rgba(255, 255, 255, 0.9); 
            backdrop-filter: blur(10px);
            border-radius: 24px; padding: 40px; width: 90%; max-width: 420px; 
            box-shadow: 0 15px 35px rgba(0,0,0,0.05); text-align: center;
        }
        .cf-logo { font-size: 50px; color: var(--cf-orange); margin-bottom: 15px; }
        h2 { margin: 0; color: #334155; font-size: 22px; }
        .sub-desc { color: #64748b; font-size: 13px; margin: 8px 0 25px; }
        
        textarea { 
            width: 100%; padding: 15px; border-radius: 15px; border: 2px solid #e2e8f0; 
            outline: none; box-sizing: border-box; font-family: monospace; 
            background: #fff; resize: none; color: #334155; font-size: 12px;
        }
        textarea:disabled { background: #f1f5f9; color: #94a3b8; cursor: not-allowed; }
        
        .btn-group { display: flex; gap: 12px; margin-top: 20px; }
        button { flex: 1; padding: 12px; border-radius: 12px; border: none; cursor: pointer; font-weight: 700; transition: 0.3s; }
        
        .btn-save { background: #fff; color: #475569; border: 1px solid #e2e8f0; }
        .btn-run { background: var(--cf-orange); color: white; }
        .btn-stop { background: #fee2e2; color: var(--danger); }
        
        .status-msg { margin-top: 25px; padding: 15px; border-radius: 12px; font-size: 14px; display: flex; align-items: center; justify-content: center; gap: 8px; font-weight: 600; }
        .s-success { background: #dcfce7; color: #15803d; border: 1px solid #bbf7d0; }
        .s-fail { background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }
        .dot { width: 8px; height: 8px; background: currentColor; border-radius: 50%; animation: blink 1s infinite; }
        @keyframes blink { 0% { opacity: 1; } 50% { opacity: 0.3; } 100% { opacity: 1; } }
    </style>
</head>
<body>
    <div class="container">
        <div class="cf-logo"><i class="fa-brands fa-cloudflare"></i></div>
        <h2>隧道管理面板</h2>
        <p class="sub-desc">
            {% if env_active %} <i class="fa-solid fa-shield-halved"></i> 环境变量模式已启用 {% else %} 数据持久化目录: /app/data {% endif %}
        </p>
        
        <form method="post">
            <textarea name="raw_input" rows="4" placeholder="粘贴 Token 或 Docker 命令..." {{ 'disabled' if is_running }}>{{ current_token }}</textarea>
            
            <div class="btn-group">
                {% if not is_running %}
                    {% if not env_active %}
                    <button type="submit" name="action" value="save" class="btn-save"><i class="fa-solid fa-save"></i> 保存</button>
                    {% endif %}
                    <button type="submit" name="action" value="start" class="btn-run" style="{{ 'width:100%; flex:none;' if env_active }}"><i class="fa-solid fa-play"></i> 启动隧道</button>
                {% else %}
                    <button type="submit" name="action" value="stop" class="btn-stop" style="width:100%; flex:none;"><i class="fa-solid fa-stop"></i> 停止并解锁</button>
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

def extract_token(text):
    cleaned = re.sub(r'[\\\n\r\t\s]', '', text)
    match = re.search(r'[eE]yJh[a-zA-Z0-9\-_]{50,}', cleaned)
    return match.group(0) if match else cleaned

def get_current_token():
    # 逻辑：优先读环境变量，其次读文件
    if ENV_TOKEN_VAL:
        return extract_token(ENV_TOKEN_VAL)
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, "r") as f:
            return f.read().strip()
    return ""

def check_status():
    """改进的检测逻辑"""
    if not os.path.exists(LOG_FILE): return False
    with open(LOG_FILE, "r") as f:
        content = f.read()
        # 匹配任何成功的标志
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
                message = "配置已保存至本地文件"
            else:
                message = "保存失败：无效内容"

        elif action == 'start' and not is_running:
            token_to_run = extract_token(raw_input) if raw_input else current_token
            if token_to_run:
                with open(LOG_FILE, "w") as f: f.write("") # 清空日志
                tunnel_process = subprocess.Popen(
                    ['cloudflared', 'tunnel', '--no-autoupdate', 'run', '--token', token_to_run],
                    stdout=open(LOG_FILE, "a"), stderr=subprocess.STDOUT, text=True
                )
                time.sleep(5) # 稍微多等一会儿让 4 个连接跑完
                if check_status():
                    message, is_running = "cloudflared隧道连接成功", True
                else:
                    message = "连接超时或失败，请查看后台日志"
            else:
                message = "错误：没有检测到Token"

        elif action == 'stop':
            if tunnel_process:
                tunnel_process.terminate()
                tunnel_process.wait()
                tunnel_process = None
                is_running = False
                message = "隧道已断开"

    return render_template_string(
        HTML_TEMPLATE, 
        current_token=current_token, 
        message=message, 
        is_running=is_running,
        env_active=(ENV_TOKEN_VAL is not None)
    )

if __name__ == '__main__':
    # 启动时自连
    t = get_current_token()
    if t:
        tunnel_process = subprocess.Popen(
            ['cloudflared', 'tunnel', '--no-autoupdate', 'run', '--token', t],
            stdout=open(LOG_FILE, "a"), stderr=subprocess.STDOUT, text=True
        )
    app.run(host='0.0.0.0', port=12222)
