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
				c := exec.Command("cloudflared", "tunnel", "--no-autoupdate", "run", "--token", tokenToRun)
				f, _ := os.OpenFile(logPath, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0644)
				c.Stdout = f
				c.Stderr = f
				if err := c.Start(); err == nil {
					mu.Lock()
					tunnelCmd = c
					mu.Unlock()
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
		}
		http.Redirect(w, r, "/", http.StatusSeeOther)
		return
	}

	const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cloudflared 控制台</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root {
            --accent: #f38020;
            --accent-grad: linear-gradient(135deg, #f38020 0%, #faad14 100%);
            --bg: #f4f7fb;
            --card-bg: rgba(255, 255, 255, 0.9);
            --text-main: #1e293b;
        }
        body {
            margin: 0; min-height: 100vh;
            display: flex; justify-content: center; align-items: center;
            background: radial-gradient(circle at 0% 0%, #e0e7ff 0%, transparent 40%),
                        radial-gradient(circle at 100% 100%, #ffedd5 0%, transparent 40%);
            background-color: var(--bg);
            font-family: -apple-system, "PingFang SC", sans-serif;
            color: var(--text-main);
        }
        .container {
            width: 90%; max-width: 420px;
            background: var(--card-bg);
            backdrop-filter: blur(20px);
            border-radius: 30px;
            padding: 40px;
            box-shadow: 0 20px 50px rgba(0,0,0,0.05);
            border: 1px solid rgba(255,255,255,0.6);
            text-align: center;
        }
        .logo-area { font-size: 50px; color: var(--accent); margin-bottom: 10px; }
        h1 { font-size: 22px; margin: 0; font-weight: 800; letter-spacing: -0.5px; }
        .subtitle { font-size: 13px; color: #64748b; margin-bottom: 25px; }

        .status-pill {
            display: inline-flex; align-items: center; gap: 8px;
            padding: 8px 20px; border-radius: 50px;
            font-size: 13px; font-weight: 700; margin-bottom: 30px;
            transition: 0.3s;
        }
        .status-pill.on { background: #dcfce7; color: #15803d; border: 1px solid #bbf7d0; }
        .status-pill.off { background: #f1f5f9; color: #64748b; border: 1px solid #e2e8f0; }
        .dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
        .on .dot { animation: blink 1.2s infinite; }
        @keyframes blink { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.4; transform: scale(0.8); } }

        .token-card {
            background: #f8fafc; border: 1px solid #e2e8f0;
            border-radius: 16px; padding: 15px; margin-bottom: 20px;
            text-align: left; position: relative;
        }
        .token-label { font-size: 11px; font-weight: 800; color: #94a3b8; text-transform: uppercase; margin-bottom: 8px; }
        .token-value { font-family: "JetBrains Mono", monospace; font-size: 12px; word-break: break-all; color: #334155; line-height: 1.5; }
        
        textarea {
            width: 100%; border: 2px solid #e2e8f0; border-radius: 16px;
            padding: 15px; box-sizing: border-box; font-size: 13px;
            font-family: inherit; margin-bottom: 20px; transition: 0.3s;
            background: rgba(255,255,255,0.5); resize: none;
        }
        textarea:focus { outline: none; border-color: var(--accent); background: #fff; }

        .actions { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
        button {
            border: none; border-radius: 16px; padding: 14px;
            font-weight: 700; font-size: 14px; cursor: pointer;
            display: flex; align-items: center; justify-content: center; gap: 8px;
            transition: all 0.2s;
        }
        button:active { transform: scale(0.96); }
        .btn-run { background: var(--accent-grad); color: white; box-shadow: 0 10px 20px rgba(243, 128, 32, 0.2); grid-column: span {{if .HasEnv}}2{{else}}1{{end}}; }
        .btn-save { background: white; color: #475569; border: 1px solid #e2e8f0; }
        .btn-stop { background: #fee2e2; color: #ef4444; grid-column: span 2; }
    </style>
</head>
<body>
    <div class="container">
        <div class="logo-area"><i class="fa-brands fa-cloudflare"></i></div>
        <h1>隧道管理仪表盘</h1>
        <div class="subtitle">Cloudflared 边缘网络连接控制器</div>

        <div class="status-pill {{if .IsRunning}}on{{else}}off{{end}}">
            <div class="dot"></div>
            {{if .IsRunning}}TUNNEL ACTIVE{{else}}TUNNEL OFFLINE{{end}}
        </div>

        <form method="post">
            {{if .Token}}
            <div class="token-card">
                <div class="token-label">{{if .HasEnv}}Environment Token{{else}}Stored Token{{end}}</div>
                <div class="token-value">{{.Token}}</div>
            </div>
            {{end}}

            {{if not .HasEnv}}
            <textarea name="raw_input" rows="3" placeholder="输入 Token 或 Docker run 命令..." {{if .IsRunning}}disabled{{end}}></textarea>
            {{end}}

            <div class="actions">
                {{if .IsRunning}}
                <button type="submit" name="action" value="stop" class="btn-stop">
                    <i class="fa-solid fa-power-off"></i> 停止连接
                </button>
                {{else}}
                    {{if not .HasEnv}}
                    <button type="submit" name="action" value="save" class="btn-save">
                        <i class="fa-solid fa-bookmark"></i> 保存
                    </button>
                    {{end}}
                    <button type="submit" name="action" value="start" class="btn-run">
                        <i class="fa-solid fa-play"></i> 启动隧道
                    </button>
                {{end}}
            </div>
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
	fmt.Println("Manager running on :12222")
	http.ListenAndServe(":12222", nil)
}
