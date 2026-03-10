from flask import Flask, jsonify, abort, request, g
from collections import deque
from datetime import datetime
from flask_cors import CORS
import random
import os
import time
import threading

from auth import require_auth, current_user_id

from neuron_feature import (
    get_project as neuron_get_project,
    start_task,
    pause_task,
    abort_task,
    retry_task,
    run_scaffold,
    run_create_project,
)

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False

# ── CORS ──────────────────────────────────────────────────────────────────────
# We use Bearer token auth (not cookies), so credentials=False is fine.
# Wildcard origin lets any localhost port work — Vite defaults to 5173,
# but projects may also use 3000, 4173, 8080, etc.
# NOTE: supports_credentials MUST be False when origins="*".
CORS(
    app,
    origins="*",
    supports_credentials=False,
    allow_headers=["Content-Type", "Authorization"],
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
)

# ─────────────────────────────────────────────────────────────────────────────
# In-memory Agent Store  (per-user)
# ─────────────────────────────────────────────────────────────────────────────
_USER_AGENTS: dict[str, dict] = {}

def _default_agents() -> dict:
    return {
        "architect": {
            "id": "architect", "name": "Architect", "type": "architect",
            "status": "idle", "enabled": True,
            "currentAction": "Waiting for tasks",
            "lastResponseTime": 0.0, "tokenUsage": 0,
        },
        "backend": {
            "id": "backend", "name": "Backend Agent", "type": "backend",
            "status": "idle", "enabled": False,
            "currentAction": "Stopped",
            "lastResponseTime": 0.0, "tokenUsage": 0,
        },
        "frontend": {
            "id": "frontend", "name": "Frontend Agent", "type": "frontend",
            "status": "waiting", "enabled": False,
            "currentAction": "Awaiting API response",
            "lastResponseTime": 0.0, "tokenUsage": 0,
        },
    }

def get_agents_for(user_id: str) -> dict:
    if user_id not in _USER_AGENTS:
        _USER_AGENTS[user_id] = _default_agents()
    return _USER_AGENTS[user_id]


# ─────────────────────────────────────────────────────────────────────────────
# Activity Feed  (per-user)
# ─────────────────────────────────────────────────────────────────────────────
_USER_ACTIVITY: dict[str, deque] = {}

def get_activity_for(user_id: str) -> deque:
    if user_id not in _USER_ACTIVITY:
        _USER_ACTIVITY[user_id] = deque(maxlen=100)
    return _USER_ACTIVITY[user_id]

def log_activity(user_id: str, agent_id: str, message: str, event_type="status", severity="info"):
    get_activity_for(user_id).appendleft({
        "agent_id":  agent_id,
        "type":      event_type,
        "message":   message,
        "severity":  severity,
        "timestamp": datetime.utcnow().isoformat(),
    })


# ─────────────────────────────────────────────────────────────────────────────
# Project / Task state  (per-user, thread-safe)
# ─────────────────────────────────────────────────────────────────────────────
_USER_STATE: dict[str, dict] = {}
_STATE_LOCK = threading.Lock()

def get_state_for(user_id: str) -> dict:
    if user_id not in _USER_STATE:
        _USER_STATE[user_id] = {"project": None, "task": None}
    return _USER_STATE[user_id]

def set_project(user_id: str, project):
    with _STATE_LOCK:
        get_state_for(user_id)["project"] = project

def set_task(user_id: str, task):
    with _STATE_LOCK:
        get_state_for(user_id)["task"] = task

def get_project_for(user_id: str):
    with _STATE_LOCK:
        return get_state_for(user_id).get("project")

def get_task_for(user_id: str):
    with _STATE_LOCK:
        return get_state_for(user_id).get("task")


# ─────────────────────────────────────────────────────────────────────────────
# Simulated Metrics
# ─────────────────────────────────────────────────────────────────────────────
def simulate_agent_metrics(user_id: str):
    for agent in get_agents_for(user_id).values():
        if agent["enabled"] and agent["status"] == "working":
            agent["tokenUsage"]      += random.randint(20, 100)
            agent["lastResponseTime"] = round(random.uniform(0.3, 1.8), 2)

