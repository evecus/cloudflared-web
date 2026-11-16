use std::{
    env,
    path::{Path, PathBuf},
    process::Stdio,
    sync::{Arc, OnceLock},
    time::Duration,
};

use axum::{
    extract::{Query, Request, State},
    http::{
        header::{HeaderValue, AUTHORIZATION, WWW_AUTHENTICATE},
        StatusCode,
    },
    middleware::{self, Next},
    response::{Html, IntoResponse, Redirect, Response},
    routing::get,
    Form, Router,
};
use base64::Engine;
use regex::Regex;
use serde::Deserialize;
use subtle::ConstantTimeEq;
use tokio::{
    io::{AsyncBufReadExt, BufReader},
    net::TcpListener,
    process::{Child, Command},
    sync::{oneshot, Mutex},
    time::timeout,
};

const DEFAULT_PORT: &str = "12222";
const DEFAULT_BIN: &str = "cloudflared";
const DEFAULT_DIR: &str = "/app/data";
const START_TIMEOUT_SECS: u64 = 7;
const SUCCESS_MARKERS: [&str; 3] = ["Connected", "Registered", "Updated to new configuration"];

/// 语言包。
#[derive(Debug)]
struct I18n {
    title: &'static str,
    status_on: &'static str,
    status_off: &'static str,
    token_place: &'static str,
    save_btn: &'static str,
    edit_btn: &'static str,
    start_btn: &'static str,
    stop_btn: &'static str,
    save_success: &'static str,
    save_fail: &'static str,
    conn_fail: &'static str,
    switch_lang: &'static str,
    current_lang: &'static str,
}

static ZH: I18n = I18n {
    title: "隧道控制中心",
    status_on: "连接已就绪",
    status_off: "未连接",
    token_place: "在此粘贴 Token 或 Docker 命令...",
    save_btn: "保存配置",
    edit_btn: "修改配置",
    start_btn: "启动连接",
    stop_btn: "断开连接",
    save_success: "配置已保存",
    save_fail: "保存失败",
    conn_fail: "连接失败，请检查配置或网络",
    switch_lang: "English",
    current_lang: "zh",
};

static EN: I18n = I18n {
    title: "Tunnel Manager",
    status_on: "Online",
    status_off: "Offline",
    token_place: "Paste Token or Docker command here...",
    save_btn: "Save Config",
    edit_btn: "Edit Config",
    start_btn: "Start Tunnel",
    stop_btn: "Stop Tunnel",
    save_success: "Config Saved",
    save_fail: "Save Failed",
    conn_fail: "Connection failed. Check config or network.",
    switch_lang: "中文",
    current_lang: "en",
};

fn i18n(lang: &str) -> &'static I18n {
    if lang == "en" {
        &EN
    } else {
        &ZH
    }
}

/// 启动后不再变化的配置。
struct Config {
    data_dir: PathBuf,
    bin: String,
    auth_user: String,
    auth_pass: String,
}

/// 运行时可变状态：隧道子进程与最近一次启动错误。
struct RuntimeState {
    child: Option<Child>,
    last_err: String,
}

impl RuntimeState {
    /// 判断隧道是否仍在运行；若子进程已退出则顺手清理。
    fn is_running(&mut self) -> bool {
        let Some(child) = self.child.as_mut() else {
            return false;
        };
        match child.try_wait() {
            Ok(None) => true,
            Ok(Some(_)) => {
                self.child = None;
                false
            }
            Err(_) => false,
        }
    }
}

#[derive(Clone)]
struct AppState {
    config: Arc<Config>,
    runtime: Arc<Mutex<RuntimeState>>,
}

#[derive(Debug, Deserialize)]
struct PageQuery {
    lang: Option<String>,
    edit: Option<String>,
    msg: Option<String>,
    #[serde(rename = "type")]
    msg_type: Option<String>,
}

#[derive(Debug, Deserialize)]
struct ActionForm {
    action: Option<String>,
    raw_input: Option<String>,
}

