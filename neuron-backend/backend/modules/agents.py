# modules/agents.py
from datetime import datetime

AGENTS = [
    {
        "id": "architect",
        "name": "Architect",
        "status": "idle",
        "response_time_sec": 0.0,
        "tokens_used": 0,
        "last_updated": None
    },
    {
        "id": "backend",
        "name": "Backend Agent",
        "status": "working",
        "response_time_sec": 1.4,
        "tokens_used": 11057,
        "last_updated": datetime.utcnow().isoformat()
    },
    {
        "id": "frontend",
        "name": "Frontend Agent",
        "status": "waiting",
        "response_time_sec": 0.8,
        "tokens_used": 2103,
        "last_updated": datetime.utcnow().isoformat()
    },
]