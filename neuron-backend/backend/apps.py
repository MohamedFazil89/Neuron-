from flask import Flask, jsonify, abort, request
from collections import deque
from datetime import datetime
from flask_cors import CORS
import random
import os

import time
import threading


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
CORS(app, origins=["http://localhost:8080"])

# -----------------------------
# In-memory Agent Store
# -----------------------------
AGENTS = {
    "architect": {
        "id": "architect",
        "name": "Architect",
        "type": "architect",
        "status": "idle",
        "enabled": True,
        "currentAction": "Waiting for tasks",
        "lastResponseTime": 0.0,
        "tokenUsage": 0
    },
    "backend": {
        "id": "backend",
        "name": "Backend Agent",
        "type": "backend",
        "status": "idle",
        "enabled": False,
        "currentAction": "Stopped",
        "lastResponseTime": 0.0,
        "tokenUsage": 0
    },
    "frontend": {
        "id": "frontend",
        "name": "Frontend Agent",
        "type": "frontend",
        "status": "waiting",
        "enabled": False,
        "currentAction": "Awaiting API response",
        "lastResponseTime": 0.0,
        "tokenUsage": 0
    }
}

# -----------------------------
# Activity Feed
# -----------------------------
AGENT_ACTIVITY = deque(maxlen=100)

def log_activity(agent_id, message, event_type="status", severity="info"):
    AGENT_ACTIVITY.appendleft({
        "agent_id":  agent_id,
        "type":      event_type,
        "message":   message,
        "severity":  severity,
        "timestamp": datetime.utcnow().isoformat()
    })

# -----------------------------
# Simulated Metrics
# -----------------------------
def simulate_agent_metrics():
    for agent in AGENTS.values():
        if agent["enabled"] and agent["status"] == "working":
            agent["tokenUsage"] += random.randint(20, 100)
            agent["lastResponseTime"] = round(random.uniform(0.3, 1.8), 2)

@app.before_request
def before():
    if request.path.startswith("/agents"):
        simulate_agent_metrics()

# -----------------------------
# PROJECT STATE
# -----------------------------

# -----------------------------
# Health
# -----------------------------
@app.route("/health")
def health():
    return jsonify({"status": "ok"})

# -----------------------------
# Agents
# -----------------------------
@app.route("/agents", methods=["GET"])
def get_agents():
    return jsonify({
        "count": len(AGENTS),
        "agents": list(AGENTS.values())
    })

@app.route("/agents/<agent_id>", methods=["GET"])
def get_agent(agent_id):
    agent = AGENTS.get(agent_id)
    if not agent:
        abort(404)
    return jsonify(agent)

@app.route("/agents/<agent_id>/start", methods=["POST"])
def start_agent(agent_id):
    agent = AGENTS.get(agent_id)
    if not agent:
        abort(404)

    agent["enabled"] = True
    agent["status"] = "working"
    agent["currentAction"] = "Processing tasks"

    log_activity(agent_id, "Agent started")

    return jsonify({"success": True, "status": agent["status"]})

@app.route("/agents/<agent_id>/stop", methods=["POST"])
def stop_agent(agent_id):
    agent = AGENTS.get(agent_id)
    if not agent:
        abort(404)

    agent["enabled"] = False
    agent["status"] = "stopped"
    agent["currentAction"] = "Stopped"

    log_activity(agent_id, "Agent stopped")

    return jsonify({"success": True, "status": agent["status"]})

@app.route("/agents/<agent_id>/pause", methods=["POST"])
def pause_agent(agent_id):
    agent = AGENTS.get(agent_id)
    if not agent:
        abort(404)

    agent["status"] = "waiting"
    agent["currentAction"] = "Paused"

    log_activity(agent_id, "Agent paused")

    return jsonify({"success": True, "status": agent["status"]})

@app.route("/agents/activity", methods=["GET"])
def get_activity():
    limit = min(int(request.args.get("limit", 20)), 50)
    items = list(AGENT_ACTIVITY)[:limit]

    return jsonify({
        "items": items,
        "count": len(items)
    })