/// 从用户输入（可能是整条 Docker 命令）里提取 JWT token。
fn extract_token(input: &str) -> String {
    if input.is_empty() {
        return String::new();
    }
    // 去掉所有空白字符和反斜杠，便于从带续行符的 Docker 命令中匹配。
    let cleaned: String = input
        .chars()
        .filter(|c| !c.is_whitespace() && *c != '\\')
        .collect();

    static TOKEN_RE: OnceLock<Regex> = OnceLock::new();
    let re = TOKEN_RE.get_or_init(|| {
        Regex::new(r"[eE]yJh[a-zA-Z0-9\-_]{50,}").expect("token regex must compile")
    });
    if let Some(m) = re.find(&cleaned) {
        return m.as_str().to_string();
    }
    input.trim().to_string()
}

fn persist_state(data_dir: &Path, state: &str) {
    let _ = std::fs::write(data_dir.join("state"), state);
}

fn get_saved_state(data_dir: &Path) -> String {
    std::fs::read_to_string(data_dir.join("state"))
        .unwrap_or_else(|_| "stopped".to_string())
        .trim()
        .to_string()
}

fn get_stored_token(data_dir: &Path) -> String {
    if let Ok(t) = env::var("token") {
        if !t.is_empty() {
            return extract_token(&t);
        }
    }
    if let Ok(t) = env::var("TOKEN") {
        if !t.is_empty() {
            return extract_token(&t);
        }
    }
    std::fs::read_to_string(data_dir.join("token"))
        .unwrap_or_default()
        .trim()
        .to_string()
}

/// 启动 cloudflared，并在 7 秒内等待 stderr 出现成功标志。
/// 成功则返回子进程；超时或启动失败则杀掉进程并返回错误。
async fn start_tunnel(bin: &str, token: &str) -> Result<Child, String> {
    let mut cmd = Command::new(bin);
    cmd.args(["tunnel", "--no-autoupdate", "run", "--token", token])
        .stdout(Stdio::null())
        .stderr(Stdio::piped());

    let mut child = cmd.spawn().map_err(|e| e.to_string())?;
    let stderr = child
        .stderr
        .take()
        .ok_or_else(|| "failed to capture cloudflared stderr".to_string())?;

    let (tx, rx) = oneshot::channel::<()>();
    tokio::spawn(async move {
        let mut lines = BufReader::new(stderr).lines();
        let mut signal = Some(tx);
        // 持续排空 stderr，避免管道写满阻塞子进程（成功后再来的日志直接丢弃）。
        while let Ok(Some(line)) = lines.next_line().await {
            if SUCCESS_MARKERS.iter().any(|marker| line.contains(marker)) {
                if let Some(sender) = signal.take() {
                    let _ = sender.send(());
                }
            }
        }
    });

    match timeout(Duration::from_secs(START_TIMEOUT_SECS), rx).await {
        Ok(Ok(())) => Ok(child),
        Ok(Err(_)) => {
            let _ = child.kill().await;
            Err("cloudflared stderr watcher closed before reporting success".to_string())
        }
        Err(_) => {
            let _ = child.kill().await;
            Err("timeout waiting for cloudflared to report a successful connection".to_string())
        }
    }
}

/// 探测隧道真实运行状态，顺带清理已退出的子进程。
async fn probe_running(app: &AppState) -> bool {
    let mut rt = app.runtime.lock().await;
    rt.is_running()
}

