package main

import (
	"fmt"
	"html/template"
	"net/http"
	"os"
	"os/exec"
	"regexp"
	"strings"
	"sync"
)

var (
	cmd       *exec.Cmd
	mu        sync.Mutex
	logPath   = "/app/data/tunnel.log"
	envToken  = os.Getenv("token") // 兼容 app.py 的逻辑 
)

func extractToken(input string) string {
	if input == "" { return "" }
	re := regexp.MustCompile(`[eE]yJh[a-zA-Z0-9\-_]{50,}`)
	match := re.FindString(input)
	if match != "" { return match }
	return strings.TrimSpace(input)
}

func indexHandler(w http.ResponseWriter, r *http.Request) {
	mu.Lock()
	isRunning := cmd != nil && cmd.Process != nil && cmd.ProcessState == nil
	mu.Unlock()

	displayToken := envToken
	if displayToken == "" {
		displayToken = "尚未设置 Token"
	}

	if r.Method == "POST" {
		action := r.FormValue("action")
		input := r.FormValue("token")
		
		if action == "start" && !isRunning {
			tokenToRun := extractToken(input)
			if tokenToRun == "" { tokenToRun = extractToken(envToken) }
			
			if tokenToRun != "" {
				c := exec.Command("cloudflared", "tunnel", "--no-autoupdate", "run", "--token", tokenToRun)
				f, _ := os.OpenFile(logPath, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0644)
				c.Stdout = f
				c.Stderr = f
				if err := c.Start(); err == nil {
					mu.Lock()
					cmd = c
					mu.Unlock()
					isRunning = true
				}
			}
		} else if action == "stop" && isRunning {
			cmd.Process.Kill()
			isRunning = false
		}
		// 简单的重定向防止刷新重复提交
		http.Redirect(w, r, "/", http.StatusSeeOther)
		return
	}

const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cloudflared Manager</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root {
            --primary: linear-gradient(135deg, #f38020 0%, #faad14 100%);
            --danger: linear-gradient(135deg, #ef4444 0%, #f87171 100%);
            --bg: #f8fafc;
        }
        body { 
            font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
            background: radial-gradient(circle at top right, #e0e7ff, transparent), 
                        radial-gradient(circle at bottom left, #ffedd5, transparent);
            background-color: var(--bg);
            margin: 0; display: flex; justify-content: center; align-items: center; min-height: 100vh;
        }
        .card { 
            background: rgba(255, 255, 255, 0.8);
            backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.3);
            padding: 2.5rem; border-radius: 2rem; 
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.08);
            width: 360px; text-align: center;
        }
        .logo { font-size: 3rem; color: #f38020; margin-bottom: 1rem; }
        h2 { margin: 0; font-size: 1.5rem; color: #1e293b; font-weight: 800; }
        .status-box {
            display: inline-flex; align-items: center; gap: 8px;
            padding: 6px 16px; border-radius: 50px; font-size: 0.85rem;
            margin: 1.5rem 0; font-weight: 600;
        }
        .on { background: #dcfce7; color: #15803d; }
        .off { background: #f1f5f9; color: #64748b; }
        .dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
        .pulse { animation: pulse-animation 2s infinite; }
        @keyframes pulse-animation { 0% { opacity: 1; } 50% { opacity: 0.4; } 100% { opacity: 1; } }
        
        input { 
            width: 100%; padding: 14px; border: 2px solid #e2e8f0; border-radius: 12px;
            box-sizing: border-box; margin-bottom: 1rem; transition: 0.3s;
            background: rgba(255,255,255,0.5); font-family: ui-monospace, monospace;
        }
        input:focus { outline: none; border-color: #f38020; background: #fff; }

        button { 
            width: 100%; padding: 14px; border: none; border-radius: 12px;
            cursor: pointer; color: white; font-weight: 700; font-size: 1rem;
            transition: transform 0.2s, box-shadow 0.2s;
            display: flex; align-items: center; justify-content: center; gap: 10px;
        }
        button:active { transform: scale(0.98); }
        .btn-start { background: var(--primary); box-shadow: 0 10px 15px -3px rgba(243, 128, 32, 0.3); }
        .btn-stop { background: var(--danger); box-shadow: 0 10px 15px -3px rgba(239, 68, 68, 0.3); }
    </style>
</head>
<body>
    <div class="card">
        <div class="logo"><i class="fa-brands fa-cloudflare"></i></div>
        <h2>隧道管理控制台</h2>
        
        <div class="status-box {{if .IsRunning}}on{{else}}off{{end}}">
            <div class="dot {{if .IsRunning}}pulse{{end}}"></div>
            {{if .IsRunning}}已连接至边缘网络{{else}}隧道处于离线状态{{end}}
        </div>

        <form method="post">
            <input type="text" name="token" placeholder="粘贴 Tunnel Token..." {{if .IsRunning}}disabled{{end}}>
            {{if .IsRunning}}
            <button type="submit" name="action" value="stop" class="btn-stop">
                <i class="fa-solid fa-power-off"></i> 断开连接
            </button>
            {{else}}
            <button type="submit" name="action" value="start" class="btn-start">
                <i class="fa-solid fa-bolt"></i> 立即启动
            </button>
            {{end}}
        </form>
    </div>
</body>
</html>`
	
	t, _ := template.New("web").Parse(html)
	t.Execute(w, map[string]interface{}{"IsRunning": isRunning})
}

func main() {
	os.MkdirAll("/app/data", 0755)
	if envToken == "" {
		envToken = os.Getenv("TOKEN") // 再次尝试大写版本 
	}
	http.HandleFunc("/", indexHandler)
	fmt.Println("Lightweight Manager running on :12222")
	http.ListenAndServe(":12222", nil)
}
