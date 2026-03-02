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
    retry_task
)

app = Flask(__name__)
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

def log_activity(agent_id, message, event_type="status"):
    AGENT_ACTIVITY.appendleft({
        "agent_id": agent_id,
        "type": event_type,
        "message": message,
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



def process_feature_task(path, prompt):
    global current_project, current_task

    try:
        start_time = time.time()

        steps = [
            "Analyzing requirement...",
            "Planning file structure...",
            "Generating backend logic...",
            "Generating frontend UI...",
            "Writing files...",
            "Finalizing..."
        ]

        for i, step in enumerate(steps):
            time.sleep(1)

            current_task["logs"].append(step)
            current_task["progress"] = int((i + 1) / len(steps) * 100)
            current_task["timeElapsed"] = int(time.time() - start_time)

        # MOCK intelligent placement
        backend_dir = os.path.join(path, "src", "api")
        os.makedirs(backend_dir, exist_ok=True)

        file_path = os.path.join(backend_dir, "auth.ts")

        with open(file_path, "w") as f:
            f.write(f"// Generated feature\n// Prompt: {prompt}")

        current_task["filesTouched"].append("src/api/auth.ts")
        current_task["status"] = "completed"
        current_project["coreStatus"] = "idle"

    except Exception as e:
        current_task["status"] = "error"
        current_project["coreStatus"] = "error"
        print("Error:", e)

@app.route("/cli/scaffold", methods=["POST"])
def cli_scaffold():
    global current_project, current_task

    if not current_project:
        return jsonify({"error": "No active project"}), 400

    data = request.json
    prompt = data.get("prompt")

    current_task = {
        "id": int(time.time()),
        "name": "Feature Scaffold",
        "description": prompt,
        "status": "running",
        "progress": 0,
        "logs": [],
        "filesTouched": [],
        "timeElapsed": 0,
        "triggerSource": "cli",
        "agents": ["Backend Agent", "Frontend Agent"],
        "startedAt": datetime.utcnow().isoformat()
    }

    current_project["coreStatus"] = "running"
    current_project["activeTask"] = current_task

    thread = threading.Thread(
        target=process_feature_task,
        args=(current_project["localPath"], prompt)
    )
    thread.start()

    return jsonify({"message": "Feature generation started"})


# -----------------------------
# Entry
# -----------------------------

if __name__ == "__main__":
    app.run(debug=False, use_reloader=False, threaded=True)