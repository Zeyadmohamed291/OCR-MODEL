import os
import sys
import subprocess

if __name__ == "__main__":
    venv_python = os.path.join(os.path.dirname(os.path.abspath(__file__)), "venv", "Scripts", "python.exe")
    if not os.path.exists(venv_python):
        print(f"Error: Virtual environment not found at {venv_python}")
        sys.exit(1)

    print("=" * 60)
    print("  Starting Universal Document OCR Server...")
    print("  Interactive Web Viewer: http://127.0.0.1:8000/viewer")
    print("  API Docs (Swagger):     http://127.0.0.1:8000/docs")
    print("  Health Check:           http://127.0.0.1:8000/health")
    print("=" * 60)

    cmd = [
        venv_python,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
        "--reload",
    ]
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\nServer stopped.")
