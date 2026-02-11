from flask import Flask, request, render_template_string
import subprocess
import signal
import os

app = Flask(__name__)
process = None

# HTML 模板
HTML = """
<!DOCTYPE html>
<html>
<head><title>Cloudflared Controller</title></head>
<body>
    <h2>Cloudflared 控制面板</h2>
    <form method="post">
        <input type="text" name="token" placeholder="输入 Tunnel Token" style="width:300px;">
        <button type="submit" name="action" value="start">运行</button>
        <button type="submit" name="action" value="stop">停止</button>
    </form>
    <p>状态: <b>{{ status }}</b></p>
</body>
</html>
"""

@app.route('/', methods=['GET', 'POST'])
def index():
    global process
    status = "停止" if process is None or process.poll() is not None else "运行中"
    
    if request.method == 'POST':
        action = request.form.get('action')
        token = request.form.get('token')
        
        if action == 'start' and token:
            if process is None or process.poll() is not None:
                # 运行 cloudflared tunnel --run <TOKEN>
                process = subprocess.Popen(['cloudflared', 'tunnel', '--run', token])
                status = "运行中"
        elif action == 'stop':
            if process:
                process.terminate()
                process = None
                status = "停止"
                
    return render_template_string(HTML, status=status)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=1450)
