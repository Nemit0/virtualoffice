import importlib.metadata
import logging
import os
import sys
import threading
import time
from dataclasses import dataclass
from typing import List

from PySide6 import QtWidgets
import uvicorn

from virtualoffice.servers.chat import app as chat_app
from virtualoffice.servers.email import app as email_app

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('virtualoffice.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

EMAIL_HOST = os.getenv("VDOS_EMAIL_HOST", "127.0.0.1")
EMAIL_PORT = int(os.getenv("VDOS_EMAIL_PORT", "8000"))
CHAT_HOST = os.getenv("VDOS_CHAT_HOST", "127.0.0.1")
CHAT_PORT = int(os.getenv("VDOS_CHAT_PORT", "8001"))


@dataclass
class ServerHandle:
    name: str
    server: uvicorn.Server
    thread: threading.Thread
    host: str
    port: int


def _start_uvicorn_server(name: str, fastapi_app, host: str, port: int) -> ServerHandle:
    config = uvicorn.Config(
        fastapi_app,
        host=host,
        port=port,
        log_level="info",
        access_log=False,
    )
    server = uvicorn.Server(config)
    server.install_signal_handlers = False

    thread = threading.Thread(target=server.run, name=f"{name}-uvicorn", daemon=True)
    thread.start()

    deadline = time.time() + 5
    while not getattr(server, "started", False) and thread.is_alive() and time.time() < deadline:
        time.sleep(0.05)

    if not getattr(server, "started", False):
        logger.error("Failed to start %s server on %s:%s", name, host, port)
        raise RuntimeError(f"{name} server failed to start on {host}:{port}")

    logger.info("%s server listening on %s:%s", name.capitalize(), host, port)
    return ServerHandle(name=name, server=server, thread=thread, host=host, port=port)


def _stop_uvicorn_server(handle: ServerHandle, timeout: float = 5.0) -> None:
    if not handle.thread.is_alive():
        return

    logger.info("Stopping %s server...", handle.name)
    handle.server.should_exit = True
    handle.thread.join(timeout)
    if handle.thread.is_alive():
        logger.warning("%s server did not shut down cleanly", handle.name)
    else:
        logger.info("%s server stopped", handle.name)


class virtualOffice(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("virtualoffice")
        self.show()


def main():
    sys.stdout.write("Starting virtualoffice application...\n")
    app_module = sys.modules["__main__"].__package__
    metadata = importlib.metadata.metadata(app_module)

    server_handles: List[ServerHandle] = []
    exit_code = 0
    try:
        server_handles.append(_start_uvicorn_server("email", email_app, EMAIL_HOST, EMAIL_PORT))
        server_handles.append(_start_uvicorn_server("chat", chat_app, CHAT_HOST, CHAT_PORT))

        QtWidgets.QApplication.setApplicationName(metadata["Formal-Name"])
        app = QtWidgets.QApplication(sys.argv)

        def _shutdown_servers():
            for handle in server_handles:
                _stop_uvicorn_server(handle)

        app.aboutToQuit.connect(_shutdown_servers)

        main_window = virtualOffice()
        exit_code = app.exec()
    finally:
        for handle in server_handles:
            _stop_uvicorn_server(handle)
        logger.info("virtualoffice application exited.")
        logger.info("Log saved to virtualoffice.log")

    sys.exit(exit_code)