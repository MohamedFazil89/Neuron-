import threading
import time
import random
import os
import re
import json
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


# ================================================================
# SCAFFOLD PIPELINE
# New addition — only called by app.py's /cli/scaffold route.
# All code above this line is completely unchanged.
# ================================================================

_IGNORE_FOLDERS = {"node_modules", ".git", "venv", "__pycache__", "dist", ".next", "build"}
_IGNORE_EXTS    = {".lock", ".log", ".png", ".jpg", ".jpeg", ".svg", ".ico", ".woff", ".woff2"}

_FILE_BLOCK_RE = re.compile(
    r'<file path="([^"]+)">\s*(.*?)\s*</file>',
    re.DOTALL,
)


def _scan_project_for_context(path: str) -> dict:
    """Walks project directory and returns file tree + short snippets."""
    file_tree     = []
    file_snippets = {}

    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in _IGNORE_FOLDERS]
        for fname in files:
            if any(fname.endswith(ext) for ext in _IGNORE_EXTS):
                continue
            rel = os.path.relpath(os.path.join(root, fname), path)
            file_tree.append(rel)

            if len(file_snippets) < 40:
                try:
                    with open(os.path.join(root, fname), "r", errors="ignore") as f:
                        file_snippets[rel] = "".join(f.readlines()[:60])
                except Exception:
                    pass

    return {"file_tree": file_tree, "file_snippets": file_snippets}


# ------------------------------------------------------------------
# DUMMY AI  — simulates a real LLM response with a realistic delay.
# Swap _dummy_call_claude() for a real API call when you have a key.
# ------------------------------------------------------------------

def _detect_lang(file_tree: list[str]) -> str:
    """Guess primary language from file extensions in the tree."""
    exts = [os.path.splitext(f)[1].lower() for f in file_tree]
    for ext in [".ts", ".tsx", ".js", ".jsx", ".py", ".go", ".java", ".rs"]:
        if exts.count(ext) > 2:
            return ext
    return exts[0] if exts else ".ts"


def _dummy_call_plan(prompt: str, file_tree: list[str]) -> str:
    """
    Fake plan step: picks realistic file paths derived from the prompt
    and the actual project tree, waits a moment to feel like a network call.
    """
    time.sleep(random.uniform(0.8, 1.5))   # simulate latency

    lang = _detect_lang(file_tree)

    # Try to reuse real dirs from the scanned tree
    real_dirs = sorted({os.path.dirname(f) for f in file_tree if os.path.dirname(f)})
    best_dir  = next((d for d in real_dirs if "src" in d or "app" in d), real_dirs[0] if real_dirs else "src")

    # Derive a slug from the prompt (first 3 meaningful words)
    words   = re.sub(r"[^a-z0-9 ]", "", prompt.lower()).split()
    slug    = "_".join(w for w in words if len(w) > 2)[:30] or "feature"
    camel   = "".join(w.capitalize() for w in slug.split("_"))

    # Build 2–3 sensible paths
    paths = [
        f"{best_dir}/{slug}{lang}",
        f"{best_dir}/{camel}.test{lang}",
    ]

    # If the project already has a components/ or routes/ dir, add one there too
    for d in real_dirs:
        if "component" in d or "route" in d or "page" in d:
            paths.append(f"{d}/{camel}{lang}")
            break

    return json.dumps(paths[:3])


