"""
VDOS Server Launcher
Automatically starts Chat, Email, and Simulation servers in sequence.
"""
import sys
import os
import time
import subprocess
import threading
import webbrowser
from typing import Optional
from pathlib import Path

# Load environment variables from .env file
from dotenv import load_dotenv

# Find and load .env from project root
project_root = Path(__file__).parent.parent.parent
env_path = project_root / '.env'
if env_path.exists():
    load_dotenv(env_path)
    print(f"[VDOS] Loaded environment variables from {env_path}")
else:
    print(f"[VDOS] Warning: .env file not found at {env_path}")

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import uvicorn


class ServerProcess:
    """Manages a single server process."""

    def __init__(self, name: str, module: str, host: str, port: int):
        self.name = name
        self.module = module
        self.host = host
        self.port = port
        self.process: Optional[subprocess.Popen] = None
        self.thread: Optional[threading.Thread] = None

    def start(self):
        """Start the server in a background thread."""
        print(f"[VDOS] Starting {self.name} server on {self.host}:{self.port}...")

        def run_server():
            try:
                # Import and run the app
                module_path, app_name = self.module.rsplit(':', 1)
                uvicorn.run(
                    f"{module_path}:{app_name}",
                    host=self.host,
                    port=self.port,
                    log_level="info"
                )
            except Exception as e:
                print(f"[VDOS] ERROR: {self.name} server failed: {e}")

        self.thread = threading.Thread(target=run_server, daemon=True)
        self.thread.start()

        # Wait a moment for server to start
        time.sleep(2)
        print(f"[VDOS] ✓ {self.name} server started")

    def is_running(self) -> bool:
        """Check if server thread is alive."""
        return self.thread is not None and self.thread.is_alive()


def main():
    """
    Main entry point for VDOS application.
    Starts core backend servers and opens the dashboard in browser.
    """
    print("=" * 70)
    print("VDOS - Virtual Department Operations Simulator")
    print("=" * 70)
    print()

    # Define servers
    servers = [
        ServerProcess(
            name="Chat",
            module="virtualoffice.servers.chat.app:app",
            host=os.getenv("VDOS_CHAT_HOST", "127.0.0.1"),
            port=int(os.getenv("VDOS_CHAT_PORT", "8001"))
        ),
        ServerProcess(
            name="Email",
            module="virtualoffice.servers.email.app:app",
            host=os.getenv("VDOS_EMAIL_HOST", "127.0.0.1"),
            port=int(os.getenv("VDOS_EMAIL_PORT", "8000"))
        ),
        ServerProcess(
            name="Simulation",
            module="virtualoffice.sim_manager.app:app",
            host=os.getenv("VDOS_SIM_HOST", "127.0.0.1"),
            port=int(os.getenv("VDOS_SIM_PORT", "8015"))
        ),
        ServerProcess(
            name="Clustering",
            module="virtualoffice.servers.clustering.app:app",
            host=os.getenv("VDOS_CLUSTER_HOST", "127.0.0.1"),
            port=int(os.getenv("VDOS_CLUSTER_PORT", "8016"))
        ),
    ]

    # Start servers sequentially
    for server in servers:
        server.start()

    # All servers started - open dashboard
    print()
    print("=" * 70)
    print("All servers started successfully!")
    print("=" * 70)
    print()
    print(f"Chat Server:       http://{servers[0].host}:{servers[0].port}")
    print(f"Email Server:      http://{servers[1].host}:{servers[1].port}")
    print(f"Simulation Server: http://{servers[2].host}:{servers[2].port}")
    print(f"Clustering Server: http://{servers[3].host}:{servers[3].port}")
    print()
    print("Opening VDOS Dashboard in browser...")
    print("=" * 70)
    print()

    # Open dashboard in browser
    dashboard_url = f"http://{servers[2].host}:{servers[2].port}"
    try:
        webbrowser.open(dashboard_url)
    except Exception as e:
        print(f"[VDOS] Could not open browser: {e}")
        print(f"[VDOS] Please manually open: {dashboard_url}")

    # Keep main thread alive
    try:
        while True:
            # Check if all servers are still running
            for server in servers:
                if not server.is_running():
                    print(f"[VDOS] WARNING: {server.name} server stopped unexpectedly")
            time.sleep(5)
    except KeyboardInterrupt:
        print()
        print("=" * 70)
        print("Shutting down VDOS servers...")
        print("=" * 70)
        sys.exit(0)


if __name__ == "__main__":
    main()
