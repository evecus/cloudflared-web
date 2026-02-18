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

// 语言包定义
type i18n struct {
	Title       string
	StatusOn    string
	StatusOff   string
	TokenPlace  string
	SaveBtn     string
	EditBtn     string
	StartBtn    string
	StopBtn     string
	SaveSuccess string
	SaveFail    string
	ConnFail    string
	SwitchLang  string
	CurrentLang string
}

var locales = map[string]i18n{
	"zh": {
		Title:       "隧道控制中心",
		StatusOn:    "连接已就绪",
		StatusOff:   "未连接",
		TokenPlace:  "在此粘贴 Token 或 Docker 命令...",
		SaveBtn:     "保存配置",
		EditBtn:     "修改配置",
		StartBtn:    "启动连接",
		StopBtn:     "断开连接",
		SaveSuccess: "配置已保存",
		SaveFail:    "保存失败",
		ConnFail:    "连接失败，请检查配置或网络",
		SwitchLang:  "English",
		CurrentLang: "zh",
	},
	"en": {
		Title:       "Tunnel Manager",
		StatusOn:    "Online",
		StatusOff:   "Offline",
		TokenPlace:  "Paste Token or Docker command here...",
		SaveBtn:     "Save Config",
		EditBtn:     "Edit Config",
		StartBtn:    "Start Tunnel",
		StopBtn:     "Stop Tunnel",
		SaveSuccess: "Config Saved",
		SaveFail:    "Save Failed",
		ConnFail:    "Connection failed. Check config or network.",
		SwitchLang:  "中文",
		CurrentLang: "en",
	},
}

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
			if strings.Contains(line, "Connected") || strings.Contains(line, "Registered") || strings.Contains(line, "Updated to new configuration") {
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
	case <-time.After(7 * time.Second):
		_ = cmd.Process.Kill()
		return false
	}
}

