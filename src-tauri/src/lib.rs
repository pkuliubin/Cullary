mod commands;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(commands::TaskRegistry::default())
        .invoke_handler(tauri::generate_handler![
            commands::get_runtime_diagnostics,
            commands::start_pipeline,
            commands::cancel_pipeline,
            commands::load_review_summary,
            commands::load_review_sets,
            commands::read_image_data_url,
            commands::append_decision,
            commands::load_decisions,
            commands::load_review_progress,
            commands::save_review_progress,
            commands::append_preference_event,
            commands::dry_run_stage,
            commands::execute_stage,
            commands::undo_stage,
        ])
        .run(tauri::generate_context!())
        .expect("error while running Cullary");
}
