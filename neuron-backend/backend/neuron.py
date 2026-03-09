import sys
import os
import json
import getpass
import requests
from datetime import datetime, timezone

BACKEND_URL = "http://127.0.0.1:5000"

# ── Credential store ──────────────────────────────────────────────────────────
# ~/.neuron/credentials  (like ~/.gitconfig)

NEURON_DIR = os.path.join(os.path.expanduser("~"), ".neuron")
CREDS_FILE = os.path.join(NEURON_DIR, "credentials")


def _save_credentials(email: str, access_token: str, refresh_token: str, expires_at: int):
    os.makedirs(NEURON_DIR, exist_ok=True)
    data = {
        "email":         email,
        "access_token":  access_token,
        "refresh_token": refresh_token,
        "expires_at":    expires_at,
    }
    with open(CREDS_FILE, "w") as f:
        json.dump(data, f, indent=2)
    try:
        os.chmod(CREDS_FILE, 0o600)
    except Exception:
        pass


def _load_credentials() -> dict | None:
    if not os.path.exists(CREDS_FILE):
        return None
    try:
        with open(CREDS_FILE) as f:
            return json.load(f)
    except Exception:
        return None


def _clear_credentials():
    if os.path.exists(CREDS_FILE):
        os.remove(CREDS_FILE)


# ── Read Supabase config from backend .env ────────────────────────────────────

def _load_supabase_config() -> tuple[str, str]:
    supabase_url  = os.getenv("SUPABASE_URL", "").rstrip("/")
    supabase_anon = os.getenv("SUPABASE_ANON_KEY", "")

    if not supabase_url or not supabase_anon:
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("SUPABASE_URL="):
                        supabase_url = line.split("=", 1)[1].strip().rstrip("/")
                    elif line.startswith("SUPABASE_ANON_KEY="):
                        supabase_anon = line.split("=", 1)[1].strip()

    if not supabase_url or not supabase_anon:
        print("\n  ❌  SUPABASE_URL and SUPABASE_ANON_KEY are not set.")
        print("      Add them to neuron-backend/backend/.env\n")
        sys.exit(1)

    return supabase_url, supabase_anon


# ── Token management (auto-refresh like git) ──────────────────────────────────

def _is_token_expired(creds: dict) -> bool:
    expires_at = creds.get("expires_at", 0)
    now = int(datetime.now(timezone.utc).timestamp())
    return now >= (expires_at - 60)