def _dummy_call_generate(prompt: str, files_to_touch: list[str], existing: str) -> str:
    """
    Fake generate step: produces plausible-looking boilerplate for each planned
    file, shaped by the prompt text and whatever existing code was passed in.
    Waits a moment to simulate generation time.
    """
    time.sleep(random.uniform(1.5, 2.5))   # simulate generation latency

    words  = re.sub(r"[^a-z0-9 ]", "", prompt.lower()).split()
    slug   = "_".join(w for w in words if len(w) > 2)[:30] or "feature"
    camel  = "".join(w.capitalize() for w in slug.split("_"))
    ts     = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    output = ""
    for rel_path in files_to_touch:
        ext = os.path.splitext(rel_path)[1].lower()

        if ext in (".ts", ".tsx", ".js", ".jsx"):
            is_test = ".test." in rel_path or ".spec." in rel_path
            if is_test:
                content = f"""\
// Auto-generated test  |  prompt: "{prompt}"
// Generated at: {ts}

import {{ {camel} }} from './{slug}';

describe('{camel}', () => {{
  it('should be defined', () => {{
    expect({camel}).toBeDefined();
  }});

  it('handles the happy path', () => {{
    const result = {camel}();
    expect(result).not.toBeNull();
  }});
}});
"""
            elif ext in (".tsx", ".jsx"):
                content = f"""\
// Auto-generated component  |  prompt: "{prompt}"
// Generated at: {ts}

import React, {{ useState, useEffect }} from 'react';

interface {camel}Props {{
  onSuccess?: () => void;
}}

export const {camel}: React.FC<{camel}Props> = ({{ onSuccess }}) => {{
  const [loading, setLoading] = useState(false);
  const [data, setData]       = useState<any>(null);

  useEffect(() => {{
    // TODO: wire up real data source
  }}, []);

  const handleAction = async () => {{
    setLoading(true);
    try {{
      // TODO: implement action for "{prompt}"
      onSuccess?.();
    }} finally {{
      setLoading(false);
    }}
  }};

  return (
    <div className="{slug}-container">
      <h2>{camel}</h2>
      {{loading && <span>Loading...</span>}}
      <button onClick={{handleAction}} disabled={{loading}}>
        Run
      </button>
    </div>
  );
}};

export default {camel};
"""
            else:
                content = f"""\
// Auto-generated module  |  prompt: "{prompt}"
// Generated at: {ts}

export interface {camel}Options {{
  // add options here
}}

export function {camel}(options?: {camel}Options) {{
  // TODO: implement "{prompt}"
  return {{
    success: true,
    data: null,
    options,
  }};
}}

export default {camel};
"""

        elif ext == ".py":
            content = f"""\
# Auto-generated module  |  prompt: "{prompt}"
# Generated at: {ts}

from typing import Optional, Any


def {slug}(options: Optional[dict] = None) -> Any:
    \"\"\"
    Generated for: {prompt}
    \"\"\"
    # TODO: implement logic
    return {{"success": True, "data": None}}


class {camel}:
    \"\"\"Handler class for: {prompt}\"\"\"

    def __init__(self):
        self._ready = False

    def run(self):
        self._ready = True
        return {slug}()
"""

        else:
            # Generic fallback for unknown extensions
            content = f"""\
// Auto-generated  |  prompt: "{prompt}"
// Generated at: {ts}
// File: {rel_path}

// TODO: implement "{prompt}"
"""

        output += f'<file path="{rel_path}">\n{content}\n</file>\n\n'

    return output


def run_scaffold(project_path: str, prompt: str, task: dict):
    """
    Real AI scaffold pipeline. Runs in a background thread (spawned by app.py).
    Mutates `task` dict in-place so /task/current endpoint streams live state.

    Pipeline:
      1. Scan  — walk project, build context for Claude
      2. Plan  — Claude returns JSON list of files to touch
      3. Generate — Claude returns full file contents in <file path="..."> blocks
      4. Write — files written to disk at correct paths inside project_path
      5. Done  — task + METRICS updated
    """
    start_time = time.time()

    def elapsed():
        return int(time.time() - start_time)

    def log(msg: str):
        task.setdefault("logs", []).append(msg)
        task["timeElapsed"] = elapsed()
        print(f"[scaffold] {msg}")

    try:
        # ── 1. Scan ──────────────────────────────────────────────────────
        task["status"] = "analyzing"
        log("🔍 Scanning project structure...")
        ctx = _scan_project_for_context(project_path)
        file_tree_str = "\n".join(ctx["file_tree"][:80])
        snippets_str  = "".join(
            f"\n\n--- {p} ---\n{s}"
            for p, s in list(ctx["file_snippets"].items())[:25]
        )
        task["progress"] = 10
        log(f"✅ Scanned {len(ctx['file_tree'])} files")

        # ── 2. Plan ──────────────────────────────────────────────────────
        log("🧠 Planning with AI...")
        plan_raw = _dummy_call_plan(prompt, ctx["file_tree"])
        log(f"📋 Plan received: {plan_raw[:200]}")

        try:
            clean = re.sub(r"```[a-z]*\n?", "", plan_raw).strip().rstrip("`").strip()
            files_to_touch = json.loads(clean)
            if not isinstance(files_to_touch, list):
                raise ValueError("expected list")
        except Exception as e:
            log(f"⚠️  Plan parse failed ({e}), using fallback")
            files_to_touch = ["src/features/generated_feature.ts"]

        task["filesTouched"] = files_to_touch
        task["progress"] = 30
        log(f"📝 Files planned: {files_to_touch}")

        # ── 3. Generate ──────────────────────────────────────────────────
        task["status"] = "implementing"
        log("⚙️  Generating code with AI...")

        # Pull in existing file content so Claude can do real edits
        existing = ""
        for fp in files_to_touch:
            full = os.path.join(project_path, fp)
            if os.path.exists(full):
                try:
                    with open(full, "r", errors="ignore") as f:
                        existing += f"\n\n--- EXISTING: {fp} ---\n{f.read()}"
                except Exception:
                    pass

        generated_raw = _dummy_call_generate(prompt, files_to_touch, existing)
        task["progress"] = 70
        log("✅ Code generation complete")

        # ── 4. Write ─────────────────────────────────────────────────────
        task["status"] = "patching"
        log("💾 Writing files to disk...")

        blocks = _FILE_BLOCK_RE.findall(generated_raw)

        if not blocks:
            log("⚠️  No <file> blocks found — fallback single-file write")
            fallback = files_to_touch[0] if files_to_touch else "src/generated_feature.ts"
            blocks = [(fallback, generated_raw)]

        written = []
        for rel_path, content in blocks:
            rel_path  = rel_path.lstrip("/")
            full_path = os.path.join(project_path, rel_path)
            dir_path  = os.path.dirname(full_path)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
            with open(full_path, "w") as f:
                f.write(content)
            written.append(rel_path)
            log(f"  📄 Written: {rel_path}")

        task["filesTouched"] = written
        task["progress"]     = 95

        # ── 5. Done ──────────────────────────────────────────────────────
        task["status"]      = "completed"
        task["progress"]    = 100
        task["timeElapsed"] = elapsed()

        # Reflect work in shared METRICS (same dict get_project() reads)
        METRICS["tokensUsed"] += len(generated_raw) // 4  # rough estimate
        METRICS["totalTasks"] += 1
        METRICS["totalTime"]  += elapsed()

        log(f"🎉 Scaffold complete — {len(written)} file(s) in {elapsed()}s")

    except Exception as e:
        task["status"]      = "error"
        task["timeElapsed"] = elapsed()
        task.setdefault("logs", []).append(f"❌ Error: {str(e)}")
        METRICS["failures"] += 1
        print(f"[scaffold] ERROR: {e}")


