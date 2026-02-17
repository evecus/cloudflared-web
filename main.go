package main

import (
	"fmt"
	"html/template"
	"io/ioutil"
	"net/http"
	"os"
	"os/exec"
	"regexp"
	"strings"
	"sync"
)

var (
	tunnelCmd *exec.Cmd
	mu        sync.Mutex
	dataDir   = "/app/data"
	tokenPath = "/app/data/token"
)

func extractToken(input string) string {
	if input == "" { return "" }
	cleaned := regexp.MustCompile(`[\\\n\r\t\s]`).ReplaceAllString(input, "")
	re := regexp.MustCompile(`[eE]yJh[a-zA-Z0-9\-_]{50,}`)
	match := re.FindString(cleaned)
	if match != "" { return match }
	return strings.TrimSpace(input)
}

func getStoredToken() string {
	if t := os.Getenv("token"); t != "" { return extractToken(t) }
	if t := os.Getenv("TOKEN"); t != "" { return extractToken(t) }
	data, _ := ioutil.ReadFile(tokenPath)
	return strings.TrimSpace(string(data))
}

func indexHandler(w http.ResponseWriter, r *http.Request) {
	mu.Lock()
	isRunning := tunnelCmd != nil && tunnelCmd.Process != nil && tunnelCmd.ProcessState == nil
	mu.Unlock()

	// 强制模式切换逻辑
	isModifying := r.URL.Query().Get("edit") == "true"
	currentToken := getStoredToken()
	hasToken := currentToken != ""
	envToken := os.Getenv("token")
	if envToken == "" { envToken = os.Getenv("TOKEN") }
	hasEnv := envToken != ""

	message := ""
	msgType := ""

	if r.Method == "POST" {
		action := r.FormValue("action")
		rawInput := r.FormValue("raw_input")

		switch action {
		case "save":
			token := extractToken(rawInput)
			if token != "" {
				_ = os.MkdirAll(dataDir, 0755)
				err := ioutil.WriteFile(tokenPath, []byte(token), 0644)
				if err == nil {
					message, msgType, currentToken, hasToken = "配置保存成功", "success", token, true
				} else {
					message, msgType = "配置保存失败", "error"
				}
			} else {
				message, msgType = "保存失败：未检测到有效 Token", "error"
			}
		case "start":
			if hasToken && !isRunning {
				c := exec.Command("cloudflared", "tunnel", "--no-autoupdate", "run", "--token", currentToken)
				if err := c.Start(); err == nil {
					mu.Lock()
					tunnelCmd = c
					mu.Unlock()
					isRunning = true
				}
			}
		case "stop":
			mu.Lock()
			if tunnelCmd != nil && tunnelCmd.Process != nil {
				_ = tunnelCmd.Process.Kill()
				_ = tunnelCmd.Wait()
				tunnelCmd = nil
			}
			mu.Unlock()
			isRunning = false
		}
		// 如果是保存成功，不重定向以显示消息；否则重定向清空 POST
		if action != "save" {
			http.Redirect(w, r, "/", http.StatusSeeOther)
			return
		}
	}

	const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CF Tunnel Manager</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root { --accent: #f38020; --bg: #f4f7fb; --primary-grad: linear-gradient(135deg, #f38020 0%, #faad14 100%); }
        body { 
            margin: 0; min-height: 100vh; display: flex; justify-content: center; align-items: center;
            background: radial-gradient(circle at 15% 15%, #e0e7ff, transparent 45%), radial-gradient(circle at 85% 85%, #ffedd5, transparent 45%), #f8fafc;
            font-family: -apple-system, "PingFang SC", sans-serif;
        }
        .card { 
            width: 90%; max-width: 400px; padding: 45px 30px; background: rgba(255,255,255,0.85);
            backdrop-filter: blur(20px); border-radius: 35px; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.1); border: 1px solid #fff; text-align: center;
        }
        .status-pill { display: inline-flex; align-items: center; gap: 8px; padding: 8px 20px; border-radius: 50px; font-size: 12px; font-weight: 800; margin-bottom: 30px; }
        .on { background: #dcfce7; color: #15803d; border: 1px solid #bbf7d0; }
        .off { background: #f1f5f9; color: #64748b; border: 1px solid #e2e8f0; }
        .dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
        .on .dot { animation: blink 1s infinite; }
        @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }

        .token-view { background: rgba(248,250,252,0.8); border: 1px solid #e2e8f0; border-radius: 18px; padding: 18px; font-family: monospace; font-size: 12px; word-break: break-all; color: #475569; text-align: left; margin-bottom: 25px; line-height: 1.5; }
        textarea { width: 100%; border: 2px solid #e2e8f0; border-radius: 20px; padding: 18px; box-sizing: border-box; font-size: 13px; background: #fff; resize: none; margin-bottom: 25px; transition: 0.3s; }
        textarea:focus { outline: none; border-color: var(--accent); }

        .btn-group { display: flex; gap: 12px; }
        button, .btn-link { 
            flex: 1; border: none; border-radius: 18px; padding: 16px; font-weight: 800; cursor: pointer; 
            display: flex; align-items: center; justify-content: center; gap: 8px; transition: 0.2s; font-size: 14px; text-decoration: none;
        }
        .btn-main { background: var(--primary-grad); color: white; box-shadow: 0 10px 20px rgba(243,128,32,0.2); }
        .btn-sub { background: white; color: #64748b; border: 1px solid #e2e8f0; }
        .btn-stop { width: 100%; background: #fee2e2; color: #ef4444; border: 1px solid #fecaca; }
        button:active { transform: scale(0.96); }

        .msg { margin-top: 15px; font-size: 13px; font-weight: 700; padding: 10px; border-radius: 12px; }
        .msg-success { color: #15803d; background: #f0fdf4; }
        .msg-error { color: #b91c1c; background: #fef2f2; }
    </style>
</head>
<body>
    <div class="card">
        <div style="font-size: 50px; color: var(--accent);"><i class="fa-brands fa-cloudflare"></i></div>
        <h2 style="margin: 10px 0 25px;">隧道控制中心</h2>

        <div class="status-pill {{if .IsRunning}}on{{else}}off{{end}}">
            <div class="dot"></div> {{if .IsRunning}}已加密连接{{else}}隧道未运行{{end}}
        </div>

        <form method="post">
            {{if .IsRunning}}
                <div class="token-view">{{.Token}}</div>
                <button type="submit" name="action" value="stop" class="btn-stop"><i class="fa-solid fa-power-off"></i> 断开连接</button>
            {{else if or (not .HasToken) .IsModifying}}
                <textarea name="raw_input" rows="4" placeholder="粘贴 Token 或 Docker 命令...">{{if .IsModifying}}{{.Token}}{{end}}</textarea>
                <button type="submit" name="action" value="save" class="btn-main" style="width:100%"><i class="fa-solid fa-floppy-disk"></i> 保存配置</button>
            {{else}}
                <div class="token-view">{{.Token}}</div>
                <div class="btn-group">
                    <a href="/?edit=true" class="btn-sub"><i class="fa-solid fa-pen-to-square"></i> 修改配置</a>
                    <button type="submit" name="action" value="start" class="btn-main"><i class="fa-solid fa-bolt"></i> 启动连接</button>
                </div>
            {{end}}
        </form>

        {{if .Message}}<div class="msg msg-{{.MsgType}}">{{.Message}}</div>{{end}}
    </div>
</body>
</html>`

	t, _ := template.New("web").Parse(html)
	t.Execute(w, map[string]interface{}{
		"IsRunning":   isRunning,
		"Token":       currentToken,
		"HasToken":    hasToken,
		"HasEnv":      hasEnv,
		"IsModifying": isModifying,
		"Message":     message,
		"MsgType":     msgType,
	})
}

func main() {
	_ = os.MkdirAll(dataDir, 0755)
	http.HandleFunc("/", indexHandler)
	fmt.Println("Dynamic Manager running on :12222")
	http.ListenAndServe(":12222", nil)
}
