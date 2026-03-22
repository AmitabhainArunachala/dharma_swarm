#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::path::PathBuf;
use std::process::Command;

use tauri::{WebviewUrl, WebviewWindowBuilder};

const DASHBOARD_URL: &str = "http://127.0.0.1:3420/dashboard";

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap_or_else(|_| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../.."))
}

fn start_runtime() {
    let script = repo_root().join("scripts/dashboard_ctl.sh");
    let _ = Command::new("bash").arg(script).arg("start").status();
}

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            start_runtime();

            let url = DASHBOARD_URL
                .parse()
                .expect("dashboard URL should be a valid URL");

            WebviewWindowBuilder::new(app, "main", WebviewUrl::External(url))
                .title("DHARMA COMMAND")
                .inner_size(1600.0, 1040.0)
                .min_inner_size(1280.0, 800.0)
                .resizable(true)
                .build()?;

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running dharma desktop shell");
}