# ================================================================
# PROJECT CREATION — full runnable boilerplate generators
# Called by app.py's /cli/create route
# ================================================================

def _write(base: str, rel: str, content: str):
    """Helper: write a file, creating parent dirs as needed."""
    full = os.path.join(base, rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)
    return rel


def create_python_project(base: str, name: str, database: str) -> list:
    """Generates a full runnable Flask + SQLAlchemy boilerplate."""
    written = []
    db_url  = f"sqlite:///{name}.db" if database == "sqlite" else f"postgresql://user:password@localhost:5432/{name}"
    pg_dep  = "\npsycopg2-binary>=2.9.9" if database == "postgres" else ""
    # ── requirements.txt ─────────────────────────────────────────────────
    written.append(_write(base, "requirements.txt", f"""\
Flask==3.0.3
Flask-SQLAlchemy==3.1.1
Flask-CORS==4.0.1
Flask-Migrate==4.0.7
python-dotenv==1.0.1{pg_dep}
"""))

    # ── .env ─────────────────────────────────────────────────────────────
    written.append(_write(base, ".env", f"""\
FLASK_ENV=development
SECRET_KEY=change-me-in-production
DATABASE_URL={db_url}
"""))

    # ── .gitignore ────────────────────────────────────────────────────────
    written.append(_write(base, ".gitignore", """\
venv/
__pycache__/
*.pyc
.env
*.db
instance/
.flask_session/
"""))

    # ── app.py ────────────────────────────────────────────────────────────
    written.append(_write(base, "app.py", f"""\
import os
from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv

from extensions import db, migrate
from routes.users import users_bp
from routes.health import health_bp

load_dotenv()


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"]         = os.getenv("SECRET_KEY", "dev-secret")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "{db_url}")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    CORS(app)
    db.init_app(app)
    migrate.init_app(app, db)

    app.register_blueprint(health_bp)
    app.register_blueprint(users_bp, url_prefix="/api/users")

    return app


app = create_app()

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)
"""))

    # ── extensions.py ─────────────────────────────────────────────────────
    written.append(_write(base, "extensions.py", """\
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

db      = SQLAlchemy()
migrate = Migrate()
"""))

    # ── models/user.py ────────────────────────────────────────────────────
    written.append(_write(base, "models/__init__.py", ""))
    written.append(_write(base, "models/user.py", """\
from extensions import db
from datetime import datetime


class User(db.Model):
    __tablename__ = "users"

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(120), nullable=False)
    email      = db.Column(db.String(255), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id":         self.id,
            "name":       self.name,
            "email":      self.email,
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self):
        return f"<User {self.email}>"
"""))

    # ── routes/health.py ──────────────────────────────────────────────────
    written.append(_write(base, "routes/__init__.py", ""))
    written.append(_write(base, "routes/health.py", """\
from flask import Blueprint, jsonify

health_bp = Blueprint("health", __name__)


@health_bp.route("/health")
def health():
    return jsonify({"status": "ok"})
"""))

    # ── routes/users.py ───────────────────────────────────────────────────
    written.append(_write(base, "routes/users.py", """\
from flask import Blueprint, jsonify, request, abort
from extensions import db
from models.user import User

users_bp = Blueprint("users", __name__)


@users_bp.route("/", methods=["GET"])
def list_users():
    users = User.query.all()
    return jsonify([u.to_dict() for u in users])


@users_bp.route("/<int:user_id>", methods=["GET"])
def get_user(user_id):
    user = User.query.get_or_404(user_id)
    return jsonify(user.to_dict())


@users_bp.route("/", methods=["POST"])
def create_user():
    data = request.json or {}
    if not data.get("name") or not data.get("email"):
        abort(400, "name and email are required")

    user = User(name=data["name"], email=data["email"])
    db.session.add(user)
    db.session.commit()
    return jsonify(user.to_dict()), 201


@users_bp.route("/<int:user_id>", methods=["PUT"])
def update_user(user_id):
    user = User.query.get_or_404(user_id)
    data = request.json or {}
    if "name"  in data: user.name  = data["name"]
    if "email" in data: user.email = data["email"]
    db.session.commit()
    return jsonify(user.to_dict())


@users_bp.route("/<int:user_id>", methods=["DELETE"])
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    return jsonify({"deleted": True})
"""))

    # ── README.md ─────────────────────────────────────────────────────────
    written.append(_write(base, "README.md", f"""\
# {name}

Flask + SQLAlchemy backend generated by Neuron.

## Setup

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\\Scripts\\activate
pip install -r requirements.txt
python app.py
```

## Endpoints

| Method | Path              | Description     |
|--------|-------------------|-----------------|
| GET    | /health           | Health check    |
| GET    | /api/users/       | List users      |
| POST   | /api/users/       | Create user     |
| GET    | /api/users/:id    | Get user        |
| PUT    | /api/users/:id    | Update user     |
| DELETE | /api/users/:id    | Delete user     |

## Database
Using: **{database}**
URL: `{db_url}`
"""))

    return written


