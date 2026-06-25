use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    collections::HashMap,
    env,
    fs::{self, OpenOptions},
    io::{BufRead, BufReader, Write},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::{Arc, Mutex},
    thread,
    time::{SystemTime, UNIX_EPOCH},
};
use tauri::{AppHandle, Emitter, Manager, State};

#[derive(Default)]
pub struct TaskRegistry {
    children: Arc<Mutex<HashMap<String, Arc<Mutex<Child>>>>>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct StagePlan {
    pub schema_version: String,
    pub plan_id: String,
    pub folder: String,
    pub destination_root: String,
    pub move_count: usize,
    pub target_delete_count: usize,
    pub target_keep_count: usize,
    pub move_to_delete_count: usize,
    pub restore_keep_count: usize,
    pub already_staged_count: usize,
    pub already_kept_count: usize,
    pub sidecar_count: usize,
    pub source_bytes: u64,
    pub sidecar_bytes: u64,
    pub total_bytes: u64,
    pub keep_source_bytes: u64,
    pub all_source_bytes: u64,
    pub operations: Vec<StageOperation>,
    pub issues: Vec<StageIssue>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct StageOperation {
    pub display_id: String,
    pub source: String,
    pub destination: String,
    pub kind: String,
    pub bytes: u64,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct StageIssue {
    pub display_id: Option<String>,
    pub issue: String,
    pub path: Option<String>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct StageResult {
    pub schema_version: String,
    pub operation_batch_id: String,
    pub moved_count: usize,
    pub failed_count: usize,
    pub failures: Vec<StageIssue>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct UndoResult {
    pub schema_version: String,
    pub operation_batch_id: String,
    pub restored_count: usize,
    pub failed_count: usize,
    pub failures: Vec<StageIssue>,
}

#[tauri::command]
pub fn start_pipeline(folder: String, app: AppHandle, registry: State<'_, TaskRegistry>) -> Result<Value, String> {
    let folder_path = require_dir(&folder)?;
    let repo_root = repo_root()?;
    let python_path = repo_root.join("src");
    let task_id = new_id("task");
    let python = if Path::new("/opt/anaconda3/envs/hippo/bin/python").exists() {
        "/opt/anaconda3/envs/hippo/bin/python".to_string()
    } else {
        "python3".to_string()
    };

    let mut child = Command::new(python)
        .current_dir(&repo_root)
        .env("PYTHONPATH", python_path.to_string_lossy().to_string())
        .arg("-m")
        .arg("cullary.pipeline")
        .arg(folder_path.to_string_lossy().to_string())
        .arg("--progress")
        .arg("jsonl")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|err| format!("failed to start pipeline: {err}"))?;

    if let Some(stdout) = child.stdout.take() {
        let app_for_stdout = app.clone();
        let task_for_stdout = task_id.clone();
        std::thread::spawn(move || {
            let reader = BufReader::new(stdout);
            for line in reader.lines().flatten() {
                let payload = parse_pipeline_line(&task_for_stdout, &line);
                let _ = app_for_stdout.emit("pipeline-progress", payload);
            }
        });
    }

    if let Some(stderr) = child.stderr.take() {
        let app_for_stderr = app.clone();
        let task_for_stderr = task_id.clone();
        std::thread::spawn(move || {
            let reader = BufReader::new(stderr);
            for line in reader.lines().flatten() {
                let _ = app_for_stderr.emit(
                    "pipeline-progress",
                    json!({"taskId": task_for_stderr, "type": "log", "stream": "stderr", "message": line}),
                );
            }
        });
    }

    let child = Arc::new(Mutex::new(child));
    registry
        .children
        .lock()
        .map_err(|_| "task registry lock poisoned".to_string())?
        .insert(task_id.clone(), Arc::clone(&child));

    watch_pipeline_exit(app, Arc::clone(&registry.children), task_id.clone(), child);

    Ok(json!({ "taskId": task_id }))
}

#[tauri::command]
pub fn cancel_pipeline(task_id: String, app: AppHandle, registry: State<'_, TaskRegistry>) -> Result<(), String> {
    let mut children = registry
        .children
        .lock()
        .map_err(|_| "task registry lock poisoned".to_string())?;
    if let Some(child) = children.remove(&task_id) {
        child
            .lock()
            .map_err(|_| "pipeline child lock poisoned".to_string())?
            .kill()
            .map_err(|err| format!("failed to cancel task: {err}"))?;
        let _ = app.emit("pipeline-cancelled", json!({ "taskId": task_id }));
    }
    Ok(())
}

fn watch_pipeline_exit(
    app: AppHandle,
    children: Arc<Mutex<HashMap<String, Arc<Mutex<Child>>>>>,
    task_id: String,
    child: Arc<Mutex<Child>>,
) {
    thread::spawn(move || loop {
        let status = {
            let mut child = match child.lock() {
                Ok(child) => child,
                Err(_) => {
                    let _ = app.emit("pipeline-failed", json!({ "taskId": task_id, "message": "pipeline child lock poisoned" }));
                    return;
                }
            };
            match child.try_wait() {
                Ok(status) => status,
                Err(err) => {
                    let removed = children.lock().ok().and_then(|mut map| map.remove(&task_id));
                    if removed.is_some() {
                        let _ = app.emit("pipeline-failed", json!({ "taskId": task_id, "message": format!("failed to wait for pipeline: {err}") }));
                    }
                    return;
                }
            }
        };

        if let Some(status) = status {
            let removed = children.lock().ok().and_then(|mut map| map.remove(&task_id));
            if removed.is_none() {
                return;
            }
            if status.success() {
                let _ = app.emit("pipeline-completed", json!({ "taskId": task_id, "exitCode": status.code() }));
            } else {
                let _ = app.emit("pipeline-failed", json!({
                    "taskId": task_id,
                    "exitCode": status.code(),
                    "message": "pipeline exited with a non-zero status"
                }));
            }
            return;
        }

        thread::sleep(std::time::Duration::from_millis(200));
    });
}

#[tauri::command]
pub fn load_review_summary(folder: String, app: AppHandle) -> Result<Value, String> {
    allow_review_asset_scope(&folder, &app)?;
    let path = cullary_dir(&folder)?.join("review_summary.json");
    read_json_file(&path)
}

#[tauri::command]
pub fn load_review_sets(folder: String, app: AppHandle) -> Result<Vec<Value>, String> {
    allow_review_asset_scope(&folder, &app)?;
    let root = require_dir(&folder)?;
    let path = cullary_dir_from_root(&root).join("review_sets.jsonl");
    let mut sets = read_jsonl_file(&path)?;
    enrich_source_sizes(&mut sets, &root);
    Ok(sets)
}

#[tauri::command]
pub fn read_image_data_url(folder: String, artifact_path: String) -> Result<String, String> {
    let root = require_dir(&folder)?;
    let path = resolve_artifact_path(&root, &artifact_path)?;
    if !path.is_file() {
        eprintln!("[Cullary image] missing file: {}", path.display());
        return Err(format!("image file does not exist: {}", path.display()));
    }
    let bytes = fs::read(&path).map_err(|err| format!("failed to read image {}: {err}", path.display()))?;
    let mime = match path.extension().and_then(|ext| ext.to_str()).unwrap_or_default().to_ascii_lowercase().as_str() {
        "jpg" | "jpeg" => "image/jpeg",
        "png" => "image/png",
        "webp" => "image/webp",
        "gif" => "image/gif",
        "svg" => "image/svg+xml",
        _ => "application/octet-stream",
    };
    eprintln!(
        "[Cullary image] data-url fallback ok path={} mime={} bytes={}",
        path.display(),
        mime,
        bytes.len()
    );
    Ok(format!("data:{mime};base64,{}", base64_encode(&bytes)))
}

#[tauri::command]
pub fn append_decision(folder: String, mut decision: Value) -> Result<(), String> {
    ensure_event_defaults(&mut decision, "photo_decision");
    append_jsonl(&cullary_dir(&folder)?.join("decisions.jsonl"), &decision)
}

#[tauri::command]
pub fn load_decisions(folder: String) -> Result<Vec<Value>, String> {
    let path = cullary_dir(&folder)?.join("decisions.jsonl");
    if !path.exists() {
        return Ok(Vec::new());
    }
    read_jsonl_file(&path)
}

#[tauri::command]
pub fn load_review_progress(folder: String) -> Result<Value, String> {
    let path = cullary_dir(&folder)?.join("review_progress.json");
    if !path.exists() {
        return Ok(default_review_progress());
    }
    let mut value = read_json_file(&path)?;
    ensure_progress_defaults(&mut value);
    Ok(value)
}

#[tauri::command]
pub fn save_review_progress(folder: String, mut progress: Value) -> Result<(), String> {
    ensure_progress_defaults(&mut progress);
    if let Some(obj) = progress.as_object_mut() {
        obj.insert("updated_at".into(), Value::Number((now_millis() as u64).into()));
    }
    write_json_file(&cullary_dir(&folder)?.join("review_progress.json"), &progress)
}

#[tauri::command]
pub fn append_preference_event(folder: String, mut event: Value) -> Result<(), String> {
    ensure_event_defaults(&mut event, "compare_decision");
    append_jsonl(&cullary_dir(&folder)?.join("preference_events.jsonl"), &event)
}

#[tauri::command]
pub fn dry_run_stage(folder: String) -> Result<StagePlan, String> {
    let root = require_dir(&folder)?;
    let cullary = cullary_dir_from_root(&root);
    let review_sets = read_jsonl_file(&cullary.join("review_sets.jsonl"))?;
    let decisions = read_jsonl_file(&cullary.join("decisions.jsonl")).unwrap_or_default();
    let keep_ids = latest_keep_decisions(&decisions, &review_sets);
    let photo_sources = collect_photo_sources(&review_sets);
    let destination_root = root.join(".to_delete");
    let mut operations = Vec::new();
    let mut issues = Vec::new();
    let mut target_delete_count = 0;
    let mut target_keep_count = 0;
    let mut move_to_delete_count = 0;
    let mut restore_keep_count = 0;
    let mut already_staged_count = 0;
    let mut already_kept_count = 0;

    for (display_id, source) in &photo_sources {
        if source.is_empty() {
            issues.push(StageIssue { display_id: Some(display_id.clone()), issue: "missing_source_path".into(), path: None });
            continue;
        }
        let source_path = PathBuf::from(source);
        let staged_path = destination_for(&root, &destination_root, &source_path);

        if keep_ids.contains(display_id) {
            target_keep_count += 1;
            if !source_path.exists() && staged_path.exists() {
                restore_keep_count += 1;
                operations.push(StageOperation {
                    display_id: display_id.clone(),
                    source: staged_path.to_string_lossy().to_string(),
                    destination: source_path.to_string_lossy().to_string(),
                    kind: "restore_source".into(),
                    bytes: file_size(&staged_path),
                });
            } else if source_path.exists() {
                already_kept_count += 1;
            }
            for ext in ["xmp", "XMP"] {
                let sidecar = source_path.with_extension(ext);
                let staged_sidecar = destination_for(&root, &destination_root, &sidecar);
                if !sidecar.exists() && staged_sidecar.exists() {
                    operations.push(StageOperation {
                        display_id: display_id.clone(),
                        source: staged_sidecar.to_string_lossy().to_string(),
                        destination: sidecar.to_string_lossy().to_string(),
                        kind: "restore_sidecar".into(),
                        bytes: file_size(&staged_sidecar),
                    });
                }
            }
            continue;
        }

        target_delete_count += 1;
        if !source_path.exists() {
            if !staged_path.exists() {
                issues.push(StageIssue { display_id: Some(display_id.clone()), issue: "source_missing".into(), path: Some(source.clone()) });
            } else {
                already_staged_count += 1;
            }
            continue;
        }
        move_to_delete_count += 1;
        operations.push(StageOperation {
            display_id: display_id.clone(),
            source: source_path.to_string_lossy().to_string(),
            destination: staged_path.to_string_lossy().to_string(),
            kind: "source".into(),
            bytes: file_size(&source_path),
        });
        for sidecar in sidecars_for(&source_path) {
            let destination = destination_for(&root, &destination_root, &sidecar);
            operations.push(StageOperation {
                display_id: display_id.clone(),
                source: sidecar.to_string_lossy().to_string(),
                destination: destination.to_string_lossy().to_string(),
                kind: "sidecar".into(),
                bytes: file_size(&sidecar),
            });
        }
    }

    let source_bytes = intended_source_bytes(&root, &destination_root, &photo_sources, |display_id| !keep_ids.contains(display_id));
    let sidecar_bytes = operations.iter().filter(|op| op.kind == "sidecar").map(|op| op.bytes).sum();
    let all_source_bytes = intended_source_bytes(&root, &destination_root, &photo_sources, |_| true);
    let keep_source_bytes = all_source_bytes - source_bytes;
    let plan = StagePlan {
        schema_version: "1.0".into(),
        plan_id: "stage_plan_current".into(),
        folder: root.to_string_lossy().to_string(),
        destination_root: destination_root.to_string_lossy().to_string(),
        move_count: target_delete_count,
        target_delete_count,
        target_keep_count,
        move_to_delete_count,
        restore_keep_count,
        already_staged_count,
        already_kept_count,
        sidecar_count: operations.iter().filter(|op| op.kind == "sidecar").count(),
        source_bytes,
        sidecar_bytes,
        total_bytes: source_bytes + sidecar_bytes,
        keep_source_bytes,
        all_source_bytes,
        operations,
        issues,
    };
    write_json_file(&stage_plan_path(&cullary, &plan.plan_id), &serde_json::to_value(&plan).unwrap())?;
    Ok(plan)
}

#[tauri::command]
pub fn execute_stage(folder: String, plan_id: String) -> Result<StageResult, String> {
    let root = require_dir(&folder)?;
    let cullary = cullary_dir_from_root(&root);
    let plan_path = stage_plan_path(&cullary, &plan_id);
    let plan: StagePlan = serde_json::from_value(read_json_file(&plan_path)?)
        .map_err(|err| format!("invalid stage plan: {err}"))?;
    let batch_id = new_id("stage_batch");
    let mut moved_count = 0;
    let mut failures = Vec::new();

    for op in &plan.operations {
        let source = PathBuf::from(&op.source);
        let destination = PathBuf::from(&op.destination);
        if let Some(parent) = destination.parent() {
            fs::create_dir_all(parent).map_err(|err| format!("failed to create destination dir: {err}"))?;
        }
        if destination.exists() {
            failures.push(StageIssue { display_id: Some(op.display_id.clone()), issue: "destination_exists".into(), path: Some(op.destination.clone()) });
            continue;
        }
        match fs::rename(&source, &destination) {
            Ok(_) => {
                moved_count += 1;
                let operation = if op.kind.starts_with("restore_") { "restore_from_delete_staging" } else { "move_to_delete_staging" };
                let log = json!({
                    "schema_version": "1.0",
                    "operation_batch_id": batch_id,
                    "operation": operation,
                    "bytes": op.bytes,
                    "display_id": op.display_id,
                    "kind": op.kind,
                    "source": op.source,
                    "destination": op.destination,
                    "status": "success",
                    "created_at": now_millis()
                });
                append_jsonl(&cullary.join("file_operations.jsonl"), &log)?;
            }
            Err(err) => failures.push(StageIssue { display_id: Some(op.display_id.clone()), issue: format!("move_failed: {err}"), path: Some(op.source.clone()) }),
        }
    }

    Ok(StageResult {
        schema_version: "1.0".into(),
        operation_batch_id: batch_id,
        moved_count,
        failed_count: failures.len(),
        failures,
    })
}

#[tauri::command]
pub fn undo_stage(folder: String, operation_batch_id: String) -> Result<UndoResult, String> {
    let cullary = cullary_dir(&folder)?;
    let logs = read_jsonl_file(&cullary.join("file_operations.jsonl")).unwrap_or_default();
    let mut restored_count = 0;
    let mut failures = Vec::new();

    for entry in logs.into_iter().rev() {
        if entry.get("operation_batch_id").and_then(Value::as_str) != Some(&operation_batch_id) {
            continue;
        }
        if entry.get("status").and_then(Value::as_str) != Some("success") {
            continue;
        }
        let source = entry.get("source").and_then(Value::as_str).unwrap_or_default();
        let destination = entry.get("destination").and_then(Value::as_str).unwrap_or_default();
        let display_id = entry.get("display_id").and_then(Value::as_str).map(str::to_string);
        let from = PathBuf::from(destination);
        let to = PathBuf::from(source);
        if let Some(parent) = to.parent() {
            fs::create_dir_all(parent).map_err(|err| format!("failed to create restore dir: {err}"))?;
        }
        match fs::rename(&from, &to) {
            Ok(_) => restored_count += 1,
            Err(err) => failures.push(StageIssue { display_id, issue: format!("restore_failed: {err}"), path: Some(destination.to_string()) }),
        }
    }

    Ok(UndoResult {
        schema_version: "1.0".into(),
        operation_batch_id,
        restored_count,
        failed_count: failures.len(),
        failures,
    })
}

fn allow_review_asset_scope(folder: &str, app: &AppHandle) -> Result<(), String> {
    let root = require_dir(folder)?;
    let cullary = cullary_dir_from_root(&root);
    app.asset_protocol_scope()
        .allow_directory(&cullary, true)
        .map_err(|err| format!("failed to allow asset scope {}: {err}", cullary.display()))?;
    eprintln!("[Cullary image] asset scope allowed dir={}", cullary.display());
    Ok(())
}

fn parse_pipeline_line(task_id: &str, line: &str) -> Value {
    match serde_json::from_str::<Value>(line) {
        Ok(mut value) => {
            if let Some(obj) = value.as_object_mut() {
                obj.insert("taskId".into(), Value::String(task_id.to_string()));
            }
            value
        }
        Err(_) => json!({"taskId": task_id, "type": "log", "message": line}),
    }
}

fn require_dir(folder: &str) -> Result<PathBuf, String> {
    let path = PathBuf::from(folder);
    if !path.is_dir() {
        return Err(format!("folder is not a directory: {folder}"));
    }
    path.canonicalize().map_err(|err| format!("failed to resolve folder: {err}"))
}

fn repo_root() -> Result<PathBuf, String> {
    if let Ok(path) = env::var("CULLARY_REPO_ROOT") {
        let root = PathBuf::from(path);
        if root.join("src/cullary").is_dir() {
            return Ok(root);
        }
    }
    let build_root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..");
    let build_root = build_root.canonicalize().unwrap_or(build_root);
    if build_root.join("src/cullary").is_dir() {
        return Ok(build_root);
    }
    let cwd = env::current_dir().map_err(|err| format!("failed to read current dir: {err}"))?;
    for candidate in [cwd.clone(), cwd.join(".."), cwd.join("../..")] {
        let root = candidate.canonicalize().unwrap_or(candidate);
        if root.join("src/cullary").is_dir() {
            return Ok(root);
        }
    }
    Err("failed to locate Cullary repo root; set CULLARY_REPO_ROOT".into())
}

fn resolve_artifact_path(root: &Path, artifact_path: &str) -> Result<PathBuf, String> {
    let path = if artifact_path.starts_with('/') {
        PathBuf::from(artifact_path)
    } else {
        root.join(artifact_path)
    };
    let canonical = path
        .canonicalize()
        .map_err(|err| format!("failed to resolve artifact path {}: {err}", path.display()))?;
    if !canonical.starts_with(root) {
        return Err(format!("artifact path is outside selected folder: {}", canonical.display()));
    }
    Ok(canonical)
}

fn cullary_dir(folder: &str) -> Result<PathBuf, String> {
    Ok(cullary_dir_from_root(&require_dir(folder)?))
}

fn cullary_dir_from_root(root: &Path) -> PathBuf {
    root.join(".cullary")
}

fn read_json_file(path: &Path) -> Result<Value, String> {
    let raw = fs::read_to_string(path).map_err(|err| format!("failed to read {}: {err}", path.display()))?;
    serde_json::from_str(&raw).map_err(|err| format!("invalid json {}: {err}", path.display()))
}

fn write_json_file(path: &Path, value: &Value) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|err| format!("failed to create {}: {err}", parent.display()))?;
    }
    fs::write(path, serde_json::to_vec_pretty(value).unwrap()).map_err(|err| format!("failed to write {}: {err}", path.display()))
}

fn read_jsonl_file(path: &Path) -> Result<Vec<Value>, String> {
    let raw = fs::read_to_string(path).map_err(|err| format!("failed to read {}: {err}", path.display()))?;
    let mut values = Vec::new();
    for (index, line) in raw.lines().enumerate() {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        values.push(serde_json::from_str(line).map_err(|err| format!("invalid jsonl {}:{}: {err}", path.display(), index + 1))?);
    }
    Ok(values)
}

fn append_jsonl(path: &Path, value: &Value) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|err| format!("failed to create {}: {err}", parent.display()))?;
    }
    let mut file = OpenOptions::new().create(true).append(true).open(path).map_err(|err| format!("failed to open {}: {err}", path.display()))?;
    writeln!(file, "{}", serde_json::to_string(value).unwrap()).map_err(|err| format!("failed to append {}: {err}", path.display()))
}

