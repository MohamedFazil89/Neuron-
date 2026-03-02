import sys
import requests

BACKEND_URL = "http://127.0.0.1:5000"

def init_project(path):
    print("🔥 USING THIS NEURON.PY FILE")
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


if __name__ == "__main__":

    if len(sys.argv) < 2:
        print("Usage:")
        print("  neuron init <project_path>")
        print("  neuron scaffold <feature_description>")
        sys.exit(1)

    command = sys.argv[1]

    if command == "init":
        if len(sys.argv) < 3:
            print("Usage: neuron init <project_path>")
            sys.exit(1)

        project_path = sys.argv[2]
        init_project(project_path)

    elif command == "scaffold":
        if len(sys.argv) < 3:
            print("Usage: neuron scaffold <feature_description>")
            sys.exit(1)

        prompt = " ".join(sys.argv[2:])
        scaffold(prompt)

    else:
        print("Unknown command")