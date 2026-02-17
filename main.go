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
	cmd     *exec.Cmd
	mu      sync.Mutex
	logPath = "/app/data/tunnel.log"
)

[span_1](start_span)// 提取 Token 逻辑[span_1](end_span)
func extractToken(input string) string {
	re := regexp.MustCompile(`[eE]yJh[a-zA-Z0-9\-_]{50,}`)
	match := re.FindString(input)
	if match != "" {
		return match
	}
	return strings.TrimSpace(input)
}

func indexHandler(w http.ResponseWriter, r *http.Request) {
	mu.Lock()
	isRunning := cmd != nil && cmd.ProcessState == nil
	mu.Unlock()

	if r.Method == "POST" {
		action := r.FormValue("action")
		token := extractToken(r.FormValue("token"))

		if action == "start" && !isRunning && token != "" {
			[span_2](start_span)// 启动 cloudflared[span_2](end_span)
			c := exec.Command("cloudflared", "tunnel", "--no-autoupdate", "run", "--token", token)
			f, _ := os.OpenFile(logPath, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0644)
			c.Stdout = f
			c.Stderr = f
			c.Start()
			mu.Lock()
			cmd = c
			mu.Unlock()
			isRunning = true
		} else if action == "stop" && isRunning {
			cmd.Process.Kill()
			isRunning = false
		}
	}

	tmpl := `
	<!DOCTYPE html>
	<html>
	<head><title>CF Manager Light</title></head>
	<body style="font-family:sans-serif; text-align:center; padding-top:50px;">
		<h2>Cloudflared Go Light</h2>
		<p>状态: <b>{{if .IsRunning}} 运行中 ✅ {{else}} 已停止 ❌ {{end}}</b></p>
		<form method="post">
			<input type="text" name="token" placeholder="输入 Token" {{if .IsRunning}}disabled{{end}}><br><br>
			{{if .IsRunning}}
				<button type="submit" name="action" value="stop" style="background:#ff4444; color:white;">停止隧道</button>
			{{else}}
				<button type="submit" name="action" value="start" style="background:#007bff; color:white;">启动隧道</button>
			{{end}}
		</form>
	</body>
	</html>`
	t, _ := template.New("web").Parse(tmpl)
	t.Execute(w, map[string]interface{}{"IsRunning": isRunning})
}

func main() {
	os.MkdirAll("/app/data", 0755)
	http.HandleFunc("/", indexHandler)
	fmt.Println("Server started at :12222")
	http.ListenAndServe(":12222", nil)
}