def _refresh_access_token(refresh_token: str) -> dict | None:
    supabase_url, supabase_anon = _load_supabase_config()
    try:
        resp = requests.post(
            f"{supabase_url}/auth/v1/token?grant_type=refresh_token",
            headers={
                "apikey":       supabase_anon,
                "Content-Type": "application/json",
            },
            json={"refresh_token": refresh_token},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None


def _get_valid_token() -> str:
    """
    Returns a valid JWT. Silently refreshes if expired — exactly like
    git credential helpers refresh OAuth tokens transparently.
    """
    creds = _load_credentials()

    if not creds:
        print("\n  ❌  Not logged in. Run:  neuron login\n")
        sys.exit(1)

    # Still valid — return immediately
    if not _is_token_expired(creds):
        return creds["access_token"]

    # Expired — silent refresh
    print("  🔄  Refreshing session...", end="", flush=True)
    new_session = _refresh_access_token(creds["refresh_token"])

    if new_session and new_session.get("access_token"):
        _save_credentials(
            email         = creds["email"],
            access_token  = new_session["access_token"],
            refresh_token = new_session.get("refresh_token", creds["refresh_token"]),
            expires_at    = new_session.get("expires_at", 0),
        )
        print(" done")
        return new_session["access_token"]

    # Refresh truly failed (password changed, account deleted, etc.)
    _clear_credentials()
    print("\n\n  ❌  Your session has expired. Run:  neuron login\n")
    sys.exit(1)


def _auth_headers() -> dict:
    return {
        "Authorization": f"Bearer {_get_valid_token()}",
        "Content-Type":  "application/json",
    }


# ── Supabase auth calls ───────────────────────────────────────────────────────

def _supabase_login(email: str, password: str) -> dict:
    supabase_url, supabase_anon = _load_supabase_config()

    resp = requests.post(
        f"{supabase_url}/auth/v1/token?grant_type=password",
        headers={
            "apikey":       supabase_anon,
            "Content-Type": "application/json",
        },
        json={"email": email, "password": password},
        timeout=10,
    )

    if resp.status_code != 200:
        data = resp.json()
        msg  = data.get("error_description") or data.get("msg") or data.get("error") or resp.text

        # Clear, actionable error messages
        if "not confirmed" in str(msg).lower() or "email_not_confirmed" in str(data.get("error", "")):
            raise ValueError(
                "Email not confirmed.\n\n"
                "  → Check your inbox and click the confirmation link.\n"
                "  → Or disable confirmation in Supabase:\n"
                "    Authentication → Settings → uncheck 'Confirm email'"
            )
        if "invalid login" in str(msg).lower() or "invalid_credentials" in str(data.get("error", "")):
            raise ValueError(
                "Invalid email or password.\n\n"
                "  → No account yet? Run:  neuron signup"
            )
        raise ValueError(msg)

    return resp.json()


def _supabase_signup(email: str, password: str) -> dict:
    supabase_url, supabase_anon = _load_supabase_config()

    resp = requests.post(
        f"{supabase_url}/auth/v1/signup",
        headers={
            "apikey":       supabase_anon,
            "Content-Type": "application/json",
        },
        json={"email": email, "password": password},
        timeout=10,
    )

    if resp.status_code not in (200, 201):
        data = resp.json()
        msg  = data.get("msg") or data.get("error_description") or resp.text
        raise ValueError(msg)

    return resp.json()


# ── Auth commands ─────────────────────────────────────────────────────────────

def cmd_login():
    print()
    print("  🧠 Neuron — Login")
    print("  " + "─" * 36)
    print()

    email    = input("  Email: ").strip()
    password = getpass.getpass("  Password: ")

    if not email or not password:
        print("  ❌  Email and password cannot be empty.")
        sys.exit(1)

    print()
    print("  Authenticating...", end="", flush=True)

    try:
        data = _supabase_login(email, password)
    except ValueError as e:
        print(f"\n\n  ❌  Login failed: {e}\n")
        sys.exit(1)
    except requests.ConnectionError:
        print("\n  ❌  Could not reach Supabase. Check your internet connection.")
        sys.exit(1)

    _save_credentials(
        email         = email,
        access_token  = data["access_token"],
        refresh_token = data["refresh_token"],
        expires_at    = data.get("expires_at", 0),
    )

    print(" done\n")
    print(f"  ✅  Logged in as {email}")
    print(f"  📁  Credentials saved to {CREDS_FILE}")
    print()


def cmd_signup():
    print()
    print("  🧠 Neuron — Create Account")
    print("  " + "─" * 36)
    print()

    email    = input("  Email: ").strip()
    password = getpass.getpass("  Password (min 6 chars): ")
    confirm  = getpass.getpass("  Confirm password: ")

    if not email or not password:
        print("  ❌  Email and password cannot be empty.")
        sys.exit(1)
    if password != confirm:
        print("  ❌  Passwords do not match.")
        sys.exit(1)
    if len(password) < 6:
        print("  ❌  Password must be at least 6 characters.")
        sys.exit(1)

    print()
    print("  Creating account...", end="", flush=True)

    try:
        _supabase_signup(email, password)
    except ValueError as e:
        print(f"\n\n  ❌  Signup failed: {e}\n")
        sys.exit(1)
    except requests.ConnectionError:
        print("\n  ❌  Could not reach Supabase. Check your internet connection.")
        sys.exit(1)

    print(" done\n")
    print(f"  ✅  Account created for {email}")
    print()
    print("  📧  Check your inbox for a confirmation email.")
    print("      After confirming, run:  neuron login")
    print()


def cmd_logout():
    creds = _load_credentials()
    if not creds:
        print("\n  You are not logged in.\n")
        return
    _clear_credentials()
    print(f"\n  ✅  Logged out ({creds.get('email', '')})")
    print(f"  🗑   Credentials removed from {CREDS_FILE}\n")


def cmd_whoami():
    creds = _load_credentials()
    if not creds:
        print("\n  Not logged in. Run:  neuron login\n")
        sys.exit(1)

    expired = _is_token_expired(creds)
    status  = "✅ active" if not expired else "🔄 will auto-refresh on next command"

    print()
    print(f"  user.email    {creds.get('email', 'unknown')}")
    print(f"  session       {status}")
    print(f"  credentials   {CREDS_FILE}")
    print()


# ── Project commands ──────────────────────────────────────────────────────────

def init_project(path):
    response = requests.post(
        f"{BACKEND_URL}/cli/init",
        headers=_auth_headers(),
        json={"path": path},
    )
    if response.status_code == 200:
        print("✅ Project initialized successfully.")
    else:
        print("❌ Failed:", response.text)


def scaffold(prompt):
    response = requests.post(
        f"{BACKEND_URL}/cli/scaffold",
        headers=_auth_headers(),
        json={"prompt": prompt},
    )
    if response.status_code == 200:
        print("🚀 Feature generation started.")
    else:
        print("❌ Failed:", response.text)


def create_project(project_name):
    print()
    print(f"  🧠 Neuron — Create Project: {project_name}")
    print("  " + "─" * 40)
    print()

    print("  📦 Select backend tech stack:")
    print("     [1] Python  (Flask + SQLAlchemy)")
    print("     [2] Node.js (Express + Prisma)")
    print()
    while True:
        choice = input("  Enter choice (1 or 2): ").strip()
        if choice == "1":   backend = "python"; break
        elif choice == "2": backend = "nodejs"; break
        else: print("  Please enter 1 or 2")

    print()
    print("  Select database:")
    print("     [1] SQLite   (simple, file-based — good for dev)")
    print("     [2] PostgreSQL")
    print()
    while True:
        db_choice = input("  Enter choice (1 or 2): ").strip()
        if db_choice == "1":   database = "sqlite"; break
        elif db_choice == "2": database = "postgres"; break
        else: print("  Please enter 1 or 2")

    print()
    print("  ✅ Config summary:")
    print(f"     Project  : {project_name}")
    print(f"     Backend  : {backend}")
    print(f"     Database : {database}")
    print()

    if input("  Create project? (y/n): ").strip().lower() != "y":
        print("  Cancelled.")
        return

    print(f"\n  Creating '{project_name}'...\n")

    response = requests.post(
        f"{BACKEND_URL}/cli/create",
        headers=_auth_headers(),
        json={
            "project_name": project_name,
            "backend":      backend,
            "database":     database,
            "cwd":          os.getcwd(),
        },
    )

    if response.status_code == 200:
        data          = response.json()
        project_path  = data.get("path", f"./{project_name}")
        files_created = data.get("files_created", [])
        print(f"  Project created at: {project_path}")
        print(f"\n  Files generated ({len(files_created)}):")
        for f in files_created:
            print(f"    + {f}")
        print()
        print("  Next steps:")
        if backend == "python":
            print(f"    cd {project_name}")
            print(f"    python -m venv venv && venv\\Scripts\\activate")
            print(f"    pip install -r requirements.txt && python app.py")
        else:
            print(f"    cd {project_name} && npm install && npm run dev")
        print()
    else:
        print(f"\n  ❌ Failed: {response.text}")


# ── Help ──────────────────────────────────────────────────────────────────────

def print_help():
    print()
    print("  🧠 Neuron CLI")
    print()
    print("  Usage: neuron <command> [args]")
    print()
    print("  Auth:")
    print("    neuron login              Log in to your Neuron account")
    print("    neuron signup             Create a new account")
    print("    neuron logout             Log out and remove saved credentials")
    print("    neuron whoami             Show currently logged-in user")
    print()
    print("  Projects:")
    print("    neuron init <path>        Initialize a project from a local path")
    print("    neuron scaffold <prompt>  Generate a feature with AI")
    print("    neuron create <name>      Create a new project with boilerplate")
    print()


# ── Entry ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print_help()
        sys.exit(0)

    command = sys.argv[1]

    if   command == "login":    cmd_login()
    elif command == "signup":   cmd_signup()
    elif command == "logout":   cmd_logout()
    elif command == "whoami":   cmd_whoami()
    elif command == "init":
        if len(sys.argv) < 3:
            print("Usage: neuron init <project_path>"); sys.exit(1)
        init_project(sys.argv[2])
    elif command == "scaffold":
        if len(sys.argv) < 3:
            print("Usage: neuron scaffold <feature_description>"); sys.exit(1)
        scaffold(" ".join(sys.argv[2:]))
    elif command == "create":
        if len(sys.argv) < 3:
            print("Usage: neuron create <project_name>"); sys.exit(1)
        create_project(sys.argv[2])
    else:
        print(f"\n  Unknown command: '{sys.argv[1]}'")
        print_help()
        sys.exit(1)