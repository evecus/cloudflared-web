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
	re := regexp.MustCompile(`[eE]yJh[a-zA-Z0-9\-_]{50,}`)
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
	message := ""

	if r.Method == "POST" {
		action := r.FormValue("action")
		rawInput := r.FormValue("raw_input")

		if action == "save" && !hasEnv {
			token := extractToken(rawInput)
			if token != "" {
				_ = ioutil.WriteFile(tokenPath, []byte(token), 0644)
				currentToken = token
				message = "配置已成功保存至本地"
			} else {
				message = "保存失败：未检测到有效 Token"
			}
		} else if action == "start" && !isRunning {
			tokenToRun := currentToken
			if !hasEnv && rawInput != "" {
				tokenToRun = extractToken(rawInput)
				_ = ioutil.WriteFile(tokenPath, []byte(tokenToRun), 0644)
			}
			if tokenToRun != "" {
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
					// 启动时不显示保存成功的提示
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
		
		// 如果有消息，通过 URL 参数传递或简单模板渲染，这里直接渲染
		if message == "" {
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
        :root { --accent: #f38020; --bg: #f4f7fb; }
        body { 
            margin: 0; min-height: 100vh; display: flex; justify-content: center; align-items: center;
            background: radial-gradient(circle at 15% 15%, #e0e7ff, transparent 45%), radial-gradient(circle at 85% 85%, #ffedd5, transparent 45%);
            background-color: var(--bg); font-family: -apple-system, "PingFang SC", sans-serif;
        }
        .container { 
            width: 90%; max-width: 400px; background: rgba(255,255,255,0.85); backdrop-filter: blur(25px);
            border-radius: 35px; padding: 45px 30px; box-shadow: 0 30px 60px -12px rgba(0,0,0,0.12); border: 1px solid #fff; text-align: center;
        }
        .status-pill { 
            display: inline-flex; align-items: center; gap: 8px; padding: 10px 24px; border-radius: 50px;
            font-size: 13px; font-weight: 800; margin-bottom: 35px; transition: 0.4s;
        }
        .on { background: #dcfce7; color: #15803d; border: 1px solid #bbf7d0; }
        .off { background: #f1f5f9; color: #64748b; border: 1px solid #e2e8f0; }
        .dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
        .on .dot { animation: blink 1.2s infinite; }
        @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
        
        .token-area { text-align: left; margin-bottom: 25px; }
        .label { font-size: 11px; font-weight: 800; color: #94a3b8; text-transform: uppercase; margin: 0 0 10px 5px; }
        .token-box { background: rgba(248,250,252,0.8); border: 1px solid #e2e8f0; border-radius: 18px; padding: 16px; font-family: monospace; font-size: 12px; word-break: break-all; color: #475569; }
        textarea { width: 100%; border: 2px solid #e2e8f0; border-radius: 18px; padding: 16px; box-sizing: border-box; font-size: 13px; background: #fff; resize: none; margin-top: 8px; transition: 0.3s; }
        textarea:focus { outline: none; border-color: var(--accent); }

        /* 左右排版容器 */
        .btn-group { display: flex; gap: 12px; }
        button { 
            border: none; border-radius: 18px; padding: 16px; font-weight: 800; cursor: pointer; 
            display: flex; align-items: center; justify-content: center; gap: 8px; transition: 0.2s; font-size: 14px;
        }
        .btn-start { flex: 1.2; background: linear-gradient(135deg, #f38020, #faad14); color: white; box-shadow: 0 10px 20px rgba(243,128,32,0.2); }
        .btn-save { flex: 1; background: white; color: #64748b; border: 1px solid #e2e8f0; }
        .btn-stop { width: 100%; background: #fee2e2; color: #ef4444; }
        button:active { transform: scale(0.96); }

        .msg { margin-top: 20px; padding: 12px; border-radius: 14px; font-size: 13px; font-weight: 700; background: #f0f9ff; color: #0369a1; border: 1px solid #bae6fd; animation: fadeIn 0.3s; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }
    </style>
</head>
<body>
    <div class="container">
        <div style="font-size: 50px; color: var(--accent);"><i class="fa-brands fa-cloudflare"></i></div>
        <h2 style="margin: 10px 0 25px;">隧道控制中心</h2>
        
        <div class="status-pill {{if .IsRunning}}on{{else}}off{{end}}">
            <div class="dot"></div>
            {{if .IsRunning}}已加密连接至云端{{else}}隧道未运行{{end}}
        </div>

        <form method="post">
            {{if not .IsRunning}}
                <div class="token-area">
                    <div class="label">{{if .HasEnv}}环境变量模式{{else}}当前配置{{end}}</div>
                    {{if .Token}}<div class="token-box">{{.Token}}</div>{{end}}
                    {{if not .HasEnv}}<textarea name="raw_input" rows="3" placeholder="粘贴 Token 或 Docker 命令..."></textarea>{{end}}
                </div>
                
                <div class="btn-group">
                    {{if not .HasEnv}}<button type="submit" name="action" value="save" class="btn-save"><i class="fa-solid fa-floppy-disk"></i> 保存本地</button>{{end}}
                    <button type="submit" name="action" value="start" class="btn-start" style="{{if .HasEnv}}flex:1;{{end}}"><i class="fa-solid fa-bolt"></i> 启动连接</button>
                </div>
            {{else}}
                <div style="height: 20px;"></div>
                <button type="submit" name="action" value="stop" class="btn-stop"><i class="fa-solid fa-power-off"></i> 断开连接</button>
            {{end}}
        </form>

        {{if .Message}}<div class="msg">{{.Message}}</div>{{end}}
    </div>
</body>
</html>`

	t, _ := template.New("web").Parse(html)
	t.Execute(w, map[string]interface{}{
		"IsRunning": isRunning,
		"Token":     currentToken,
		"HasEnv":    hasEnv,
		"Message":   message,
	})
}

func main() {
	_ = os.MkdirAll(dataDir, 0755)
	http.HandleFunc("/", indexHandler)
	fmt.Println("UI Optimized Manager running on :12222")
	http.ListenAndServe(":12222", nil)
}