/// 渲染主页面。
async fn render_page(app: &AppState, q: &PageQuery, is_running: bool) -> Response {
    let lang = if q.lang.as_deref() == Some("en") {
        "en"
    } else {
        "zh"
    };
    let t_next = if lang == "en" { "zh" } else { "en" };
    let is_modifying = q.edit.as_deref() == Some("true");
    let current_token = get_stored_token(&app.config.data_dir);
    let has_token = !current_token.is_empty();

    let display_msg: String = match q.msg.as_deref() {
        Some("saved") => i18n(lang).save_success.to_string(),
        Some("save_err") => i18n(lang).save_fail.to_string(),
        Some("conn_err") => {
            let err = app.runtime.lock().await.last_err.clone();
            let base = i18n(lang).conn_fail;
            if err.is_empty() {
                base.to_string()
            } else {
                format!("{base} ({err})")
            }
        }
        _ => String::new(),
    };
    let msg_type = q.msg_type.clone().unwrap_or_default();

    Html(render_html(
        is_running,
        &current_token,
        has_token,
        is_modifying,
        &display_msg,
        &msg_type,
        i18n(lang),
        t_next,
    ))
    .into_response()
}

/// 对插入到 HTML 中的动态内容进行转义，防止 XSS（对齐原 html/template 与 tera 的自动转义）。
fn html_escape(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for c in s.chars() {
        match c {
            '&' => out.push_str("&amp;"),
            '<' => out.push_str("&lt;"),
            '>' => out.push_str("&gt;"),
            '"' => out.push_str("&quot;"),
            '\'' => out.push_str("&#39;"),
            _ => out.push(c),
        }
    }
    out
}

