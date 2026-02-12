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

# 环境变量检测
ENV_TOKEN_VAL = os.getenv('token') or os.getenv('TOKEN')

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cloudflared Pro Manager</title>
    <link rel="icon" href="https://www.cloudflare.com/favicon.ico" type="image/x-icon">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        :root { 
            --cf-orange: #F38020; 
            --glass: rgba(255, 255, 255, 0.85);
            --grad-start: #6366f1;
            --grad-end: #a855f7;
            --success: #10B981;
            --danger: #EF4444;
        }

        body { 
            font-family: 'PingFang SC', system-ui, -apple-system, sans-serif; 
            /* 绚丽的多色渐变背景 */
            background: linear-gradient(45deg, #e0e7ff, #f3e8ff, #dcfce7);
            background-size: 400% 400%;
            animation: gradientBG 15s ease infinite;
            margin: 0; display: flex; justify-content: center; align-items: center; min-height: 100vh;
        }

        @keyframes gradientBG {
            0% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
            100% { background-position: 0% 50%; }
        }

        .container { 
            background: var(--glass); 
            backdrop-filter: blur(20px);
            border-radius: 30px; padding: 45px; width: 90%; max-width: 440px; 
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.1);
            text-align: center;
            border: 1px solid rgba(255, 255, 255, 0.4);
            position: relative;
            overflow: hidden;
        }

        /* 顶部装饰条 */
        .container::before {
            content: ""; position: absolute; top: 0; left: 0; right: 0; height: 6px;
            background: linear-gradient(to right, var(--cf-orange), #ffedd5);
        }

        .cf-logo { 
            font-size: 60px; color: var(--cf-orange); margin-bottom: 15px;
            filter: drop-shadow(0 5px 15px rgba(243, 128, 32, 0.3));
        }

        h2 { margin: 0; color: #1e293b; font-size: 26px; font-weight: 800; letter-spacing: -0.5px; }
        
        .sub-desc { 
            display: inline-block; padding: 6px 16px; border-radius: 50px;
            background: rgba(255,255,255,0.5); color: #64748b; font-size: 13px; margin: 15px 0 30px;
            border: 1px solid rgba(0,0,0,0.05);
        }
        
        textarea { 
            width: 100%; padding: 18px; border-radius: 20px; border: 2px solid rgba(99, 102, 241, 0.1); 
            outline: none; box-sizing: border-box; font-family: 'Fira Code', monospace; 
            background: rgba(255,255,255,0.6); resize: none; color: #334155; font-size: 13px;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }

        textarea:focus { 
            border-color: var(--grad-start); background: #fff;
            box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.15);
        }

        textarea:disabled { background: rgba(0,0,0,0.03); color: #94a3b8; cursor: not-allowed; border-color: transparent; }
        
        .btn-group { display: flex; gap: 15px; margin-top: 25px; }
        
        button { 
            flex: 1; padding: 14px; border-radius: 16px; border: none; cursor: pointer; 
            font-weight: 700; font-size: 15px; transition: all 0.3s;
            display: flex; align-items: center; justify-content: center; gap: 8px;
        }
        
        .btn-save { 
            background: #fff; color: #4f46e5; border: 2px solid #e0e7ff;
        }
        .btn-save:hover { background: #f5f3ff; border-color: #c7d2fe; transform: translateY(-2px); }

        .btn-run { 
            background: linear-gradient(135deg, var(--cf-orange), #fb923c); 
            color: white; box-shadow: 0 10px 20px -5px rgba(243, 128, 32, 0.4);
        }
        .btn-run:hover { transform: translateY(-3px) scale(1.02); box-shadow: 0 15px 25px -5px rgba(243, 128, 32, 0.5); }

        .btn-stop { 
            background: linear-gradient(135deg, #f43f5e, #e11d48); 
            color: white; box-shadow: 0 10px 20px -5px rgba(244, 63, 94, 0.3);
        }
        .btn-stop:hover { transform: translateY(-2px); filter: brightness(1.1); }
        
        .status-msg { 
            margin-top: 30px; padding: 18px; border-radius: 18px; font-size: 14px; 
            display: flex; align-items: center; justify-content: center; gap: 10px; font-weight: 700;
            animation: slideUp 0.4s ease-out;
        }

        @keyframes slideUp { from { opacity:0; transform: translateY(10px); } to { opacity:1; transform: translateY(0); } }

        .s-success { background: #d1fae5; color: #065f46; border: 1px solid #a7f3d0; }
        .s-fail { background: #fee2e2; color: #991b1b; border: 1px solid #fecaca; }
        
        .dot { 
            width: 10px; height: 10px; background: currentColor; border-radius: 50%; 
            position: relative;
        }
        .dot::after {
            content: ""; position: absolute; width: 100%; height: 100%;
            background: inherit; border-radius: 50%; animation: pulse 1.5s infinite;
        }

        @keyframes pulse {
            0% { transform: scale(1); opacity: 0.8; }
            100% { transform: scale(3); opacity: 0; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="cf-logo"><i class="fa-brands fa-cloudflare"></i></div>
        <h2>隧道管理面板</h2>
        
        <div class="sub-desc">
            {% if env_active %}
                <i class="fa-solid fa-bolt" style="color: #eab308"></i> 环境变量模式
            {% else %}
                <i class="fa-solid fa-folder-open" style="color: #6366f1"></i> 本地持久化模式
            {% endif %}
        </div>
        
        <form method="post">
            <textarea name="raw_input" rows="4" placeholder="在此输入 Token 或 Docker 运行命令..." {{ 'disabled' if is_running }}>{{ current_token }}</textarea>
            
            <div class="btn-group">
                {% if not is_running %}
                    {% if not env_active %}
                    <button type="submit" name="action" value="save" class="btn-save">
                        <i class="fa-solid fa-cloud-arrow-up"></i> 保存配置
                    </button>
                    {% endif %}
                    <button type="submit" name="action" value="start" class="btn-run" style="{{ 'width:100%; flex:none;' if env_active }}">
                        <i class="fa-solid fa-rocket"></i> 启动隧道
                    </button>
                {% else %}
                    <button type="submit" name="action" value="stop" class="btn-stop" style="width:100%; flex:none;">
                        <i class="fa-solid fa-power-off"></i> 断开隧道连接
                    </button>
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

# 后端逻辑保持你发送的代码逻辑不变，仅更新 check_status 匹配项
def extract_token(text):
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
                message = "未检测到有效Token"

        elif action == 'start' and not is_running:
            token_to_run = extract_token(raw_input) if raw_input else current_token
            if token_to_run:
                with open(LOG_FILE, "w") as f: f.write("") 
                tunnel_process = subprocess.Popen(
                    ['cloudflared', 'tunnel', '--no-autoupdate', 'run', '--token', token_to_run],
                    stdout=open(LOG_FILE, "a"), stderr=subprocess.STDOUT, text=True
                )
                time.sleep(5) 
                if check_status():
                    message, is_running = "隧道已连接成功", True
                else:
                    message = "连接失败，请检查Token"
            else:
                message = "缺少Token内容"

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
    t = get_current_token()
    if t:
        tunnel_process = subprocess.Popen(
            ['cloudflared', 'tunnel', '--no-autoupdate', 'run', '--token', t],
            stdout=open(LOG_FILE, "a"), stderr=subprocess.STDOUT, text=True
        )
    app.run(host='0.0.0.0', port=12222)
