import os
import click
from flask import Flask

def create_app():
    app = Flask(__name__)
    # ... other app configurations ...
    return app

app = create_app()

@app.cli.command("current-path")
def get_path():
    """Prints the current working directory."""
    cwd = os.getcwd()
    print(f"The current terminal path is: {cwd}")

if __name__ == "__main__":
    app.run()