def create_nodejs_project(base: str, name: str, database: str) -> list:
    """Generates a full runnable Express + Prisma boilerplate."""
    written = []

    db_provider = "sqlite" if database == "sqlite" else "postgresql"
    db_url = f'file:./{name}.db' if database == "sqlite" else f"postgresql://user:password@localhost:5432/{name}"
    prisma_preview = 'previewFeatures = []' if database == "sqlite" else ''

    # ── package.json ─────────────────────────────────────────────────────
    written.append(_write(base, "package.json", f"""\
{{
  "name": "{name}",
  "version": "1.0.0",
  "description": "Express + Prisma backend generated by Neuron",
  "main": "src/index.js",
  "scripts": {{
    "dev": "nodemon src/index.js",
    "start": "node src/index.js",
    "db:migrate": "npx prisma migrate dev",
    "db:studio": "npx prisma studio"
  }},
  "dependencies": {{
    "@prisma/client": "^5.14.0",
    "cors": "^2.8.5",
    "dotenv": "^16.4.5",
    "express": "^4.19.2"
  }},
  "devDependencies": {{
    "nodemon": "^3.1.4",
    "prisma": "^5.14.0"
  }}
}}
"""))

    # ── .env ─────────────────────────────────────────────────────────────
    written.append(_write(base, ".env", f"""\
PORT=3000
NODE_ENV=development
DATABASE_URL="{db_url}"
"""))

    # ── .gitignore ────────────────────────────────────────────────────────
    written.append(_write(base, ".gitignore", """\
node_modules/
.env
*.db
dist/
"""))

    # ── prisma/schema.prisma ──────────────────────────────────────────────
    written.append(_write(base, "prisma/schema.prisma", f"""\
generator client {{
  provider = "prisma-client-js"
}}

datasource db {{
  provider = "{db_provider}"
  url      = env("DATABASE_URL")
}}

model User {{
  id        Int      @id @default(autoincrement())
  name      String
  email     String   @unique
  createdAt DateTime @default(now())
}}
"""))

    # ── src/index.js ──────────────────────────────────────────────────────
    written.append(_write(base, "src/index.js", """\
require('dotenv').config();
const express = require('express');
const cors    = require('cors');

const healthRouter = require('./routes/health');
const usersRouter  = require('./routes/users');

const app  = express();
const PORT = process.env.PORT || 3000;

app.use(cors());
app.use(express.json());

app.use('/health',    healthRouter);
app.use('/api/users', usersRouter);

// 404 handler
app.use((req, res) => {
  res.status(404).json({ error: 'Not found' });
});

// Error handler
app.use((err, req, res, next) => {
  console.error(err);
  res.status(500).json({ error: err.message || 'Internal server error' });
});

app.listen(PORT, () => {
  console.log(`🚀 Server running on http://localhost:${PORT}`);
});
"""))

    # ── src/db.js ─────────────────────────────────────────────────────────
    written.append(_write(base, "src/db.js", """\
const { PrismaClient } = require('@prisma/client');

const prisma = new PrismaClient();

module.exports = prisma;
"""))

    # ── src/routes/health.js ──────────────────────────────────────────────
    written.append(_write(base, "src/routes/health.js", """\
const router = require('express').Router();

router.get('/', (req, res) => {
  res.json({ status: 'ok' });
});

module.exports = router;
"""))

    # ── src/routes/users.js ───────────────────────────────────────────────
    written.append(_write(base, "src/routes/users.js", """\
const router = require('express').Router();
const prisma = require('../db');

// GET /api/users
router.get('/', async (req, res, next) => {
  try {
    const users = await prisma.user.findMany();
    res.json(users);
  } catch (e) { next(e); }
});

// GET /api/users/:id
router.get('/:id', async (req, res, next) => {
  try {
    const user = await prisma.user.findUnique({
      where: { id: Number(req.params.id) }
    });
    if (!user) return res.status(404).json({ error: 'User not found' });
    res.json(user);
  } catch (e) { next(e); }
});

// POST /api/users
router.post('/', async (req, res, next) => {
  try {
    const { name, email } = req.body;
    if (!name || !email)
      return res.status(400).json({ error: 'name and email are required' });
    const user = await prisma.user.create({ data: { name, email } });
    res.status(201).json(user);
  } catch (e) { next(e); }
});

// PUT /api/users/:id
router.put('/:id', async (req, res, next) => {
  try {
    const { name, email } = req.body;
    const user = await prisma.user.update({
      where: { id: Number(req.params.id) },
      data:  { ...(name && { name }), ...(email && { email }) }
    });
    res.json(user);
  } catch (e) { next(e); }
});

// DELETE /api/users/:id
router.delete('/:id', async (req, res, next) => {
  try {
    await prisma.user.delete({ where: { id: Number(req.params.id) } });
    res.json({ deleted: true });
  } catch (e) { next(e); }
});

module.exports = router;
"""))

    # ── README.md ─────────────────────────────────────────────────────────
    written.append(_write(base, "README.md", f"""\
# {name}

Express + Prisma backend generated by Neuron.

## Setup

```bash
npm install
npx prisma migrate dev --name init
npm run dev
```

## Endpoints

| Method | Path              | Description     |
|--------|-------------------|-----------------|
| GET    | /health           | Health check    |
| GET    | /api/users        | List users      |
| POST   | /api/users        | Create user     |
| GET    | /api/users/:id    | Get user        |
| PUT    | /api/users/:id    | Update user     |
| DELETE | /api/users/:id    | Delete user     |

## Database
Using: **{database}**
URL: `{db_url}`
"""))

    return written


def run_create_project(project_name: str, backend: str, database: str, cwd: str = None) -> dict:
    """
    Entry point called by app.py /cli/create.
    Creates the project folder inside `cwd` (the user's terminal directory),
    not the backend server's working directory.
    """
    base_dir = cwd if cwd and os.path.isdir(cwd) else os.getcwd()
    base     = os.path.join(base_dir, project_name)

    if os.path.exists(base):
        raise FileExistsError(f"Directory '{project_name}' already exists")

    os.makedirs(base)

    if backend == "python":
        files = create_python_project(base, project_name, database)
    elif backend == "nodejs":
        files = create_nodejs_project(base, project_name, database)
    else:
        raise ValueError(f"Unknown backend: {backend}")

    return {
        "path": base,
        "files_created": files,
    }