fn ensure_event_defaults(value: &mut Value, default_type: &str) {
    if let Some(obj) = value.as_object_mut() {
        obj.entry("schema_version").or_insert_with(|| Value::String("1.0".into()));
        obj.entry("event_id").or_insert_with(|| Value::String(new_id("event")));
        obj.entry("event_type").or_insert_with(|| Value::String(default_type.into()));
        obj.entry("created_at").or_insert_with(|| Value::Number((now_millis() as u64).into()));
    }
}

fn default_review_progress() -> Value {
    json!({
        "schema_version": "1.0",
        "completed_review_set_ids": [],
    })
}

fn ensure_progress_defaults(value: &mut Value) {
    if !value.is_object() {
        *value = default_review_progress();
        return;
    }
    if let Some(obj) = value.as_object_mut() {
        obj.entry("schema_version").or_insert_with(|| Value::String("1.0".into()));
        obj.entry("completed_review_set_ids").or_insert_with(|| Value::Array(Vec::new()));
    }
}

fn stage_plan_path(cullary: &Path, plan_id: &str) -> PathBuf {
    if plan_id == "stage_plan_current" {
        cullary.join("stage_plan.current.json")
    } else {
        cullary.join(format!("{plan_id}.json"))
    }
}

fn latest_keep_decisions(decisions: &[Value], review_sets: &[Value]) -> std::collections::HashSet<String> {
    let mut states: HashMap<String, String> = HashMap::new();
    for set in review_sets {
        if let Some(primary) = set.get("primary_keeper_id").and_then(Value::as_str) {
            states.insert(primary.to_string(), "user_keep".to_string());
        }
        if let Some(ids) = set.get("recommended_keep_ids").and_then(Value::as_array) {
            for id in ids.iter().filter_map(Value::as_str) {
                states.insert(id.to_string(), "user_keep".to_string());
            }
        }
        if let Some(photos) = set.get("photos").and_then(Value::as_array) {
            for photo in photos {
                let Some(display_id) = photo.get("display_id").and_then(Value::as_str) else { continue; };
                if photo.get("ui_initial_state").and_then(Value::as_str) == Some("recommended_keep") {
                    states.insert(display_id.to_string(), "user_keep".to_string());
                }
            }
        }
    }
    for decision in decisions {
        let Some(display_id) = decision.get("display_id").and_then(Value::as_str) else { continue; };
        let Some(user_state) = decision.get("user_state").and_then(Value::as_str) else { continue; };
        states.insert(display_id.to_string(), user_state.to_string());
    }
    states.into_iter().filter_map(|(display_id, state)| (state == "user_keep").then_some(display_id)).collect()
}