@app.before_request
def before():
    if request.method == "OPTIONS":
        return  # CORS preflight — handled by flask-cors
    if request.path.startswith("/agents") and request.method == "GET":
        uid = _peek_user_id()
        if uid:
            simulate_agent_metrics(uid)

def _peek_user_id() -> str | None:
    try:
        from auth import verify_token
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None
        payload = verify_token(auth_header[len("Bearer "):])
        return payload.get("sub")
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Health  (public)
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/health")
def health():
    return jsonify({"status": "ok"})


# ─────────────────────────────────────────────────────────────────────────────
# Agents
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/agents", methods=["GET"])
@require_auth
def get_agents():
    uid    = current_user_id()
    agents = get_agents_for(uid)
    return jsonify({"count": len(agents), "agents": list(agents.values())})

@app.route("/agents/<agent_id>", methods=["GET"])
@require_auth
def get_agent(agent_id):
    uid   = current_user_id()
    agent = get_agents_for(uid).get(agent_id)
    if not agent:
        abort(404)
    return jsonify(agent)

@app.route("/agents/<agent_id>/start", methods=["POST"])
@require_auth
def start_agent(agent_id):
    uid   = current_user_id()
    agent = get_agents_for(uid).get(agent_id)
    if not agent:
        abort(404)
    agent["enabled"]       = True
    agent["status"]        = "working"
    agent["currentAction"] = "Processing tasks"
    log_activity(uid, agent_id, "Agent started")
    return jsonify({"success": True, "status": agent["status"]})

@app.route("/agents/<agent_id>/stop", methods=["POST"])
@require_auth
def stop_agent(agent_id):
    uid   = current_user_id()
    agent = get_agents_for(uid).get(agent_id)
    if not agent:
        abort(404)
    agent["enabled"]       = False
    agent["status"]        = "stopped"
    agent["currentAction"] = "Stopped"
    log_activity(uid, agent_id, "Agent stopped")
    return jsonify({"success": True, "status": agent["status"]})

@app.route("/agents/<agent_id>/pause", methods=["POST"])
@require_auth
def pause_agent(agent_id):
    uid   = current_user_id()
    agent = get_agents_for(uid).get(agent_id)
    if not agent:
        abort(404)
    agent["status"]        = "waiting"
    agent["currentAction"] = "Paused"
    log_activity(uid, agent_id, "Agent paused")
    return jsonify({"success": True, "status": agent["status"]})

@app.route("/agents/activity", methods=["GET"])
@require_auth
def get_activity():
    uid   = current_user_id()
    limit = min(int(request.args.get("limit", 20)), 50)
    items = list(get_activity_for(uid))[:limit]
    return jsonify({"items": items, "count": len(items)})


# ─────────────────────────────────────────────────────────────────────────────
# Project
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/project/load", methods=["POST"])
@require_auth
def load_project():
    uid  = current_user_id()
    data = request.json or {}
    path = data.get("path")

    if not path or not os.path.isdir(path):
        return jsonify({"error": "Invalid path"}), 400

    project_name = os.path.basename(path)
    project = {
        "id":            "1",
        "name":          project_name,
        "localPath":     path,
        "gitBranch":     "main",
        "workspaceMode": "safe",
        "coreStatus":    "idle",
        "activeTask":    None,
        "lastActiveAt":  datetime.utcnow().isoformat(),
    }
    set_project(uid, project)
    print(f"✅ [{uid[:8]}] Project loaded: {project_name}")
    return jsonify({"success": True, "project": project})

@app.route("/project", methods=["GET"])
@require_auth
def get_project():
    uid     = current_user_id()
    project = get_project_for(uid)
    return jsonify({
        "project": project,
        "metrics": {
            "tokensUsed": 0, "estimatedCost": 0,
            "avgTaskTime": 0, "agentFailureRate": 0,
        },
    })


