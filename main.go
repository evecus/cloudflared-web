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
	logPath   = "/app/data/tunnel.log"
)

func extractToken(input string) string {
	if input == "" { return "" }
	cleaned := regexp.MustCompile(`[\\\n\r\t\s]`).ReplaceAllString(input, "")
	re := regexp.MustCompile(`eyJh[a-zA-Z0-9\-_]{50,}`)
	match := re.FindString(cleaned)
	if match != "" { return match }
	return strings.TrimSpace(input)
}

func getCurrentToken() string {
	if t := os.Getenv("token"); t != "" { return extractToken(t) }
	if t := os.Getenv("TOKEN"); t != "" { return extractToken(t) }
	data, _ := ioutil.ReadFile(tokenPath)
	return strings.TrimSpace(string(data))
}

func indexHandler(w http.ResponseWriter, r *http.Request) {
	mu.Lock()
	isRunning := tunnelCmd != nil && tunnelCmd.Process != nil && tunnelCmd.ProcessState == nil
	mu.Unlock()

	envToken := os.Getenv("token")
	if envToken == "" { envToken = os.Getenv("TOKEN") }
	hasEnv := envToken != ""
	currentToken := getCurrentToken()

	if r.Method == "POST" {
		action := r.FormValue("action")
		rawInput := r.FormValue("raw_input")

		if action == "save" && !hasEnv {
			token := extractToken(rawInput)
			if token != "" {
				_ = ioutil.WriteFile(tokenPath, []byte(token), 0644)
				currentToken = token
			}
		} else if action == "start" && !isRunning {
			tokenToRun := currentToken
			if !hasEnv && rawInput != "" {
				tokenToRun = extractToken(rawInput)
				_ = ioutil.WriteFile(tokenPath, []byte(tokenToRun), 0644)
			}
			if tokenToRun != "" {
				// 启动前先清空旧日志
				_ = ioutil.WriteFile(logPath, []byte(""), 0644)
				c := exec.Command("cloudflared", "tunnel", "--no-autoupdate", "run", "--token", tokenToRun)
				f, _ := os.OpenFile(logPath, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0644)
				c.Stdout = f
				c.Stderr = f
				if err := c.Start(); err == nil {
					mu.Lock()
					tunnelCmd = c
					mu.Unlock()
					isRunning = true
				}
			}
		} else if action == "stop" && isRunning {
			mu.Lock()
			if tunnelCmd != nil && tunnelCmd.Process != nil {
				_ = tunnelCmd.Process.Kill()
				_ = tunnelCmd.Wait()
				tunnelCmd = nil
			}
			mu.Unlock()
			isRunning = false
		}
		http.Redirect(w, r, "/", http.StatusSeeOther)
		return
	}

	const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cloudflared 控制台</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root { --accent: #f38020; --bg: #f4f7fb; }
        body { 
            margin: 0; min-height: 100vh; display: flex; justify-content: center; align-items: center;
            background: radial-gradient(circle at top left, #e0e7ff, transparent 40%), radial-gradient(circle at bottom right, #ffedd5, transparent 40%);
            background-color: var(--bg); font-family: -apple-system, sans-serif; 
        }
        .container { 
            width: 90%; max-width: 400px; background: rgba(255,255,255,0.9); backdrop-filter: blur(20px);
            border-radius: 32px; padding: 40px; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.1); border: 1px solid #fff; text-align: center;
        }
        .status-pill { 
            display: inline-flex; align-items: center; gap: 8px; padding: 8px 20px; border-radius: 50px;
            font-size: 13px; font-weight: 800; margin: 20px 0 30px; transition: 0.3s;
        }
        .on { background: #dcfce7; color: #15803d; border: 1px solid #bbf7d0; }
        .off { background: #f1f5f9; color: #64748b; border: 1px solid #e2e8f0; }
        .dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
        .on .dot { animation: blink 1s infinite; }
        @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
        
        .token-area { text-align: left; margin-bottom: 25px; }
        .label { font-size: 11px; font-weight: 800; color: #94a3b8; text-transform: uppercase; margin-bottom: 8px; padding-left: 5px; }
        .token-box { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 16px; padding: 15px; font-family: monospace; font-size: 12px; word-break: break-all; color: #475569; }
        textarea { width: 100%; border: 2px solid #e2e8f0; border-radius: 16px; padding: 15px; box-sizing: border-box; font-size: 13px; background: #fff; resize: none; margin-top: 5px; }
        
        button { 
            width: 100%; border: none; border-radius: 18px; padding: 15px; font-weight: 700; cursor: pointer; 
            display: flex; align-items: center; justify-content: center; gap: 10px; transition: 0.2s;
        }
        .btn-start { background: linear-gradient(135deg, #f38020, #faad14); color: white; box-shadow: 0 10px 20px rgba(243,128,32,0.2); }
        .btn-stop { background: #fee2e2; color: #ef4444; }
        .btn-save { background: #fff; color: #64748b; border: 1px solid #e2e8f0; margin-bottom: 10px; }
        button:active { transform: scale(0.97); }
    </style>
</head>
<body>
    <div class="container">
        <div style="font-size: 50px; color: var(--accent);"><i class="fa-brands fa-cloudflare"></i></div>
        <h2 style="margin: 10px 0 5px;">Cloudflared</h2>
        
        <div class="status-pill {{if .IsRunning}}on{{else}}off{{end}}">
            <div class="dot"></div>
            {{if .IsRunning}}隧道已连接边缘网络{{else}}服务处于离线状态{{end}}
        </div>

        <form method="post">
            {{if not .IsRunning}}
                <div class="token-area">
                    <div class="label">{{if .HasEnv}}Environment Token{{else}}Current Configuration{{end}}</div>
                    {{if .Token}}<div class="token-box">{{.Token}}</div>{{end}}
                    
                    {{if not .HasEnv}}
                        <textarea name="raw_input" rows="3" placeholder="输入 Token 或 Docker run 命令..."></textarea>
                    {{end}}
                </div>
                
                {{if not .HasEnv}}
                    <button type="submit" name="action" value="save" class="btn-save"><i class="fa-solid fa-floppy-disk"></i> 保存本地配置</button>
                {{end}}
                <button type="submit" name="action" value="start" class="btn-start"><i class="fa-solid fa-bolt"></i> 启动隧道</button>
            {{else}}
                <div style="margin-bottom: 30px; color: #94a3b8; font-size: 13px;">
                    <i class="fa-solid fa-shield-halved"></i> 隧道加密传输中，配置已锁定
                </div>
                <button type="submit" name="action" value="stop" class="btn-stop">
                    <i class="fa-solid fa-power-off"></i> 断开隧道连接
                </button>
            {{end}}
        </form>
    </div>
</body>
</html>`

	t, _ := template.New("web").Parse(html)
	t.Execute(w, map[string]interface{}{
		"IsRunning": isRunning,
		"Token":     currentToken,
		"HasEnv":    hasEnv,
	})
}

func main() {
	_ = os.MkdirAll(dataDir, 0755)
	http.HandleFunc("/", indexHandler)
	fmt.Println("Secure Manager running on :12222")
	http.ListenAndServe(":12222", nil)
}