func indexHandler(w http.ResponseWriter, r *http.Request) {
	mu.Lock()
	isRunning := tunnelCmd != nil && tunnelCmd.Process != nil && tunnelCmd.ProcessState == nil
	mu.Unlock()

	lang := r.URL.Query().Get("lang")
	if lang != "en" { lang = "zh" }
	tNext := "en"
	if lang == "en" { tNext = "zh" }
	
	isModifying := r.URL.Query().Get("edit") == "true"
	currentToken := getStoredToken()
	hasToken := currentToken != ""
	
	msgKey := r.URL.Query().Get("msg")
	msgType := r.URL.Query().Get("type")
	displayMsg := ""
	if msgKey != "" {
		switch msgKey {
		case "saved": displayMsg = locales[lang].SaveSuccess
		case "save_err": displayMsg = locales[lang].SaveFail
		case "conn_err": displayMsg = locales[lang].ConnFail
		}
	}

	if r.Method == "POST" {
		action := r.FormValue("action")
		rawInput := r.FormValue("raw_input")
		if action == "save" {
			token := extractToken(rawInput)
			if token != "" {
				_ = os.MkdirAll(dataDir, 0755)
				if err := ioutil.WriteFile(tokenPath, []byte(token), 0644); err == nil {
					http.Redirect(w, r, "/?lang="+lang+"&msg=saved&type=success", http.StatusSeeOther)
					return
				}
			}
			http.Redirect(w, r, "/?lang="+lang+"&msg=save_err&type=error", http.StatusSeeOther)
			return
		} else if action == "start" && !isRunning {
			if startTunnelWithCheck(currentToken) {
				http.Redirect(w, r, "/?lang="+lang, http.StatusSeeOther)
			} else {
				http.Redirect(w, r, "/?lang="+lang+"&msg=conn_err&type=error", http.StatusSeeOther)
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
			http.Redirect(w, r, "/?lang="+lang, http.StatusSeeOther)
			return
		}
	}

	const html = `<!DOCTYPE html>
<html lang="{{.I18n.CurrentLang}}">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{.I18n.Title}}</title>
    <link rel="icon" href="https://www.cloudflare.com/favicon.ico" type="image/x-icon">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root { --accent: #f38020; --primary-grad: linear-gradient(135deg, #f38020 0%, #faad14 100%); --glass: rgba(255, 255, 255, 0.85); }
        body { 
            margin: 0; min-height: 100vh; display: flex; justify-content: center; align-items: center;
            background: radial-gradient(circle at 10% 20%, #e0e7ff 0%, transparent 40%),
                        radial-gradient(circle at 90% 80%, #ffedd5 0%, transparent 40%), #f8fafc;
            font-family: -apple-system, "PingFang SC", sans-serif;
        }
        .lang-switch { position: fixed; top: 20px; right: 20px; z-index: 100; }
        .lang-btn { background: var(--glass); padding: 8px 15px; border-radius: 12px; text-decoration: none; color: #475569; font-size: 13px; font-weight: 700; border: 1px solid rgba(255,255,255,0.6); backdrop-filter: blur(10px); transition: 0.2s; }
        .lang-btn:hover { background: white; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }

        .card { width: 90%; max-width: 400px; padding: 45px 35px; background: var(--glass); backdrop-filter: blur(20px); border-radius: 35px; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.1); border: 1px solid rgba(255,255,255,0.6); text-align: center; position: relative; }
        .status-pill { display: inline-flex; align-items: center; gap: 8px; padding: 8px 22px; border-radius: 50px; font-size: 13px; font-weight: 800; margin-bottom: 30px; }
        .on { background: #dcfce7; color: #15803d; border: 1px solid #bbf7d0; }
        .off { background: #f1f5f9; color: #64748b; border: 1px solid #e2e8f0; }
        .dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
        .on .dot { animation: blink 1.2s infinite; }
        @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }

        .token-view { background: rgba(248,250,252,0.8); border: 1px solid #e2e8f0; border-radius: 18px; padding: 20px; font-family: monospace; font-size: 13px; word-break: break-all; color: #475569; text-align: left; margin-bottom: 25px; line-height: 1.5; }
        textarea { width: 100%; border: 2px solid #e2e8f0; border-radius: 20px; padding: 20px; box-sizing: border-box; font-size: 14px; background: rgba(255,255,255,0.9); resize: none; margin-bottom: 25px; transition: 0.3s; }
        textarea:focus { outline: none; border-color: var(--accent); }

        .btn-group { display: flex; gap: 12px; }
        button, .btn-link { flex: 1; height: 55px; border: none; border-radius: 18px; font-weight: 800; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px; transition: 0.2s; font-size: 15px; text-decoration: none; box-sizing: border-box; }
        .btn-main { background: var(--primary-grad); color: white; box-shadow: 0 8px 20px rgba(243,128,32,0.25); }
        .btn-edit { background: white; color: #64748b; border: 1.5px solid #e2e8f0; }
        .btn-stop { width: 100%; background: #fee2e2; color: #ef4444; border: 1.5px solid rgba(239,68,68,0.1); }
        button:active { transform: scale(0.96); }

        .msg { margin-top: 20px; font-size: 13px; font-weight: 800; padding: 12px; border-radius: 15px; }
        .msg-success { color: #15803d; background: #f0fdf4; border: 1px solid #bbf7d0; }
        .msg-error { color: #b91c1c; background: #fef2f2; border: 1px solid #fecaca; }
    </style>
</head>
<body>
    <div class="lang-switch">
        <a href="?lang={{.NextLang}}{{if .IsModifying}}&edit=true{{end}}" class="lang-btn">
            <i class="fa-solid fa-language"></i> {{.I18n.SwitchLang}}
        </a>
    </div>

    <div class="card">
        <div style="font-size: 55px; color: var(--accent); margin-bottom: 10px;"><i class="fa-brands fa-cloudflare"></i></div>
        <h2 style="margin: 0 0 25px; font-weight: 900; color: #1e293b; letter-spacing: -1px;">{{.I18n.Title}}</h2>

        <div class="status-pill {{if .IsRunning}}on{{else}}off{{end}}">
            <div class="dot"></div> {{if .IsRunning}}{{.I18n.StatusOn}}{{else}}{{.I18n.StatusOff}}{{end}}
        </div>

        <form method="post" action="?lang={{.I18n.CurrentLang}}">
            {{if .IsRunning}}
                <div class="token-view">{{.Token}}</div>
                <button type="submit" name="action" value="stop" class="btn-stop"><i class="fa-solid fa-power-off"></i> {{.I18n.StopBtn}}</button>
            {{else if or (not .HasToken) .IsModifying}}
                <textarea name="raw_input" rows="4" placeholder="{{.I18n.TokenPlace}}">{{if .IsModifying}}{{.Token}}{{end}}</textarea>
                <button type="submit" name="action" value="save" class="btn-main" style="width:100%"><i class="fa-solid fa-floppy-disk"></i> {{.I18n.SaveBtn}}</button>
            {{else}}
                <div class="token-view">{{.Token}}</div>
                <div class="btn-group">
                    <a href="/?lang={{.I18n.CurrentLang}}&edit=true" class="btn-link btn-edit"><i class="fa-solid fa-pen-to-square"></i> {{.I18n.EditBtn}}</a>
                    <button type="submit" name="action" value="start" class="btn-main"><i class="fa-solid fa-bolt"></i> {{.I18n.StartBtn}}</button>
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
		"Message":     displayMsg,
		"MsgType":     msgType,
		"I18n":        locales[lang],
		"NextLang":    tNext,
	})
}

func main() {
	_ = os.MkdirAll(dataDir, 0755)
	http.HandleFunc("/", indexHandler)
	http.ListenAndServe(":12222", nil)
}
