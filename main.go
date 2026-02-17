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
	[span_3](start_span)envToken  = os.Getenv("token") // 兼容 app.py 的逻辑[span_3](end_span)
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

	const html = `
	<!DOCTYPE html>
	<html>
	<head>
		<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
		<title>CF Manager Light</title>
		<style>
			body { font-family: system-ui; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background: #f4f7f6; }
			.card { background: white; padding: 2rem; border-radius: 1rem; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); width: 300px; text-align: center; }
			.status { padding: 5px 10px; border-radius: 20px; font-size: 0.8rem; font-weight: bold; }
			.on { background: #dcfce7; color: #15803d; }
			.off { background: #fee2e2; color: #991b1b; }
			input { width: 100%; padding: 10px; margin: 15px 0; border: 1px solid #ddd; border-radius: 8px; box-sizing: border-box; }
			button { width: 100%; padding: 10px; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; color: white; }
		</style>
	</head>
	<body>
		<div class="card">
			<h3>Cloudflared Go</h3>
			<p>状态: <span class="status {{if .IsRunning}}on{{else}}off{{end}}">{{if .IsRunning}}运行中{{else}}待命{{end}}</span></p>
			<form method="post">
				<input type="text" name="token" placeholder="输入 Token (若有环境变量可为空)" {{if .IsRunning}}disabled{{end}}>
				{{if .IsRunning}}
					<button type="submit" name="action" value="stop" style="background:#ef4444;">断开连接</button>
				{{else}}
					<button type="submit" name="action" value="start" style="background:#f38020;">启动隧道</button>
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
		[span_4](start_span)envToken = os.Getenv("TOKEN") // 再次尝试大写版本[span_4](end_span)
	}
	http.HandleFunc("/", indexHandler)
	fmt.Println("Lightweight Manager running on :12222")
	http.ListenAndServe(":12222", nil)
}