# -----------------------------
# Load Project (Path Input)
# -----------------------------
@app.route("/project/load", methods=["POST"])
def load_project():
    global current_project

    data = request.json
    path = data.get("path")

    if not path or not os.path.isdir(path):
        return jsonify({"error": "Invalid path"}), 400

    project_name = os.path.basename(path)

    current_project = {
        "id": "1",
        "name": project_name,
        "localPath": path,
        "gitBranch": "main",
        "workspaceMode": "safe",
        "coreStatus": "idle",
        "activeTask": None,
        "lastActiveAt": datetime.utcnow().isoformat()
    }

    print(f"✅ Project loaded: {project_name}")
    return jsonify({"success": True, "project": current_project})

# -----------------------------
# Get Project
# -----------------------------

current_project = None
current_task = None

@app.route("/project", methods=["GET"])
def get_project():
    print("PROJECT STATE:", current_project)
    return jsonify({
        "project": current_project,
        "metrics": {
            "tokensUsed": 0,
            "estimatedCost": 0,
            "avgTaskTime": 0,
            "agentFailureRate": 0
        }
    })

# -----------------------------
# Task Controls
# -----------------------------
@app.route("/task/start", methods=["POST"])
def task_start():
    body = request.json
    result = start_task(body["name"], body["description"])
    return jsonify(result)

@app.route("/task/pause", methods=["POST"])
def task_pause():
    return jsonify(pause_task())

@app.route("/task/abort", methods=["POST"])
def task_abort():
    return jsonify(abort_task())

@app.route("/task/retry", methods=["POST"])
def task_retry():
    return jsonify(retry_task())


# Cli codes
IGNORE_FOLDERS = {"node_modules", ".git", "venv", "__pycache__"}
def scan_project(path):
    total_files = 0
    total_folders = 0
    total_size = 0
    languages = {}

    for root, dirs, files in os.walk(path):
        # Remove ignored folders
        dirs[:] = [d for d in dirs if d not in IGNORE_FOLDERS]

        total_folders += len(dirs)

        for file in files:
            total_files += 1

            full_path = os.path.join(root, file)
            total_size += os.path.getsize(full_path)

            ext = file.split('.')[-1].lower()

            languages[ext] = languages.get(ext, 0) + 1

    return {
        "totalFiles": total_files,
        "totalFolders": total_folders,
        "totalSizeMB": round(total_size / (1024 * 1024), 2),
        "languages": languages
    }

def process_init_task(path, task):
    global current_project, current_task

    try:
        print("🚀 THREAD STARTED")

        start_time = time.time()

        task["status"] = "analyzing"
        time.sleep(1)

        total_files = 0
        files_list = []

        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in IGNORE_FOLDERS]
            for file in files:
                total_files += 1
                relative_path = os.path.relpath(os.path.join(root, file), path)
                files_list.append(relative_path)

                if total_files % 10 == 0:
                    task["filesTouched"] = files_list[:20]
                    task["timeElapsed"] = int(time.time() - start_time)
                    time.sleep(0.1)

        current_project = {
    "id": "1",
    "name": os.path.basename(path),
    "localPath": path,
    "gitBranch": "main",
    "workspaceMode": "safe",
    "coreStatus": "idle",
    "activeTask": task,
    "lastActiveAt": datetime.utcnow().isoformat(),
    "totalFiles": total_files
}

        task["status"] = "completed"
        task["timeElapsed"] = int(time.time() - start_time)

        current_project["activeTask"] = task

        print("✅ PROJECT SET:", current_project)

    except Exception as e:
        print("❌ THREAD CRASHED:", str(e))


@app.route("/cli/init", methods=["POST"])
def cli_init():
    global current_project, current_task

    data = request.get_json()
    path = data.get("path")
    print("🔥 BACKEND RECEIVED /cli/init")

    if not path or not os.path.exists(path):
        return jsonify({"error": "Invalid project path"}), 400

    # Create task
    current_task = {
        "id": int(time.time()),
        "name": "Project Initialization",
        "description": f"Initializing project at {path}",
        "status": "received",
        "triggerSource": "cli",
        "timeElapsed": 0,
        "filesTouched": [],
        "agents": ["scanner"],
    }

    # Start background processing
    thread = threading.Thread(target=process_init_task, args=(path, current_task))
    thread.start()

    return jsonify({"message": "Initialization started"})


# -----------------------------
# CLI scaffold  ← ONLY this function replaced
# -----------------------------

