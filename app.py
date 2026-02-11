from flask import Flask, request, render_template_string
import subprocess
import os
import time
import re

app = Flask(__name__)
tunnel_process = None
LOG_FILE = "tunnel.log"

# --- 更加精美且符合要求的界面 ---
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
            --success: #22c55e;
            --danger: #ef4444;
            --card-bg: rgba(255, 255, 255, 0.9);
        }
        body { 
            font-family: 'PingFang SC', sans-serif; 
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            margin: 0; display: flex; justify-content: center; align-items: center; min-height: 100vh;
        }
        .dashboard {
            background: var(--card-bg);
            backdrop-filter: blur(15px);
            border-radius: 28px;
            padding: 35px;
            width: 90%; max-width: 440px;
            box-shadow: 0 25px 50px -12px rgba(0,0,0,0.15);
            text-align: center;
        }
        .header { margin-bottom: 25px; }
        .icon-rocket { 
            font-size: 50px; color: var(--primary); 
            background: #fff; width: 90px; height: 90px; 
            line-height: 90px; border-radius: 25px; 
            margin: 0 auto 15px; box-shadow: 0 10px 20px rgba(99, 102, 241, 0.2);
        }
        h2 { color: #1e293b; margin: 0; font-weight: 700; letter-spacing: -0.5px; }
        .sub-text { color: #94a3b8; font-size: 13px; margin-top: 5px; }
        
        .input-area { margin: 25px 0; }
        textarea {
            width: 100%; padding: 15px; border-radius: 18px;
            border: 2px solid #f1f5f9; outline: none; transition: 0.3s;
            box-sizing: border-box; font-family: 'Courier New', monospace;
            background: #f8fafc; font-size: 13px; resize: none;
        }
        textarea:focus { border-color: var(--primary); background: #fff; }
        
        .actions { display: flex; gap: 12px; }
        button {
            flex: 1; padding: 14px; border-radius: 16px; border: none;
            cursor: pointer; font-weight: 600; font-size: 15px;
            display: flex; align-items: center; justify-content: center; gap: 8px;
            transition: 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .btn-run { background: var(--primary); color: white; }
        .btn-run:hover { transform: translateY(-3px); box-shadow: 0 8px 15px rgba(99, 102, 241, 0.3); }
        .btn-stop { background: #f1f5f9; color: #64748b; }
        .btn-stop:hover { background: #e2e8f0; color: #1e293b; }

        .status-msg {
            margin-top: 25px; padding: 16px; border-radius: 18px;
            font-size: 14px; font-weight: 600; display: flex; align-items: center; justify-content: center; gap: 10px;
            animation: fadeIn 0.5s ease;
        }
        .success { background: #dcfce7; color: #15803d; border: 1px solid #bbf7d0; }
        .error { background: #fee2e2; color: #b91c1c; border: 1px solid #fecaca; }
        .info { background: #f1f5f9; color: #475569; border: 1px solid #e2e8f0; }
        
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        
        .dot { width: 8px; height: 8px; background: currentColor; border-radius: 50%; animation: pulse 1.5s infinite; }
        @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.3; } 100% { opacity: 1; } }
    </style>
</head>
<body>
    <div class="dashboard">
        <div class="header">
            <div class="icon-rocket"><i class="fa-solid fa-rocket"></i></div>
            <h2>隧道控制台</h2>
            <p class="sub-text">支持粘贴原始 Docker 命令或纯 Token</p>
        </div>

        <form method="post">
            <div class="input-area">
                <textarea name="raw_input" rows="4" placeholder="粘贴 Token 或 Docker 命令...">{{ raw_input }}</textarea>
            </div>
            <div class="actions">
                <button type="submit" name="action" value="start" class="btn-run">
                    <i class="fa-solid fa-play"></i> 启动隧道
                </button>
                <button type="submit" name="action" value="stop" class="btn-stop">
                    <i class="fa-solid fa-stop"></i> 停止运行
                </button>
            </div>
        </form>

        {% if message %}
        <div class="status-msg {{ msg_class }}">
            {% if '成功' in message %}<div class="dot"></div>{% endif %}
            <i class="{{ icon }}"></i> {{ message }}
        </div>
        {% endif %}
    </div>
</body>
</html>
"""

def extract_token(text):
    """从复杂输入（包括换行、转义符）中提取 Token"""
    # 核心修复：移除反斜杠、换行符、制表符等干扰字符
    cleaned = text.replace('\\', '').replace('\n', '').replace('\r', '').replace('\t', '').strip()
    
    # 正则搜索：寻找以 eyJhI 开头的长字符串
    match = re.search(r'eyJh[a-zA-Z0-9\-_]{50,}', cleaned)
    if match:
        return match.group(0)
    return cleaned

def get_real_status():
    """实时解析日志判断是否连接成功"""
    if not os.path.exists(LOG_FILE): return "none"
    with open(LOG_FILE, "r") as f:
        log_content = f.read()
        # 只要日志出现 Connected 或 Registered 即视为成功
        if "Connected" in log_content or "Registered" in log_content:
            return "success"
        # 常见错误关键词
        if "error" in log_content.lower() or "failed" in log_content.lower() or "incorrect usage" in log_content.lower():
            return "fail"
    return "pending"

@app.route('/', methods=['GET', 'POST'])
def index():
    global tunnel_process
    message, msg_class, icon = "", "info", "fa-solid fa-circle-info"
    raw_input = request.form.get('raw_input', '')

    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'start' and raw_input:
            token = extract_token(raw_input)
            
            # 停止旧进程
            if tunnel_process:
                tunnel_process.terminate()
            
            # 清理旧日志并开启新进程
            with open(LOG_FILE, "w") as f: f.write("--- 正在启动 ---\n")
            log_f = open(LOG_FILE, "a")
            
            # 增加 --no-autoupdate 增强兼容性
            tunnel_process = subprocess.Popen(
                ['cloudflared', 'tunnel', '--no-autoupdate', 'run', '--token', token],
                stdout=log_f, stderr=log_f, text=True
            )
            
            # 给 4 秒检测宽限时间
            time.sleep(4)
            status = get_real_status()
            
            if status == "success":
                message, msg_class, icon = "cloudflared隧道连接成功", "success", "fa-solid fa-circle-check"
            else:
                message, msg_class, icon = "cloudflared隧道连接失败，请重试", "error", "fa-solid fa-circle-xmark"

        elif action == 'stop':
            if tunnel_process:
                tunnel_process.terminate()
                tunnel_process.wait()
                tunnel_process = None
                message, msg_class, icon = "cloudflared隧道已断开", "info", "fa-solid fa-link-slash"
            else:
                message = "隧道当前未运行"

    return render_template_string(HTML_TEMPLATE, raw_input=raw_input, message=message, msg_class=msg_class, icon=icon)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=12222)
