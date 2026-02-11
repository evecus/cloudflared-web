from flask import Flask, request, render_template_string
import subprocess
import os

app = Flask(__name__)
tunnel_process = None
LOG_FILE = "tunnel.log"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Cloudflared Manager</title>
    <style>
        body { font-family: sans-serif; max-width: 700px; margin: 30px auto; padding: 0 20px; }
        input { padding: 10px; width: 70%; }
        button { padding: 10px 20px; cursor: pointer; }
        pre { background: #eee; padding: 15px; height: 300px; overflow-y: scroll; text-align: left; font-size: 12px; }
        .status { font-weight: bold; margin: 15px 0; }
    </style>
</head>
<body>
    <h2>Cloudflared 控制面板</h2>
    <form method="post">
        <input type="text" name="token" placeholder="输入 Token" value="{{ token }}">
        <button type="submit" name="action" value="start">运行</button>
        <button type="submit" name="action" value="stop">停止</button>
    </form>
    <div class="status">状态: {{ status }}</div>
    <h3>运行日志:</h3>
    <pre>{{ logs }}</pre>
    <script>
        // 自动滚动到底部
        const pre = document.querySelector('pre');
        pre.scrollTop = pre.scrollHeight;
    </script>
</body>
</html>
"""

@app.route('/', methods=['GET', 'POST'])
def index():
    global tunnel_process
    
    if request.method == 'POST':
        action = request.form.get('action')
        token = request.form.get('token')
        
        if action == 'start' and token:
            if tunnel_process: tunnel_process.terminate()
            # 清空旧日志
            with open(LOG_FILE, "w") as f: f.write("")
            # 记录输出到文件
            log_f = open(LOG_FILE, "a")
            tunnel_process = subprocess.Popen(
                ['cloudflared', 'tunnel', '--run', token],
                stdout=log_f, stderr=log_f
            )
        elif action == 'stop' and tunnel_process:
            tunnel_process.terminate()
            tunnel_process = None

    status = "🟢 运行中" if tunnel_process and tunnel_process.poll() is None else "🔴 已停止"
    logs = ""
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            logs = f.read()

    return render_template_string(HTML_TEMPLATE, status=status, token=request.form.get('token', ''), logs=logs)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=1450)