fn enrich_source_sizes(review_sets: &mut [Value], root: &Path) {
    let destination_root = root.join(".to_delete");
    for set in review_sets {
        let Some(photos) = set.get_mut("photos").and_then(Value::as_array_mut) else { continue; };
        for photo in photos {
            let source = photo
                .get("source_path")
                .and_then(Value::as_str)
                .or_else(|| photo.pointer("/source/path").and_then(Value::as_str))
                .map(str::to_string);
            let Some(source) = source else { continue; };
            let source_path = PathBuf::from(source);
            let staged_path = destination_for(root, &destination_root, &source_path);
            let bytes = file_size(&source_path).max(file_size(&staged_path));
            if let Some(obj) = photo.as_object_mut() {
                obj.insert("source_size_bytes".into(), Value::Number(bytes.into()));
            }
        }
    }
}

fn collect_photo_sources(review_sets: &[Value]) -> HashMap<String, String> {
    let mut sources = HashMap::new();
    for set in review_sets {
        let Some(photos) = set.get("photos").and_then(Value::as_array) else { continue; };
        for photo in photos {
            let Some(display_id) = photo.get("display_id").and_then(Value::as_str) else { continue; };
            let source = photo
                .get("source_path")
                .and_then(Value::as_str)
                .or_else(|| photo.pointer("/source/path").and_then(Value::as_str));
            if let Some(source) = source {
                sources.insert(display_id.to_string(), source.to_string());
            }
        }
    }
    sources
}