/// 用纯 Rust 拼接完整 HTML 页面（无外部模板文件）。
#[allow(clippy::too_many_arguments)]
fn render_html(
    is_running: bool,
    token: &str,
    has_token: bool,
    is_modifying: bool,
    message: &str,
    msg_type: &str,
    t: &I18n,
    next_lang: &str,
) -> String {
    let edit_suffix = if is_modifying { "&edit=true" } else { "" };

    // 表单主体：运行 -> 断开按钮；无 token 或编辑中 -> 文本域 + 保存按钮；否则 -> 编辑/启动按钮组
    let form_body = if is_running {
        format!(
            r#"<button type="submit" name="action" value="stop" class="btn-stop"><i class="fa-solid fa-power-off"></i> {}</button>"#,
            html_escape(t.stop_btn)
        )
    } else if !has_token || is_modifying {
        let shown_token = if is_modifying { token } else { "" };
        format!(
            r#"<textarea name="raw_input" rows="4" placeholder="{}">{}</textarea>
                <button type="submit" name="action" value="save" class="btn-main" style="width:100%"><i class="fa-solid fa-floppy-disk"></i> {}</button>"#,
            html_escape(t.token_place),
            html_escape(shown_token),
            html_escape(t.save_btn)
        )
    } else {
        format!(
            r#"<div class="btn-group">
                    <a href="/?lang={}&edit=true" class="btn-link btn-edit"><i class="fa-solid fa-pen-to-square"></i> {}</a>
                    <button type="submit" name="action" value="start" class="btn-main"><i class="fa-solid fa-bolt"></i> {}</button>
                </div>"#,
            html_escape(t.current_lang),
            html_escape(t.edit_btn),
            html_escape(t.start_btn)
        )
    };

    let status_class = if is_running { "on" } else { "off" };
    let status_text = if is_running {
        t.status_on
    } else {
        t.status_off
    };

    let msg_block = if message.is_empty() {
        String::new()
    } else {
        format!(
            r#"<div class="msg msg-{}">{}</div>"#,
            html_escape(msg_type),
            html_escape(message)
        )
    };

    format!(
        r#"<!DOCTYPE html>
<html lang="{}">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{}</title>
    <link rel="icon" href="https://www.cloudflare.com/favicon.ico" type="image/x-icon">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root {{ --accent: #f38020; --primary-grad: linear-gradient(135deg, #f38020 0%, #faad14 100%); --glass: rgba(255, 255, 255, 0.85); }}
        body {{
            margin: 0; min-height: 100vh; display: flex; justify-content: center; align-items: center;
            background: radial-gradient(circle at 10% 20%, #e0e7ff 0%, transparent 40%),
                        radial-gradient(circle at 90% 80%, #ffedd5 0%, transparent 40%), #f8fafc;
            font-family: -apple-system, "PingFang SC", sans-serif;
        }}
        .lang-switch {{ position: fixed; top: 20px; right: 20px; z-index: 100; }}
        .lang-btn {{ background: var(--glass); padding: 8px 15px; border-radius: 12px; text-decoration: none; color: #475569; font-size: 13px; font-weight: 700; border: 1px solid rgba(255,255,255,0.6); backdrop-filter: blur(10px); transition: 0.2s; }}
        .lang-btn:hover {{ background: white; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }}

        .card {{ width: 90%; max-width: 400px; padding: 45px 35px; background: var(--glass); backdrop-filter: blur(20px); border-radius: 35px; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.1); border: 1px solid rgba(255,255,255,0.6); text-align: center; position: relative; }}
        .status-pill {{ display: inline-flex; align-items: center; gap: 8px; padding: 8px 22px; border-radius: 50px; font-size: 13px; font-weight: 800; margin-bottom: 30px; }}
        .on {{ background: #dcfce7; color: #15803d; border: 1px solid #bbf7d0; }}
        .off {{ background: #f1f5f9; color: #64748b; border: 1px solid #e2e8f0; }}
        .dot {{ width: 8px; height: 8px; border-radius: 50%; background: currentColor; }}
        .on .dot {{ animation: blink 1.2s infinite; }}
        @keyframes blink {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.3; }} }}

        .token-view {{ background: rgba(248,250,252,0.8); border: 1px solid #e2e8f0; border-radius: 18px; padding: 20px; font-family: monospace; font-size: 13px; word-break: break-all; color: #475569; text-align: left; margin-bottom: 25px; line-height: 1.5; }}
        .token-masked {{ text-align: center; letter-spacing: 4px; color: #94a3b8; font-size: 18px; }}
        textarea {{ width: 100%; border: 2px solid #e2e8f0; border-radius: 20px; padding: 20px; box-sizing: border-box; font-size: 14px; background: rgba(255,255,255,0.9); resize: none; margin-bottom: 25px; transition: 0.3s; }}
        textarea:focus {{ outline: none; border-color: var(--accent); }}

        .btn-group {{ display: flex; gap: 12px; }}
        button, .btn-link {{ flex: 1; height: 55px; border: none; border-radius: 18px; font-weight: 800; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px; transition: 0.2s; font-size: 15px; text-decoration: none; box-sizing: border-box; }}
        .btn-main {{ background: var(--primary-grad); color: white; box-shadow: 0 8px 20px rgba(243,128,32,0.25); }}
        .btn-edit {{ background: white; color: #64748b; border: 1.5px solid #e2e8f0; }}
        .btn-stop {{ width: 100%; background: #fee2e2; color: #ef4444; border: 1.5px solid rgba(239,68,68,0.1); }}
        button:active {{ transform: scale(0.96); }}

        .msg {{ margin-top: 20px; font-size: 13px; font-weight: 800; padding: 12px; border-radius: 15px; }}
        .msg-success {{ color: #15803d; background: #f0fdf4; border: 1px solid #bbf7d0; }}
        .msg-error {{ color: #b91c1c; background: #fef2f2; border: 1px solid #fecaca; }}
    </style>
</head>
<body>
    <div class="lang-switch">
        <a href="?lang={}{}" class="lang-btn">
            <i class="fa-solid fa-language"></i> {}
        </a>
    </div>

    <div class="card">
        <div style="font-size: 55px; color: var(--accent); margin-bottom: 10px;"><i class="fa-brands fa-cloudflare"></i></div>
        <h2 style="margin: 0 0 25px; font-weight: 900; color: #1e293b; letter-spacing: -1px;">{}</h2>

        <div class="status-pill {}">
            <div class="dot"></div> {}
        </div>

        <form method="post" action="?lang={}">
            {}
        </form>

        {}
    </div>
</body>
</html>"#,
        html_escape(t.current_lang),
        html_escape(t.title),
        html_escape(next_lang),
        edit_suffix,
        html_escape(t.switch_lang),
        html_escape(t.title),
        status_class,
        html_escape(status_text),
        html_escape(t.current_lang),
        form_body,
        msg_block,
    )
}

async fn index_handler(State(app): State<AppState>, Query(q): Query<PageQuery>) -> Response {
    let is_running = probe_running(&app).await;
    render_page(&app, &q, is_running).await
}

async fn action_handler(
    State(app): State<AppState>,
    Query(q): Query<PageQuery>,
    Form(form): Form<ActionForm>,
) -> Response {
    let is_running = probe_running(&app).await;
    let lang = if q.lang.as_deref() == Some("en") {
        "en"
    } else {
        "zh"
    };

    match form.action.as_deref().unwrap_or("") {
        "save" => {
            let token = extract_token(form.raw_input.as_deref().unwrap_or(""));
            let saved = !token.is_empty()
                && std::fs::create_dir_all(&app.config.data_dir).is_ok()
                && std::fs::write(app.config.data_dir.join("token"), token).is_ok();
            let target = if saved {
                format!("/?lang={lang}&msg=saved&type=success")
            } else {
                format!("/?lang={lang}&msg=save_err&type=error")
            };
            Redirect::to(&target).into_response()
        }
        "start" if !is_running => {
            let current_token = get_stored_token(&app.config.data_dir);
            match start_tunnel(&app.config.bin, &current_token).await {
                Ok(child) => {
                    let mut rt = app.runtime.lock().await;
                    rt.child = Some(child);
                    rt.last_err.clear();
                    drop(rt);
                    persist_state(&app.config.data_dir, "running");
                    Redirect::to(&format!("/?lang={lang}")).into_response()
                }
                Err(e) => {
                    let mut rt = app.runtime.lock().await;
                    rt.last_err = e;
                    drop(rt);
                    Redirect::to(&format!("/?lang={lang}&msg=conn_err&type=error")).into_response()
                }
            }
        }
        "stop" => {
            let mut rt = app.runtime.lock().await;
            if let Some(child) = rt.child.as_mut() {
                let _ = child.kill().await;
                let _ = child.wait().await;
                rt.child = None;
            }
            drop(rt);
            persist_state(&app.config.data_dir, "stopped");
            Redirect::to(&format!("/?lang={lang}")).into_response()
        }
        // 未知 action：按当前查询参数重新渲染页面。
        _ => render_page(&app, &q, is_running).await,
    }
}

/// authPass 为空时直接放行；否则做常量时间比较，对齐 Go 版行为。
async fn basic_auth(State(app): State<AppState>, req: Request, next: Next) -> Response {
    if app.config.auth_pass.is_empty() {
        return next.run(req).await;
    }

    let mut authorized = false;
    if let Some(value) = req
        .headers()
        .get(AUTHORIZATION)
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.strip_prefix("Basic "))
    {
        if let Ok(decoded) = base64::engine::general_purpose::STANDARD.decode(value) {
            let text = String::from_utf8_lossy(&decoded);
            let (user, pass) = text.split_once(':').unwrap_or((&text, ""));
            authorized = bool::from(user.as_bytes().ct_eq(app.config.auth_user.as_bytes()))
                && bool::from(pass.as_bytes().ct_eq(app.config.auth_pass.as_bytes()));
        }
    }

    if !authorized {
        return (
            StatusCode::UNAUTHORIZED,
            [(
                WWW_AUTHENTICATE,
                HeaderValue::from_static("Basic realm=\"Tunnel Manager\""),
            )],
            "Unauthorized",
        )
            .into_response();
    }
    next.run(req).await
}

#[derive(Default)]
struct CliArgs {
    port: String,
    bin: String,
    dir: String,
    password: String,
}

/// 极简 flag 解析：支持 `--key value`、`--key=value` 及单横线写法。
fn parse_args(args: &[String]) -> CliArgs {
    let mut out = CliArgs {
        port: DEFAULT_PORT.to_string(),
        bin: DEFAULT_BIN.to_string(),
        dir: DEFAULT_DIR.to_string(),
        password: String::new(),
    };
    let mut i = 0;
    while i < args.len() {
        let raw = &args[i];
        let stripped = raw.strip_prefix("--").or_else(|| raw.strip_prefix('-'));
        let Some(rest) = stripped else {
            i += 1;
            continue;
        };
        let (key, inline) = match rest.split_once('=') {
            Some((k, v)) => (k.to_string(), Some(v.to_string())),
            None => (rest.to_string(), None),
        };
        let value = match inline {
            Some(v) => v,
            None => {
                i += 1;
                if i >= args.len() {
                    break;
                }
                args[i].clone()
            }
        };
        match key.as_str() {
            "port" => out.port = value,
            "bin" => out.bin = value,
            "dir" => out.dir = value,
            "password" => out.password = value,
            _ => {}
        }
        i += 1;
    }
    out
}

#[tokio::main]
async fn main() {
    let args: Vec<String> = env::args().skip(1).collect();
    let cli = parse_args(&args);

    let port = if cli.port != DEFAULT_PORT {
        cli.port
    } else {
        env::var("PORT").unwrap_or_else(|_| DEFAULT_PORT.to_string())
    };
    let bin = if cli.bin != DEFAULT_BIN {
        cli.bin
    } else {
        env::var("CLOUDFLARED_BIN").unwrap_or_else(|_| DEFAULT_BIN.to_string())
    };
    let data_dir = if cli.dir != DEFAULT_DIR {
        PathBuf::from(cli.dir)
    } else {
        PathBuf::from(env::var("DATA_DIR").unwrap_or_else(|_| DEFAULT_DIR.to_string()))
    };
    let auth_pass = if cli.password.is_empty() {
        env::var("PASSWORD").unwrap_or_default()
    } else {
        cli.password
    };

    let config = Arc::new(Config {
        data_dir: data_dir.clone(),
        bin,
        auth_user: "admin".to_string(),
        auth_pass,
    });

    let _ = std::fs::create_dir_all(&data_dir);

    let app = AppState {
        config,
        runtime: Arc::new(Mutex::new(RuntimeState {
            child: None,
            last_err: String::new(),
        })),
    };

    // 启动时若上次是 running 且 token 存在，则自动拉起隧道。
    if get_saved_state(&app.config.data_dir) == "running" {
        let token = get_stored_token(&app.config.data_dir);
        if !token.is_empty() {
            println!("saved state is 'running', auto-starting cloudflared tunnel...");
            let starter = app.clone();
            tokio::spawn(async move {
                match start_tunnel(&starter.config.bin, &token).await {
                    Ok(child) => {
                        let mut rt = starter.runtime.lock().await;
                        rt.child = Some(child);
                        rt.last_err.clear();
                    }
                    Err(e) => {
                        let mut rt = starter.runtime.lock().await;
                        rt.last_err = e;
                    }
                }
            });
        }
    }

    let router = Router::new()
        .route("/", get(index_handler).post(action_handler))
        .layer(middleware::from_fn_with_state(app.clone(), basic_auth))
        .with_state(app.clone());

    let addr = format!("0.0.0.0:{port}");
    let listener = TcpListener::bind(&addr)
        .await
        .unwrap_or_else(|e| panic!("failed to bind {addr}: {e}"));
    let auth_state = if app.config.auth_pass.is_empty() {
        "disabled"
    } else {
        "enabled"
    };
    println!(
        "cloudflared-web listening on :{port} | bin: {} | dir: {} | auth: {auth_state}",
        app.config.bin,
        app.config.data_dir.display()
    );
    axum::serve(listener, router).await.expect("server error");
}