# ─────────────────────────────────────────────────────────────────────────────
# Task Controls
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/task/start", methods=["POST"])
@require_auth
def task_start():
    body   = request.json or {}
    result = start_task(body.get("name", ""), body.get("description", ""))
    return jsonify(result)

@app.route("/task/pause", methods=["POST"])
@require_auth
def task_pause():
    return jsonify(pause_task())

@app.route("/task/abort", methods=["POST"])
@require_auth
def task_abort():
    return jsonify(abort_task())

@app.route("/task/retry", methods=["POST"])
@require_auth
def task_retry():
    return jsonify(retry_task())

@app.route("/task/current", methods=["GET"])
@require_auth
def get_current_task():
    uid = current_user_id()
    return jsonify({"task": get_task_for(uid)})


# ─────────────────────────────────────────────────────────────────────────────
# CLI — init
# ─────────────────────────────────────────────────────────────────────────────
IGNORE_FOLDERS = {"node_modules", ".git", "venv", "__pycache__"}

def process_init_task(user_id: str, path: str, task: dict):
    try:
        print(f"🚀 [{user_id[:8]}] THREAD STARTED")
        start_time     = time.time()
        task["status"] = "analyzing"
        time.sleep(1)

        total_files = 0
        files_list  = []

        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in IGNORE_FOLDERS]
            for file in files:
                total_files += 1
                relative_path = os.path.relpath(os.path.join(root, file), path)
                files_list.append(relative_path)
                if total_files % 10 == 0:
                    task["filesTouched"] = files_list[:20]
                    task["timeElapsed"]  = int(time.time() - start_time)
                    time.sleep(0.1)

        task["status"]       = "completed"
        task["timeElapsed"]  = int(time.time() - start_time)
        task["filesTouched"] = files_list[:20]

        project = {
            "id":            "1",
            "name":          os.path.basename(path),
            "localPath":     path,
            "gitBranch":     "main",
            "workspaceMode": "safe",
            "coreStatus":    "idle",
            "activeTask":    task,
            "lastActiveAt":  datetime.utcnow().isoformat(),
            "totalFiles":    total_files,
        }

        set_project(user_id, project)
        set_task(user_id, task)
        print(f"✅ [{user_id[:8]}] PROJECT SET: {project['name']} ({total_files} files)")

    except Exception as e:
        print(f"❌ [{user_id[:8]}] THREAD CRASHED: {e}")
        import traceback; traceback.print_exc()

@app.route("/cli/init", methods=["POST"])
@require_auth
def cli_init():
    uid  = current_user_id()
    data = request.get_json() or {}
    path = data.get("path")
    print(f"🔥 [{uid[:8]}] BACKEND RECEIVED /cli/init path={path}")

    if not path or not os.path.exists(path):
        return jsonify({"error": "Invalid project path"}), 400

    task = {
        "id":            int(time.time()),
        "name":          "Project Initialization",
        "description":   f"Initializing project at {path}",
        "status":        "received",
        "triggerSource": "cli",
        "timeElapsed":   0,
        "filesTouched":  [],
        "agents":        ["scanner"],
    }
    set_task(uid, task)

    thread = threading.Thread(
        target=process_init_task,
        args=(uid, path, task),
        daemon=True,
    )
    thread.start()

    return jsonify({"message": "Initialization started"})


# ─────────────────────────────────────────────────────────────────────────────
# CLI — scaffold
# ─────────────────────────────────────────────────────────────────────────────
def _scaffold_wrapper(user_id: str, project_path: str, prompt: str, task: dict):
    try:
        run_scaffold(project_path, prompt, task)
    finally:
        project = get_project_for(user_id)
        if project:
            project["coreStatus"] = (
                "idle" if task.get("status") == "completed" else "error"
            )
            project["activeTask"] = task
            set_project(user_id, project)
        set_task(user_id, task)