fn destination_for(root: &Path, destination_root: &Path, source: &Path) -> PathBuf {
    let relative = source.strip_prefix(root).unwrap_or_else(|_| source.file_name().map(Path::new).unwrap_or(source));
    destination_root.join(relative)
}

fn file_size(path: &Path) -> u64 {
    fs::metadata(path).map(|metadata| metadata.len()).unwrap_or(0)
}

fn intended_source_bytes<F>(root: &Path, destination_root: &Path, photo_sources: &HashMap<String, String>, include: F) -> u64
where
    F: Fn(&str) -> bool,
{
    photo_sources
        .iter()
        .filter(|(display_id, _)| include(display_id))
        .map(|(_, source)| {
            let source_path = PathBuf::from(source);
            let staged_path = destination_for(root, destination_root, &source_path);
            file_size(&source_path).max(file_size(&staged_path))
        })
        .sum()
}

fn sidecars_for(source: &Path) -> Vec<PathBuf> {
    let mut sidecars = Vec::new();
    let mut seen = std::collections::HashSet::new();
    for ext in ["xmp", "XMP"] {
        let candidate = source.with_extension(ext);
        if candidate.exists() {
            let key = candidate.to_string_lossy().to_lowercase();
            if seen.insert(key) {
                sidecars.push(candidate);
            }
        }
    }
    sidecars
}

fn new_id(prefix: &str) -> String {
    format!("{}_{}", prefix, now_millis())
}

fn now_millis() -> u128 {
    SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_millis()
}

fn base64_encode(bytes: &[u8]) -> String {
    const TABLE: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::with_capacity(bytes.len().div_ceil(3) * 4);
    for chunk in bytes.chunks(3) {
        let b0 = chunk[0];
        let b1 = *chunk.get(1).unwrap_or(&0);
        let b2 = *chunk.get(2).unwrap_or(&0);
        out.push(TABLE[(b0 >> 2) as usize] as char);
        out.push(TABLE[(((b0 & 0b0000_0011) << 4) | (b1 >> 4)) as usize] as char);
        if chunk.len() > 1 {
            out.push(TABLE[(((b1 & 0b0000_1111) << 2) | (b2 >> 6)) as usize] as char);
        } else {
            out.push('=');
        }
        if chunk.len() > 2 {
            out.push(TABLE[(b2 & 0b0011_1111) as usize] as char);
        } else {
            out.push('=');
        }
    }
    out
}