def _scaffold_wrapper(project_path, prompt, task):
    """
    Thin wrapper so the thread target stays in app.py.
    Calls run_scaffold() from neuron_feature, then syncs project state.
    """
    global current_project
    try:
        run_scaffold(project_path, prompt, task)
    finally:
        if current_project:
            current_project["coreStatus"] = (
                "idle" if task.get("status") == "completed" else "error"
            )
            current_project["activeTask"] = task


@app.route("/cli/scaffold", methods=["POST"])
def cli_scaffold():
    global current_project, current_task

    if not current_project:
        return jsonify({"error": "No active project"}), 400

    data = request.json
    prompt = data.get("prompt", "").strip()
    if not prompt:
        return jsonify({"error": "prompt is required"}), 400

    current_task = {
        "id": int(time.time()),
        "name": "Feature Scaffold",
        "description": prompt,
        "status": "queued",
        "progress": 0,
        "logs": [],
        "filesTouched": [],
        "timeElapsed": 0,
        "triggerSource": "cli",
        "agents": ["Architect", "Backend Agent", "Frontend Agent"],
        "startedAt": datetime.utcnow().isoformat()
    }

    current_project["coreStatus"] = "running"
    current_project["activeTask"] = current_task

    thread = threading.Thread(
        target=_scaffold_wrapper,
        args=(current_project["localPath"], prompt, current_task),
        daemon=True,
    )
    thread.start()

    return jsonify({"message": "Feature generation started", "task_id": current_task["id"]})


# Expose live task state for frontend polling
@app.route("/task/current", methods=["GET"])
def get_current_task():
    return jsonify({"task": current_task})


# -----------------------------
# Unified Logs endpoint
# Merges agent activity feed + current task logs into one stream
# -----------------------------
@app.route("/logs", methods=["GET"])
def get_logs():
    limit = min(int(request.args.get("limit", 100)), 200)
    unified = []

    # Agent activity events (start/stop/pause)
    for item in list(AGENT_ACTIVITY):
        unified.append({
            "id":        f"agent-{item['timestamp']}-{item['agent_id']}",
            "timestamp": item["timestamp"],
            "severity":  "info",
            "source":    item["agent_id"],
            "message":   item["message"],
            "type":      "agent",
        })

    # Current task step logs (scaffold / init progress)
    if current_task and current_task.get("logs"):
        for i, msg in enumerate(current_task["logs"]):
            severity = "error" if "error" in msg.lower() or "failed" in msg.lower() \
                else "warning" if "warn" in msg.lower() or "fallback" in msg.lower() \
                else "info"
            unified.append({
                "id":        f"task-{current_task['id']}-{i}",
                "timestamp": current_task.get("startedAt", datetime.utcnow().isoformat()),
                "severity":  severity,
                "source":    "scaffold",
                "message":   msg,
                "type":      "task",
            })

    # Sort newest first, cap at limit
    unified.sort(key=lambda x: x["timestamp"], reverse=True)
    return jsonify({"logs": unified[:limit], "count": len(unified)})




@app.route("/cli/create", methods=["POST"])
def cli_create():
    global current_project, current_task

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
        print(f"[create] cwd='{cwd}' -> will create at: {os.path.join(cwd or '.', project_name)}")
        result = run_create_project(project_name, backend, database, cwd)

        # Auto-register as active project so dashboard updates immediately
        current_project = {
            "id": "1",
            "name": project_name,
            "localPath": result["path"],
            "gitBranch": "main",
            "workspaceMode": "safe",
            "coreStatus": "idle",
            "activeTask": {
                "id": int(time.time()),
                "name": "Project Created",
                "description": f"{backend} + {database} boilerplate generated by Neuron",
                "status": "completed",
                "triggerSource": "cli",
                "timeElapsed": 0,
                "filesTouched": result["files_created"],
                "agents": ["scaffold"],
                "startedAt": datetime.utcnow().isoformat(),
            },
            "lastActiveAt": datetime.utcnow().isoformat(),
            "totalFiles": len(result["files_created"]),
        }

        print(f"[create] Project registered in dashboard: {project_name}")
        return jsonify(result)

    except FileExistsError as e:
        return jsonify({"error": str(e)}), 409
    except Exception as e:
        print(f"[create] failed: {e}")
        return jsonify({"error": str(e)}), 500


# -----------------------------
# Entry
# -----------------------------

if __name__ == "__main__":
    app.run(debug=False, use_reloader=False, threaded=True)