import threading
import time
import random
from datetime import datetime

# -----------------------------
# GLOBAL STATE (Mock Only)
# -----------------------------

PROJECT = {
    "id": "neuron-core",
    "name": "neuron-core",
    "workspaceMode": "safe",
    "localPath": "/home/dev/projects/neuron-core",
    "gitBranch": "feature/multi-agent",
    "coreStatus": "idle",
    "activeTask": None
}

METRICS = {
    "tokensUsed": 0,
    "estimatedCost": 0.0,
    "avgTaskTime": 0,
    "agentFailureRate": 0.0,
    "totalTasks": 0,
    "totalTime": 0,
    "failures": 0
}

TASK_STAGES = [
    "received",
    "analyzing",
    "implementing",
    "patching",
    "verifying",
    "completed"
]

engine_thread = None
engine_running = False


# -----------------------------
# REAL TIME TASK ENGINE
# -----------------------------

def task_engine():
    global engine_running

    task = PROJECT["activeTask"]
    if not task:
        return

    start_time = time.time()

    for stage in TASK_STAGES:
        if not engine_running:
            return

        task["status"] = stage
        task["timeElapsed"] = int(time.time() - start_time)

        # Simulate files touched
        task["filesTouched"].append(f"file_{random.randint(1,5)}.py")

        # Simulate agents involved
        task["agents"] = ["architect", "backend", "frontend"]

        # Simulate tokens
        tokens = random.randint(100, 300)
        METRICS["tokensUsed"] += tokens

        time.sleep(3)

    # Task Completed
    duration = int(time.time() - start_time)
    METRICS["totalTasks"] += 1
    METRICS["totalTime"] += duration

    PROJECT["coreStatus"] = "idle"
    engine_running = False


# -----------------------------
# API FUNCTIONS
# -----------------------------

def get_project():
    if METRICS["totalTasks"] > 0:
        METRICS["avgTaskTime"] = round(
            METRICS["totalTime"] / METRICS["totalTasks"], 2
        )

    METRICS["estimatedCost"] = round(METRICS["tokensUsed"] * 0.000002, 2)

    return {
        **PROJECT,
        "metrics": {
            "tokensUsed": METRICS["tokensUsed"],
            "estimatedCost": METRICS["estimatedCost"],
            "avgTaskTime": METRICS["avgTaskTime"],
            "agentFailureRate": METRICS["agentFailureRate"]
        }
    }


def start_task(name, description):
    global engine_thread, engine_running

    PROJECT["activeTask"] = {
        "id": f"task-{int(time.time())}",
        "name": name,
        "description": description,
        "status": "received",
        "triggerSource": "ui",
        "timeElapsed": 0,
        "filesTouched": [],
        "agents": []
    }

    PROJECT["coreStatus"] = "running"

    engine_running = True
    engine_thread = threading.Thread(target=task_engine)
    engine_thread.start()

    return PROJECT["activeTask"]


def pause_task():
    global engine_running
    engine_running = False
    PROJECT["coreStatus"] = "idle"
    return {"success": True}


def abort_task():
    global engine_running
    engine_running = False
    PROJECT["coreStatus"] = "error"
    METRICS["failures"] += 1
    return {"success": True}


def retry_task():
    task = PROJECT["activeTask"]
    if not task:
        return {"error": "No task"}

    return start_task(task["name"], task["description"])