@app.route("/cli/scaffold", methods=["POST"])
@require_auth
def cli_scaffold():
    uid     = current_user_id()
    project = get_project_for(uid)

    if not project:
        return jsonify({"error": "No active project"}), 400

    data   = request.json or {}
    prompt = data.get("prompt", "").strip()
    if not prompt:
        return jsonify({"error": "prompt is required"}), 400

    task = {
        "id":            int(time.time()),
        "name":          "Feature Scaffold",
        "description":   prompt,
        "status":        "queued",
        "progress":      0,
        "logs":          [],
        "filesTouched":  [],
        "timeElapsed":   0,
        "triggerSource": "cli",
        "agents":        ["Architect", "Backend Agent", "Frontend Agent"],
        "startedAt":     datetime.utcnow().isoformat(),
    }
    set_task(uid, task)

    project["coreStatus"] = "running"
    project["activeTask"] = task
    set_project(uid, project)

    thread = threading.Thread(
        target=_scaffold_wrapper,
        args=(uid, project["localPath"], prompt, task),
        daemon=True,
    )
    thread.start()

    return jsonify({"message": "Feature generation started", "task_id": task["id"]})


# ─────────────────────────────────────────────────────────────────────────────
# CLI — create project
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/cli/create", methods=["POST"])
@require_auth
def cli_create():
    uid          = current_user_id()
    data         = request.json or {}
    project_name = data.get("project_name", "").strip()
    backend      = data.get("backend", "").strip()
    database     = data.get("database", "sqlite").strip()
    cwd          = data.get("cwd", "").strip()

    if not project_name:
        return jsonify({"error": "project_name is required"}), 400
    if backend not in ("python", "nodejs"):
        return jsonify({"error": "backend must be 'python' or 'nodejs'"}), 400

    try:
        result = run_create_project(project_name, backend, database, cwd)
        project = {
            "id":            "1",
            "name":          project_name,
            "localPath":     result["path"],
            "gitBranch":     "main",
            "workspaceMode": "safe",
            "coreStatus":    "idle",
            "activeTask": {
                "id":            int(time.time()),
                "name":          "Project Created",
                "description":   f"{backend} + {database} boilerplate generated by Neuron",
                "status":        "completed",
                "triggerSource": "cli",
                "timeElapsed":   0,
                "filesTouched":  result["files_created"],
                "agents":        ["scaffold"],
                "startedAt":     datetime.utcnow().isoformat(),
            },
            "lastActiveAt": datetime.utcnow().isoformat(),
            "totalFiles":   len(result["files_created"]),
        }
        set_project(uid, project)
        return jsonify(result)
    except FileExistsError as e:
        return jsonify({"error": str(e)}), 409
    except Exception as e:
        print(f"[create] [{uid[:8]}] failed: {e}")
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# Logs
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/logs", methods=["GET"])
@require_auth
def get_logs():
    uid     = current_user_id()
    limit   = min(int(request.args.get("limit", 100)), 200)
    unified = []

    for item in list(get_activity_for(uid)):
        unified.append({
            "id":        f"agent-{item['timestamp']}-{item['agent_id']}",
            "timestamp": item["timestamp"],
            "severity":  "info",
            "source":    item["agent_id"],
            "message":   item["message"],
            "type":      "agent",
        })

    task = get_task_for(uid)
    if task and task.get("logs"):
        for i, msg in enumerate(task["logs"]):
            severity = (
                "error"   if "error"  in msg.lower() or "failed"   in msg.lower() else
                "warning" if "warn"   in msg.lower() or "fallback" in msg.lower() else
                "info"
            )
            unified.append({
                "id":        f"task-{task['id']}-{i}",
                "timestamp": task.get("startedAt", datetime.utcnow().isoformat()),
                "severity":  severity,
                "source":    "scaffold",
                "message":   msg,
                "type":      "task",
            })

    unified.sort(key=lambda x: x["timestamp"], reverse=True)
    return jsonify({"logs": unified[:limit], "count": len(unified)})


# ─────────────────────────────────────────────────────────────────────────────
# Entry
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=False, use_reloader=False, threaded=True)