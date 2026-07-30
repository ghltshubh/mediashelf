// MediaShelf desktop shell (P2).
//
// The whole app is the existing FastAPI server: this shell spawns it as a
// sidecar bound to 127.0.0.1:8000, waits for /api/health, then points a webview
// at it. Nothing about the product lives here — keeping the shell thin is what
// makes web, Docker and desktop the same app in different wrappers.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::sync::Mutex;
use std::time::Duration;

use tauri::{Manager, RunEvent, WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;

// Must match app/__main__.py's default. The OAuth redirect registered in the
// user's own Spotify/Google apps points at this exact port.
const SERVER_URL: &str = "http://127.0.0.1:8000";

/// Holds the sidecar so we can kill it on exit instead of orphaning a server.
#[derive(Default)]
struct Server(Mutex<Option<CommandChild>>);

/// Block until the server answers /api/health, or give up.
fn wait_for_health(timeout: Duration) -> bool {
    let deadline = std::time::Instant::now() + timeout;
    while std::time::Instant::now() < deadline {
        if health_ok() {
            return true;
        }
        std::thread::sleep(Duration::from_millis(250));
    }
    false
}

/// True once /api/health answers. A raw TCP+HTTP probe keeps the shell free of
/// an HTTP client dependency; the endpoint has no auth and returns {"ok": true}.
fn health_ok() -> bool {
    use std::io::{Read, Write};
    let Ok(mut stream) = std::net::TcpStream::connect(("127.0.0.1", 8000)) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_secs(2)));
    let req = "GET /api/health HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n";
    if stream.write_all(req.as_bytes()).is_err() {
        return false;
    }
    let mut buf = String::new();
    if stream.read_to_string(&mut buf).is_err() {
        return false;
    }
    buf.starts_with("HTTP/1.")
        && buf
            .lines()
            .next()
            .map(|line| line.contains(" 200"))
            .unwrap_or(false)
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .manage(Server::default())
        .setup(|app| {
            // Data lives in the OS app-data dir, so uninstalling the app doesn't
            // scatter SQLite files next to the binary.
            let data_dir = app.path().app_data_dir()?;
            std::fs::create_dir_all(&data_dir)?;

            let (mut rx, child) = app
                .shell()
                .sidecar("mediashelf-server")?
                .args([
                    "--data-dir",
                    &data_dir.to_string_lossy(),
                    // Belt and braces: we kill the child on exit, but a one-file
                    // PyInstaller binary is two processes, so the server also
                    // watches for us disappearing (force-quit, crash).
                    "--exit-with-parent",
                ])
                .spawn()?;
            app.state::<Server>().0.lock().unwrap().replace(child);

            // Forward the server's own logs to the shell's stdout, otherwise a
            // failing sidecar is invisible and undebuggable.
            tauri::async_runtime::spawn(async move {
                use tauri_plugin_shell::process::CommandEvent;
                while let Some(event) = rx.recv().await {
                    match event {
                        CommandEvent::Stdout(line) | CommandEvent::Stderr(line) => {
                            print!("[server] {}", String::from_utf8_lossy(&line));
                        }
                        CommandEvent::Terminated(payload) => {
                            eprintln!("[server] exited: {:?}", payload);
                        }
                        _ => {}
                    }
                }
            });

            // First boot seeds the catalog, so give it room before giving up.
            let ready = wait_for_health(Duration::from_secs(60));
            if !ready {
                eprintln!("mediashelf: server did not become healthy in time");
            }

            WebviewWindowBuilder::new(
                app,
                "main",
                WebviewUrl::External(SERVER_URL.parse().unwrap()),
            )
            .title("MediaShelf")
            .inner_size(1280.0, 860.0)
            .min_inner_size(720.0, 520.0)
            .build()?;

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building MediaShelf")
        .run(|app, event| {
            // Kill the sidecar on exit — an orphaned server would hold port 8000
            // and keep syncing in the background.
            if let RunEvent::ExitRequested { .. } | RunEvent::Exit = event {
                if let Some(child) = app.state::<Server>().0.lock().unwrap().take() {
                    let _ = child.kill();
                }
            }
        });
}
