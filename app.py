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

# --- 新增：环境变量判断 ---
# 兼容你要求的 'token' (全小写)
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
            /* 清新色调：浅蓝绿渐变 */
            background: linear-gradient(120deg, #e0f2fe 0%, #f0fdf4 100%);
            margin: 0; display: flex; justify-content: center; align-items: center; min-height: 100vh;
        }
        .container { 
            background: rgba(255, 255, 255, 0.8); 
            backdrop-filter: blur(15px);
            border-radius: 28px; padding: 40px; width: 90%; max-width: 420px; 
            box-shadow: 0 20px 40px rgba(0,0,0,0.05); text-align: center;
            border: 1px solid #fff;
        }
        .cf-logo { font-size: 55px; color: var(--cf-orange); margin-bottom: 15px; }
        h2 { margin: 0; color: #334155; font-size: 24px; }
        .sub-desc { color: #64748b; font-size: 13px; margin: 10px 0 25px; }
        textarea { 
            width: 100%; padding: 15px; border-radius: 18px; border: 2px solid #e2e8f0; 
            outline: none; box-sizing: border-box; font-family: monospace; 
            background: #fff; resize: none; color: #334155;
        }
        textarea:disabled { background: #f8fafc; color: #94a3b8; }
        .btn-group { display: flex; gap: 12px; margin-top: 20px; }
        button { flex: 1; padding: 13px; border-radius: 14px; border: none; cursor: pointer; font-weight: 700; transition: 0.3s; }
        .btn-save { background: #fff; color: #475569; border: 1px solid #e2e8f0; }
        .btn-run { background: var(--cf-orange); color: white; }
        .btn-stop { background: #fee2e2; color: var(--danger); }
        .status-msg { margin-top: 20px; padding: 15px; border-radius: 15px; font-size: 14px; display: flex; align-items: center; justify-content: center; gap: 8px; }
        .s-success { background: #dcfce7; color: #15803d; }
        .s-fail { background: #fef2f2; color: #991b1b; }
    </style>
</head>
<body>
    <div class="container">
        <div class="cf-logo"><i class="fa-brands fa-cloudflare"></i></div>
        <h2>隧道管理面板</h2>
        <p class="sub-desc">
            {% if env_active %} <i class="fa-solid fa-bolt"></i> 环境变量模式已激活 {% else %} 模式：本地配置保存 {% endif %}
        </p>
        <form method="post">
            <textarea name="raw_input" rows="4" placeholder="粘贴 Token..." {{ 'disabled' if is_running }}>{{ current_token }}</textarea>
            <div class="btn-group">
                {% if not is_running %}
                    {% if not env_active %}
                    <button type="submit" name="action" value="save" class="btn-save">保存</button>
                    {% endif %}
                    <button type="submit" name="action" value="start" class="btn-run" style="{{ 'grid-column: span 2;' if env_active }}">启动</button>
                {% else %}
                    <button type="submit" name="action" value="stop" class="btn-stop" style="width:100%">停止</button>
                {% endif %}
            </div>
        </form>
        {% if message %}<div class="status-msg {{ 's-success' if '成功' in message else 's-fail' }}">{{ message }}</div>{% endif %}
    </div>
</body>
</html>
"""

def extract_token(text):
    cleaned = re.sub(r'[\\\n\r\t\s]', '', text)
    match = re.search(r'[eE]yJh[a-zA-Z0-9\-_]{50,}', cleaned)
    return match.group(0) if match else cleaned

def load_token():
    # 逻辑：有环境变量用变量，没变量查文件
    if ENV_TOKEN_VAL:
        return extract_token(ENV_TOKEN_VAL)
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, "r") as f: return f.read().strip()
    return ""

@app.route('/', methods=['GET', 'POST'])
def index():
    global tunnel_process
    message = ""
    current_token = load_token()
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
        
        elif action == 'start':
            # 运行逻辑：如果有输入用输入，没有用加载的（变量或文件）
            run_token = extract_token(raw_input) if raw_input else current_token
            if run_token:
                with open(LOG_FILE, "w") as f: f.write("")
                tunnel_process = subprocess.Popen(['cloudflared', 'tunnel', '--no-autoupdate', 'run', '--token', run_token], stdout=open(LOG_FILE, "a"), stderr=subprocess.STDOUT)
                time.sleep(4)
                with open(LOG_FILE, "r") as f:
                    if "Connected" in f.read(): message, is_running = "隧道启动成功", True
                    else: message = "启动失败，请检查Token"
            else: message = "缺少Token内容"

        elif action == 'stop' and tunnel_process:
            tunnel_process.terminate()
            tunnel_process = None
            is_running = False
            message = "隧道已停止"

    return render_template_string(HTML_TEMPLATE, current_token=current_token, message=message, is_running=is_running, env_active=(ENV_TOKEN_VAL is not None))

if __name__ == '__main__':
    t = load_token()
    if t:
        tunnel_process = subprocess.Popen(['cloudflared', 'tunnel', '--no-autoupdate', 'run', '--token', t], stdout=open(LOG_FILE, "a"), stderr=subprocess.STDOUT)
    app.run(host='0.0.0.0', port=1450)
