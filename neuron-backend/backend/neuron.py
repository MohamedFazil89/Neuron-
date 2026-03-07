import sys
import os
import requests

BACKEND_URL = "http://127.0.0.1:5000"


def init_project(path):
    print("USING THIS NEURON.PY FILE")
    response = requests.post(
        f"{BACKEND_URL}/cli/init",
        json={"path": path}
    )
    if response.status_code == 200:
        print("✅ Project initialized successfully.")
    else:
        print("❌ Failed:", response.text)


def scaffold(prompt):
    response = requests.post(
        f"{BACKEND_URL}/cli/scaffold",
        json={"prompt": prompt}
    )
    if response.status_code == 200:
        print("🚀 Feature generation started.")
    else:
        print("❌ Failed:", response.text)


def create_project(project_name):
    """
    Interactive project creation wizard.
    Asks for tech stack selections, then calls the backend to generate
    a full runnable boilerplate in a new folder.
    """
    print()
    print(f"  🧠 Neuron — Create Project: {project_name}")
    print("  " + "─" * 40)
    print()

    # ── Step 1: Backend stack ────────────────────────────────────────────
    print("  📦 Select backend tech stack:")
    print("     [1] Python  (Flask + SQLAlchemy)")
    print("     [2] Node.js (Express + Prisma)")
    print()

    while True:
        backend_choice = input("  Enter choice (1 or 2): ").strip()
        if backend_choice == "1":
            backend = "python"
            break
        elif backend_choice == "2":
            backend = "nodejs"
            break
        else:
            print("   Please enter 1 or 2")

    print()

    # ── Step 2: Database ─────────────────────────────────────────────────
    print("  Select database:")
    print("     [1] SQLite   (simple, file-based — good for dev)")
    print("     [2] PostgreSQL")
    print()

    while True:
        db_choice = input("  Enter choice (1 or 2): ").strip()
        if db_choice == "1":
            database = "sqlite"
            break
        elif db_choice == "2":
            database = "postgres"
            break
        else:
            print("  Please enter 1 or 2")

    print()

    # ── Step 3: Confirm ──────────────────────────────────────────────────
    print("  ✅ Config summary:")
    print(f"     Project  : {project_name}")
    print(f"     Backend  : {backend}")
    print(f"     Database : {database}")
    print()

    confirm = input("  Create project? (y/n): ").strip().lower()
    if confirm != "y":
        print("  Cancelled.")
        return

    print()
    print(f"   Creating project '{project_name}'...")
    print()

    # ── Step 4: Call backend ─────────────────────────────────────────────
    response = requests.post(
        f"{BACKEND_URL}/cli/create",
        json={
            "project_name": project_name,
            "backend": backend,
            "database": database,
            "cwd": os.getcwd(),
        }
    )

    if response.status_code == 200:
        data = response.json()
        project_path = data.get("path", f"./{project_name}")
        files_created = data.get("files_created", [])

        print(f"   Project created at: {project_path}")
        print()
        print(f"   Files generated ({len(files_created)}):")
        for f in files_created:
            print(f"     + {f}")
        print()
        print("  Next steps:")
        if backend == "python":
            print(f"     cd {project_name}")
            print(f"     python -m venv venv &&  venv\Scripts\activate")
            print(f"     pip install -r requirements.txt")
            print(f"     python app.py")
        else:
            print(f"     cd {project_name}")
            print(f"     npm install")
            print(f"     npm run dev")
        print()
    else:
        print(f"  Failed: {response.text}")




if __name__ == "__main__":

    if len(sys.argv) < 2:
        print("Usage:")
        print("  neuron init <project_path>")
        print("  neuron scaffold <feature_description>")
        print("  neuron create <project_name>")
        sys.exit(1)

    command = sys.argv[1]

    if command == "init":
        if len(sys.argv) < 3:
            print("Usage: neuron init <project_path>")
            sys.exit(1)
        init_project(sys.argv[2])

    elif command == "scaffold":
        if len(sys.argv) < 3:
            print("Usage: neuron scaffold <feature_description>")
            sys.exit(1)
        prompt = " ".join(sys.argv[2:])
        scaffold(prompt)

    elif command == "create":
        if len(sys.argv) < 3:
            print("Usage: neuron create <project_name>")
            sys.exit(1)
        create_project(sys.argv[2])

    else:
        print(f"Unknown command: '{sys.argv[1]}'")
        print("Commands: init, scaffold, create")