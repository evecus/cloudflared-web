package main

import (
	"bufio"
	"html/template"
	"io/ioutil"
	"net/http"
	"os"
	"os/exec"
	"regexp"
	"strings"
	"sync"
	"time"
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

// 严谨的连接检测：匹配 Registered 或 Updated
func startTunnelWithCheck(token string) bool {
	cmd := exec.Command("cloudflared", "tunnel", "--no-autoupdate", "run", "--token", token)
	stderr, _ := cmd.StderrPipe()
	if err := cmd.Start(); err != nil {
		return false
	}

	success := make(chan bool)
	go func() {
		scanner := bufio.NewScanner(stderr)
		for scanner.Scan() {
			line := scanner.Text()
			// 严谨匹配你日志中的 Registered 和 Updated 关键字
			if strings.Contains(line, "Connected") || 
			   strings.Contains(line, "Registered") || 
			   strings.Contains(line, "Updated to new configuration") {
				success <- true
				return
			}
		}
	}()

	select {
	case <-success:
		mu.Lock()
		tunnelCmd = cmd
		mu.Unlock()
		return true
	case <-time.After(15 * time.Second):
		_ = cmd.Process.Kill()
		return false
	}
}

func indexHandler(w http.ResponseWriter, r *http.Request) {
	mu.Lock()
	isRunning := tunnelCmd != nil && tunnelCmd.Process != nil && tunnelCmd.ProcessState == nil
	mu.Unlock()

	isModifying := r.URL.Query().Get("edit") == "true"
	currentToken := getStoredToken()
	hasToken := currentToken != ""
	
	message := r.URL.Query().Get("msg")
	msgType := r.URL.Query().Get("type")

	if r.Method == "POST" {
		action := r.FormValue("action")
		rawInput := r.FormValue("raw_input")

		if action == "save" {
			token := extractToken(rawInput)
			if token != "" {
				_ = os.MkdirAll(dataDir, 0755)
				if err := ioutil.WriteFile(tokenPath, []byte(token), 0644); err == nil {
					http.Redirect(w, r, "/?msg=配置保存成功&type=success", http.StatusSeeOther)
					return
				}
			}
			http.Redirect(w, r, "/?msg=配置保存失败&type=error", http.StatusSeeOther)
			return
		} else if action == "start" && !isRunning {
			if startTunnelWithCheck(currentToken) {
				http.Redirect(w, r, "/", http.StatusSeeOther)
			} else {
				http.Redirect(w, r, "/?msg=连接失败，请检查配置或网络&type=error", http.StatusSeeOther)
			}
			return
		} else if action == "stop" {
			mu.Lock()
			if tunnelCmd != nil {
				_ = tunnelCmd.Process.Kill()
				_ = tunnelCmd.Wait()
				tunnelCmd = nil
			}
			mu.Unlock()
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
            background: #f8fafc; font-family: -apple-system, sans-serif;
        }
        .card { 
            width: 90%; max-width: 420px; padding: 40px; background: white;
            border-radius: 30px; box-shadow: 0 20px 50px rgba(0,0,0,0.05); text-align: center;
        }
        .status-pill { display: inline-flex; align-items: center; gap: 8px; padding: 8px 18px; border-radius: 50px; font-size: 12px; font-weight: 800; margin-bottom: 30px; }
        .on { background: #dcfce7; color: #15803d; }
        .off { background: #f1f5f9; color: #64748b; }
        .dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
        .on .dot { animation: blink 1s infinite; }
        @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }

        .token-view { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 18px; padding: 20px; font-family: monospace; font-size: 13px; word-break: break-all; color: #475569; text-align: left; margin-bottom: 25px; line-height: 1.5; }
        textarea { width: 100%; border: 2px solid #e2e8f0; border-radius: 18px; padding: 20px; box-sizing: border-box; font-size: 14px; background: #fff; resize: none; margin-bottom: 25px; transition: 0.3s; }
        textarea:focus { outline: none; border-color: var(--accent); }

        .btn-group { display: flex; gap: 12px; }
        button, .btn-link { 
            flex: 1; height: 55px; border: none; border-radius: 16px; font-weight: 800; cursor: pointer; 
            display: flex; align-items: center; justify-content: center; gap: 8px; transition: 0.2s; font-size: 15px; text-decoration: none; box-sizing: border-box;
        }
        .btn-main { background: var(--primary-grad); color: white; }
        .btn-edit { background: #f1f5f9; color: #475569; border: 1px solid #e2e8f0; }
        .btn-stop { width: 100%; background: #fee2e2; color: #ef4444; border: 1px solid #fecaca; }
        button:active { transform: scale(0.96); }

        .msg { margin-top: 20px; font-size: 14px; font-weight: 700; padding: 12px; border-radius: 12px; }
        .msg-success { color: #15803d; background: #f0fdf4; border: 1px solid #bbf7d0; }
        .msg-error { color: #b91c1c; background: #fef2f2; border: 1px solid #fecaca; }
    </style>
</head>
<body>
    <div class="card">
        <div style="font-size: 50px; color: var(--accent); margin-bottom: 20px;"><i class="fa-brands fa-cloudflare"></i></div>
        
        <div class="status-pill {{if .IsRunning}}on{{else}}off{{end}}">
            <div class="dot"></div> {{if .IsRunning}}隧道已连接边缘网络{{else}}等待建立安全隧道{{end}}
        </div>

        <form method="post">
            {{if .IsRunning}}
                <div class="token-view">{{.Token}}</div>
                <button type="submit" name="action" value="stop" class="btn-stop"><i class="fa-solid fa-power-off"></i> 断开连接</button>
            {{else if or (not .HasToken) .IsModifying}}
                <textarea name="raw_input" rows="4" placeholder="在此粘贴 Token...">{{if .IsModifying}}{{.Token}}{{end}}</textarea>
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
	http.ListenAndServe(":12222", nil)
}
