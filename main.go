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

	// 核心逻辑判断
	isModifying := r.URL.Query().Get("edit") == "true"
	currentToken := getStoredToken()
	hasToken := currentToken != ""
	
	message := r.URL.Query().Get("msg")
	msgType := r.URL.Query().Get("type")

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
					// 保存成功后，重定向到不带 edit=true 的页面，回到界面二
					http.Redirect(w, r, "/?msg=配置保存成功&type=success", http.StatusSeeOther)
					return
				}
				message, msgType = "配置保存失败", "error"
			} else {
				message, msgType = "未检测到有效Token", "error"
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
			http.Redirect(w, r, "/", http.StatusSeeOther)
			return
		case "stop":
			mu.Lock()
			if tunnelCmd != nil && tunnelCmd.Process != nil {
				_ = tunnelCmd.Process.Kill()
				_ = tunnelCmd.Wait()
				tunnelCmd = nil
			}
			mu.Unlock()
			isRunning = false
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
        :root { --accent: #f38020; --primary-grad: linear-gradient(135deg, #f38020 0%, #faad14 100%); }
        body { 
            margin: 0; min-height: 100vh; display: flex; justify-content: center; align-items: center;
            background: radial-gradient(circle at 15% 15%, #e0e7ff, transparent 45%), radial-gradient(circle at 85% 85%, #ffedd5, transparent 45%), #f8fafc;
            font-family: -apple-system, "PingFang SC", sans-serif;
        }
        .card { 
            width: 90%; max-width: 420px; padding: 45px 30px; background: rgba(255,255,255,0.85);
            backdrop-filter: blur(25px); border-radius: 35px; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.1); border: 1px solid #fff; text-align: center;
        }
        .status-pill { display: inline-flex; align-items: center; gap: 8px; padding: 8px 22px; border-radius: 50px; font-size: 13px; font-weight: 800; margin-bottom: 30px; }
        .on { background: #dcfce7; color: #15803d; border: 1px solid #bbf7d0; }
        .off { background: #f1f5f9; color: #64748b; border: 1px solid #e2e8f0; }
        .dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
        .on .dot { animation: blink 1s infinite; }
        @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }

        .token-view { background: rgba(248,250,252,0.9); border: 1px solid #e2e8f0; border-radius: 20px; padding: 20px; font-family: monospace; font-size: 13px; word-break: break-all; color: #475569; text-align: left; margin-bottom: 25px; line-height: 1.6; }
        textarea { width: 100%; border: 2px solid #e2e8f0; border-radius: 20px; padding: 20px; box-sizing: border-box; font-size: 14px; background: #fff; resize: none; margin-bottom: 25px; transition: 0.3s; }
        textarea:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 4px rgba(243,128,32,0.1); }

        .btn-group { display: flex; gap: 15px; }
        button, .btn-link { 
            flex: 1; height: 55px; border: none; border-radius: 18px; font-weight: 800; cursor: pointer; 
            display: flex; align-items: center; justify-content: center; gap: 10px; transition: all 0.2s; font-size: 15px; text-decoration: none; box-sizing: border-box;
        }
        /* 启动/保存：主色调 */
        .btn-main { background: var(--primary-grad); color: white; box-shadow: 0 8px 15px rgba(243,128,32,0.2); }
        /* 修改：次色调，大小与启动相同 */
        .btn-edit { background: #eff6ff; color: #2563eb; border: 1.5px solid #dbeafe; }
        .btn-stop { width: 100%; background: #fee2e2; color: #ef4444; border: 1.5px solid #fecaca; }
        
        button:hover, .btn-link:hover { transform: translateY(-2px); filter: brightness(1.05); }
        button:active { transform: scale(0.96); }

        .msg { margin-top: 20px; font-size: 14px; font-weight: 700; padding: 12px; border-radius: 15px; animation: slideUp 0.3s; }
        .msg-success { color: #15803d; background: #f0fdf4; border: 1px solid #bbf7d0; }
        .msg-error { color: #b91c1c; background: #fef2f2; border: 1px solid #fecaca; }
        @keyframes slideUp { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
    </style>
</head>
<body>
    <div class="card">
        <div style="font-size: 55px; color: var(--accent);"><i class="fa-brands fa-cloudflare"></i></div>
        <h2 style="margin: 10px 0 25px; font-weight: 900;">隧道管理中心</h2>

        <div class="status-pill {{if .IsRunning}}on{{else}}off{{end}}">
            <div class="dot"></div> {{if .IsRunning}}TUNNEL ACTIVE{{else}}TUNNEL OFFLINE{{end}}
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
                    <a href="/?edit=true" class="btn-link btn-edit"><i class="fa-solid fa-pen-to-square"></i> 修改配置</a>
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
		"IsModifying": isModifying,
		"Message":     message,
		"MsgType":     msgType,
	})
}

func main() {
	_ = os.MkdirAll(dataDir, 0755)
	http.HandleFunc("/", indexHandler)
	fmt.Println("Tunnel Manager running on :12222")
	http.ListenAndServe(":12222", nil)
}
