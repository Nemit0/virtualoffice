from __future__ import annotations

import importlib.metadata
import logging
import os
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import httpx
from PySide6 import QtCore, QtGui, QtWidgets
import uvicorn

from virtualoffice.servers.chat import app as chat_app
from virtualoffice.servers.email import app as email_app
from virtualoffice.sim_manager import create_app as create_sim_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("virtualoffice.log"), logging.StreamHandler()],
)

logger = logging.getLogger(__name__)

EMAIL_HOST = os.getenv("VDOS_EMAIL_HOST", "127.0.0.1")
EMAIL_PORT = int(os.getenv("VDOS_EMAIL_PORT", "8000"))
CHAT_HOST = os.getenv("VDOS_CHAT_HOST", "127.0.0.1")
CHAT_PORT = int(os.getenv("VDOS_CHAT_PORT", "8001"))
SIM_HOST = os.getenv("VDOS_SIM_HOST", "127.0.0.1")
SIM_PORT = int(os.getenv("VDOS_SIM_PORT", "8015"))
SIM_BASE_URL = os.getenv("VDOS_SIM_BASE_URL", f"http://{SIM_HOST}:{SIM_PORT}")
LOG_PATH = Path("virtualoffice.log")


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


class WorkerSignals(QtCore.QObject):
    finished = QtCore.Signal(object, object)


class RequestWorker(QtCore.QRunnable):
    def __init__(self, fn: Callable, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @QtCore.Slot()
    def run(self) -> None:
        try:
            result = self.fn(*self.args, **self.kwargs)
            self.signals.finished.emit(result, None)
        except Exception as exc:  # pragma: no cover - UI safeguard
            logger.exception("Background request failed")
            self.signals.finished.emit(None, exc)


SERVER_ORDER = ["email", "chat", "sim"]
SERVER_CONFIG = {
    "email": {
        "label": "Email API",
        "host": EMAIL_HOST,
        "port": EMAIL_PORT,
        "factory": lambda: email_app,
    },
    "chat": {
        "label": "Chat API",
        "host": CHAT_HOST,
        "port": CHAT_PORT,
        "factory": lambda: chat_app,
    },
    "sim": {
        "label": "Simulation API",
        "host": SIM_HOST,
        "port": SIM_PORT,
        "factory": create_sim_app,
    },
}


class SimulationDashboard(QtWidgets.QWidget):
    def __init__(
        self,
        server_config: Dict[str, Dict[str, object]],
        start_server_cb: Callable[[str], object],
        stop_server_cb: Callable[[str], object],
        is_running_cb: Callable[[str], bool],
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.server_config = server_config
        self.start_server_cb = start_server_cb
        self.stop_server_cb = stop_server_cb
        self.is_running_cb = is_running_cb

        self.http_client = httpx.Client(base_url=SIM_BASE_URL, timeout=5.0)
        self.thread_pool = QtCore.QThreadPool.globalInstance()
        self.people_cache: list[dict[str, Any]] = []

        self.server_status_labels: Dict[str, QtWidgets.QLabel] = {}
        self.server_start_buttons: Dict[str, QtWidgets.QPushButton] = {}
        self.server_stop_buttons: Dict[str, QtWidgets.QPushButton] = {}

        server_group = QtWidgets.QGroupBox("Local Services")
        server_layout = QtWidgets.QGridLayout(server_group)
        for row, name in enumerate(SERVER_ORDER):
            config = self.server_config[name]
            label = QtWidgets.QLabel("stopped")
            start_btn = QtWidgets.QPushButton("Start")
            stop_btn = QtWidgets.QPushButton("Stop")
            start_btn.clicked.connect(lambda _, n=name: self.request_start_server(n))
            stop_btn.clicked.connect(lambda _, n=name: self.request_stop_server(n))

            server_layout.addWidget(QtWidgets.QLabel(config["label"]), row, 0)
            server_layout.addWidget(label, row, 1)
            server_layout.addWidget(start_btn, row, 2)
            server_layout.addWidget(stop_btn, row, 3)

            self.server_status_labels[name] = label
            self.server_start_buttons[name] = start_btn
            self.server_stop_buttons[name] = stop_btn

        self.status_label = QtWidgets.QLabel("Simulation server offline. Start it above.")
        self.start_button = QtWidgets.QPushButton("Start Simulation")
        self.stop_button = QtWidgets.QPushButton("Stop Simulation")
        self.refresh_button = QtWidgets.QPushButton("Refresh Status")

        self.tick_spin = QtWidgets.QSpinBox()
        self.tick_spin.setRange(1, 480)
        self.tick_spin.setValue(5)
        self.reason_input = QtWidgets.QLineEdit("manual")
        self.advance_button = QtWidgets.QPushButton("Advance")
        self.seed_button = QtWidgets.QPushButton("Seed Sample Worker")

        self.project_name_input = QtWidgets.QLineEdit()
        self.project_summary_input = QtWidgets.QPlainTextEdit()
        self.project_summary_input.setFixedHeight(80)
        self.project_duration_spin = QtWidgets.QSpinBox()
        self.project_duration_spin.setRange(1, 52)
        self.project_duration_spin.setValue(4)
        self.department_head_input = QtWidgets.QLineEdit()
        self.model_hint_input = QtWidgets.QLineEdit()

        controls_layout = QtWidgets.QGridLayout()
        controls_layout.addWidget(self.status_label, 0, 0, 1, 4)
        controls_layout.addWidget(self.start_button, 1, 0)
        controls_layout.addWidget(self.stop_button, 1, 1)
        controls_layout.addWidget(self.refresh_button, 1, 2)
        controls_layout.addWidget(QtWidgets.QLabel("Ticks:"), 2, 0)
        controls_layout.addWidget(self.tick_spin, 2, 1)
        controls_layout.addWidget(QtWidgets.QLabel("Reason:"), 3, 0)
        controls_layout.addWidget(self.reason_input, 3, 1, 1, 2)
        controls_layout.addWidget(self.advance_button, 2, 2, 2, 1)
        controls_layout.addWidget(QtWidgets.QLabel("Project Name:"), 4, 0)
        controls_layout.addWidget(self.project_name_input, 4, 1, 1, 2)
        controls_layout.addWidget(QtWidgets.QLabel("Project Summary:"), 5, 0)
        controls_layout.addWidget(self.project_summary_input, 5, 1, 1, 2)
        controls_layout.addWidget(QtWidgets.QLabel("Duration (weeks):"), 6, 0)
        controls_layout.addWidget(self.project_duration_spin, 6, 1)
        controls_layout.addWidget(QtWidgets.QLabel("Department Head:"), 7, 0)
        controls_layout.addWidget(self.department_head_input, 7, 1, 1, 2)
        controls_layout.addWidget(QtWidgets.QLabel("Model Hint:"), 8, 0)
        controls_layout.addWidget(self.model_hint_input, 8, 1, 1, 2)
        controls_layout.addWidget(self.seed_button, 9, 0, 1, 4)

        reports_header = QtWidgets.QHBoxLayout()
        reports_header.addWidget(QtWidgets.QLabel("Person:"))
        self.person_combo = QtWidgets.QComboBox()
        self.person_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToContents)
        reports_header.addWidget(self.person_combo)
        self.refresh_people_button = QtWidgets.QPushButton("Refresh People")
        reports_header.addWidget(self.refresh_people_button)
        self.refresh_reports_button = QtWidgets.QPushButton("Refresh Reports")
        reports_header.addWidget(self.refresh_reports_button)
        reports_header.addStretch(1)

        self.report_tabs = QtWidgets.QTabWidget()
        self.daily_reports_view = QtWidgets.QPlainTextEdit()
        self.daily_reports_view.setReadOnly(True)
        self.simulation_reports_view = QtWidgets.QPlainTextEdit()
        self.simulation_reports_view.setReadOnly(True)
        self.token_usage_view = QtWidgets.QPlainTextEdit()
        self.token_usage_view.setReadOnly(True)
        self.report_tabs.addTab(self.daily_reports_view, "Daily Reports")
        self.report_tabs.addTab(self.simulation_reports_view, "Simulation Reports")
        self.report_tabs.addTab(self.token_usage_view, "Token Usage")

        self.log_view = QtWidgets.QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        fixed_font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
        self.log_view.setFont(fixed_font)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(server_group)
        layout.addLayout(controls_layout)
        layout.addLayout(reports_header)
        layout.addWidget(self.report_tabs)
        layout.addWidget(QtWidgets.QLabel("virtualoffice.log"))
        layout.addWidget(self.log_view)

        self.start_button.clicked.connect(self.start_simulation)
        self.stop_button.clicked.connect(self.stop_simulation)
        self.refresh_button.clicked.connect(self.refresh_state)
        self.advance_button.clicked.connect(self.advance_simulation)
        self.seed_button.clicked.connect(self.seed_worker)
        self.refresh_people_button.clicked.connect(self.refresh_people)
        self.refresh_reports_button.clicked.connect(self.refresh_reports)
        self.person_combo.currentIndexChanged.connect(self._on_person_changed)

        self.log_timer = QtCore.QTimer(self)
        self.log_timer.setInterval(2000)
        self.log_timer.timeout.connect(self.refresh_log)
        self.log_timer.start()

        self.update_server_buttons()
        QtCore.QTimer.singleShot(200, self.refresh_state)
        QtCore.QTimer.singleShot(200, self.refresh_log)

    # ------------------------------------------------------------------
    def request_start_server(self, name: str) -> None:
        config = self.server_config[name]
        self.status_label.setText(f"Starting {config['label']}…")
        self.server_start_buttons[name].setEnabled(False)
        worker = RequestWorker(self.start_server_cb, name)
        worker.signals.finished.connect(lambda result, error: self._handle_server_result(name, result, error))
        self.thread_pool.start(worker)

    def request_stop_server(self, name: str) -> None:
        config = self.server_config[name]
        self.status_label.setText(f"Stopping {config['label']}…")
        self.server_stop_buttons[name].setEnabled(False)
        worker = RequestWorker(self.stop_server_cb, name)
        worker.signals.finished.connect(lambda result, error: self._handle_server_result(name, result, error))
        self.thread_pool.start(worker)

    def _handle_server_result(self, name: str, result: object, error: Optional[Exception]) -> None:
        config = self.server_config[name]
        if error:
            self.status_label.setText(f"{config['label']} error: {error}")
        else:
            state = "running" if self.is_running_cb(name) else "stopped"
            self.status_label.setText(f"{config['label']} {state}.")
        self.update_server_buttons()
        if name == "sim" and self.is_running_cb("sim"):
            self.refresh_state()
            self.refresh_people()

    def update_server_buttons(self) -> None:
        for name in SERVER_ORDER:
            config = self.server_config[name]
            running = self.is_running_cb(name)
            status_text = "running" if running else "stopped"
            self.server_status_labels[name].setText(f"{status_text} on {config['host']}:{config['port']}")
            self.server_start_buttons[name].setEnabled(not running)
            self.server_stop_buttons[name].setEnabled(running)

        sim_running = self.is_running_cb("sim")
        self._set_simulation_controls_enabled(sim_running)
        if not sim_running:
            self.status_label.setText("Simulation server offline. Start it above.")

    # ------------------------------------------------------------------
    def _run_request(
        self,
        fn: Callable,
        callback: Callable[[Optional[dict], Optional[Exception]], None],
    ) -> None:
        worker = RequestWorker(fn)
        worker.signals.finished.connect(callback)
        self.thread_pool.start(worker)

    def _start(self, payload: Optional[dict] = None) -> dict:
        response = self.http_client.post("/api/v1/simulation/start", json=payload)
        response.raise_for_status()
        return response.json()

    def _stop(self) -> dict:
        response = self.http_client.post("/api/v1/simulation/stop")
        response.raise_for_status()
        return response.json()

    def _state(self) -> dict:
        response = self.http_client.get("/api/v1/simulation")
        response.raise_for_status()
        return response.json()

    def _advance(self, ticks: int, reason: str) -> dict:
        payload = {"ticks": ticks, "reason": reason}
        response = self.http_client.post("/api/v1/simulation/advance", json=payload)
        response.raise_for_status()
        return response.json()

    def _seed_person(self) -> dict:
        payload = {
            "name": "Hana Kim",
            "role": "Designer",
            "timezone": "Asia/Seoul",
            "work_hours": "09:00-18:00",
            "break_frequency": "50/10 cadence",
            "communication_style": "Warm async",
            "email_address": "hana.kim@vdos.local",
            "chat_handle": "hana",
            "skills": ["Figma", "UX"],
            "personality": ["Collaborative", "Calm"],
            "schedule": [
                {"start": "09:00", "end": "10:00", "activity": "Stand-up & triage"},
                {"start": "10:00", "end": "12:00", "activity": "Design sprint"},
            ],
        }
        response = self.http_client.post("/api/v1/people", json=payload)
        response.raise_for_status()
        return response.json()

    def refresh_people(self) -> None:
        if not self._sim_available():
            self.person_combo.blockSignals(True)
            self.person_combo.clear()
            self.person_combo.addItem("Simulation offline", None)
            self.person_combo.setEnabled(False)
            self.person_combo.blockSignals(False)
            return
        self._run_request(self._load_people, self._handle_people_response)

    def refresh_reports(self) -> None:
        if not self._sim_available():
            message = "Simulation server offline."
            self.daily_reports_view.setPlainText(message)
            self.simulation_reports_view.setPlainText(message)
            self.token_usage_view.setPlainText(message)
            return
        person_id = self._selected_person_id()
        if person_id is None:
            self.daily_reports_view.setPlainText("Select a persona to view daily reports.")
            self.simulation_reports_view.clear()
            self.token_usage_view.clear()
            return
        self._run_request(lambda: self._fetch_reports(person_id), self._handle_reports_response)

    def _load_people(self) -> List[dict]:
        response = self.http_client.get("/api/v1/people")
        response.raise_for_status()
        return response.json()

    def _handle_people_response(self, result: Optional[List[dict]], error: Optional[Exception]) -> None:
        if error:
            self.person_combo.blockSignals(True)
            self.person_combo.clear()
            self.person_combo.addItem(f"People load failed: {error}", None)
            self.person_combo.setEnabled(False)
        else:
            people = result or []
            self.people_cache = people
            self.person_combo.blockSignals(True)
            self.person_combo.clear()
            if not people:
                self.person_combo.addItem("No personas available", None)
                self.person_combo.setEnabled(False)
            else:
                self.person_combo.setEnabled(True)
                for person in people:
                    display = f"{person['name']} (#{person['id']})"
                    self.person_combo.addItem(display, person['id'])
                self.person_combo.setCurrentIndex(0)
        self.person_combo.blockSignals(False)
        if not error and self.people_cache:
            self.refresh_reports()
        elif not self.people_cache:
            self.daily_reports_view.setPlainText("No daily reports yet.")
            self.simulation_reports_view.clear()
            self.token_usage_view.clear()

    def _selected_person_id(self) -> Optional[int]:
        data = self.person_combo.currentData()
        return int(data) if isinstance(data, int) else None

    def _fetch_reports(self, person_id: int) -> Dict[str, Any]:
        daily = self.http_client.get(f"/api/v1/people/{person_id}/daily-reports")
        daily.raise_for_status()
        simulation = self.http_client.get("/api/v1/simulation/reports")
        simulation.raise_for_status()
        usage = self.http_client.get("/api/v1/simulation/token-usage")
        usage.raise_for_status()
        return {"daily": daily.json(), "simulation": simulation.json(), "usage": usage.json()}

    def _handle_reports_response(self, result: Optional[Dict[str, Any]], error: Optional[Exception]) -> None:
        if error:
            message = f"Failed to load reports: {error}"
            self.daily_reports_view.setPlainText(message)
            self.simulation_reports_view.clear()
            self.token_usage_view.clear()
            return
        payload = result or {}
        self.daily_reports_view.setPlainText(self._format_daily_reports(payload.get("daily", [])))
        self.simulation_reports_view.setPlainText(self._format_simulation_reports(payload.get("simulation", [])))
        self.token_usage_view.setPlainText(self._format_token_usage(payload.get("usage") or {}))

    def _format_daily_reports(self, reports: List[dict]) -> str:
        if not reports:
            return "No daily reports yet."
        parts: List[str] = []
        for report in reports:
            parts.append(
                f"Day {report['day_index']} (model={report['model_used']}, tokens={report.get('tokens_used', 0)})"
            )
            parts.append(report.get("schedule_outline", ""))
            parts.append("")
            parts.append(report.get("report", ""))
            parts.append("")
        return "\n".join(parts).strip()

    def _format_simulation_reports(self, reports: List[dict]) -> str:
        if not reports:
            return "No simulation reports generated yet."
        parts: List[str] = []
        for report in reports:
            parts.append(
                f"Report #{report['id']} (ticks={report['total_ticks']}, model={report['model_used']})"
            )
            parts.append(report.get("report", ""))
            parts.append("")
        return "\n".join(parts).strip()

    def _format_token_usage(self, usage: Dict[str, Any]) -> str:
        if not usage:
            return "No token usage recorded yet."
        per_model = usage.get("per_model", {}) if isinstance(usage, dict) else {}
        total = usage.get("total_tokens", 0) if isinstance(usage, dict) else 0
        if not per_model:
            return "No token usage recorded yet."
        lines = [f"Total tokens: {total}"]
        for model, tokens in sorted(per_model.items(), key=lambda item: item[1], reverse=True):
            lines.append(f"{model}: {tokens}")
        return "
".join(lines)

    def _on_person_changed(self) -> None:
        if not self._sim_available():
            return
        if self._selected_person_id() is None:
            return
        self.refresh_reports()

    # ------------------------------------------------------------------
    def start_simulation(self) -> None:
        if not self._sim_available():
            self.status_label.setText("Simulation server offline. Start it above.")
            return
        project_name = self.project_name_input.text().strip()
        project_summary = self.project_summary_input.toPlainText().strip()
        if not project_name or not project_summary:
            self.status_label.setText("Provide project name and summary before starting.")
            return
        payload: Dict[str, Any] = {
            "project_name": project_name,
            "project_summary": project_summary,
            "duration_weeks": self.project_duration_spin.value(),
        }
        department_head = self.department_head_input.text().strip()
        if department_head:
            payload["department_head_name"] = department_head
        model_hint = self.model_hint_input.text().strip()
        if model_hint:
            payload["model_hint"] = model_hint
        self.status_label.setText("Simulation state: starting…")
        self._run_request(lambda: self._start(payload), self._handle_state_response)

    def stop_simulation(self) -> None:
        if not self._sim_available():
            self.status_label.setText("Simulation server offline. Start it above.")
            return
        self.status_label.setText("Simulation state: stopping…")
        self._run_request(self._stop, self._handle_state_response)

    def refresh_state(self) -> None:
        if not self._sim_available():
            self._set_simulation_controls_enabled(False)
            self.status_label.setText("Simulation server offline. Start it above.")
            return
        self._run_request(self._state, self._handle_state_response)

    def advance_simulation(self) -> None:
        if not self._sim_available():
            self.status_label.setText("Simulation server offline. Start it above.")
            return
        ticks = self.tick_spin.value()
        reason = self.reason_input.text().strip() or "manual"
        self.status_label.setText(f"Advancing {ticks} ticks…")
        self._run_request(lambda: self._advance(ticks, reason), self._handle_advance_response)

    def seed_worker(self) -> None:
        if not self._sim_available():
            self.status_label.setText("Simulation server offline. Start it above.")
            return
        self.status_label.setText("Creating sample worker…")
        self._run_request(self._seed_person, self._handle_seed_response)

    def _handle_state_response(self, result: Optional[dict], error: Optional[Exception]) -> None:
        if error:
            self.status_label.setText(f"Simulation state error: {error}")
            self._set_simulation_controls_enabled(False)
            return
        state = result or {}
        running = "running" if state.get("is_running") else "stopped"
        tick = state.get("current_tick", 0)
        self.status_label.setText(f"Simulation state: {running} (tick {tick})")
        self._set_simulation_controls_enabled(True)
        self.refresh_people()
        self.refresh_reports()

    def _handle_advance_response(self, result: Optional[dict], error: Optional[Exception]) -> None:
        if error:
            self.status_label.setText(f"Advance failed: {error}")
            return
        summary = result or {}
        tick = summary.get("current_tick", "?")
        emails = summary.get("emails_sent", 0)
        chats = summary.get("chat_messages_sent", 0)
        self.status_label.setText(f"Advanced to tick {tick} — emails {emails}, chats {chats}")
        self.refresh_reports()
        self.refresh_log()

    def _handle_seed_response(self, result: Optional[dict], error: Optional[Exception]) -> None:
        if error:
            self.status_label.setText(f"Seed failed: {error}")
            return
        person = result or {}
        self.status_label.setText(f"Created worker: {person.get('name', 'unknown')}")
        self.refresh_people()

    def refresh_log(self) -> None:
        if LOG_PATH.exists():
            try:
                text = LOG_PATH.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                return
            lines = text.splitlines()[-500:]
            cursor = self.log_view.textCursor()
            self.log_view.setPlainText("
".join(lines))
            cursor = self.log_view.textCursor()
            cursor.movePosition(QtGui.QTextCursor.End)
            self.log_view.setTextCursor(cursor)
        else:
            self.log_view.setPlainText("Log file not found yet.")

    def _set_simulation_controls_enabled(self, enabled: bool) -> None:
        widgets = [
            self.start_button,
            self.stop_button,
            self.refresh_button,
            self.advance_button,
            self.seed_button,
            self.tick_spin,
            self.reason_input,
            self.project_name_input,
            self.project_summary_input,
            self.project_duration_spin,
            self.department_head_input,
            self.model_hint_input,
            self.refresh_people_button,
            self.refresh_reports_button,
            self.person_combo,
        ]
        for widget in widgets:
            widget.setEnabled(enabled)

    def _sim_available(self) -> bool:
        return self.is_running_cb("sim")

    def _on_person_changed(self) -> None:
        if not self._sim_available():
            return
        if self._selected_person_id() is None:
            return
        self.refresh_reports()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # pragma: no cover - GUI only
        self.log_timer.stop()
        self.http_client.close()
        super().closeEvent(event)


class virtualOffice(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("virtualoffice")
        self.server_handles: Dict[str, ServerHandle] = {}

        self.dashboard = SimulationDashboard(
            server_config=SERVER_CONFIG,
            start_server_cb=self.start_server,
            stop_server_cb=self.stop_server,
            is_running_cb=self.is_server_running,
            parent=self,
        )
        self.setCentralWidget(self.dashboard)
        self.resize(960, 720)

    def start_server(self, name: str) -> None:
        if name in self.server_handles:
            raise RuntimeError(f"{SERVER_CONFIG[name]['label']} is already running")
        config = SERVER_CONFIG[name]
        app_factory: Callable[[], object] = config["factory"]  # type: ignore[assignment]
        fastapi_app = app_factory()
        handle = _start_uvicorn_server(name, fastapi_app, config["host"], config["port"])
        self.server_handles[name] = handle

    def stop_server(self, name: str) -> None:
        handle = self.server_handles.pop(name, None)
        if not handle:
            raise RuntimeError(f"{SERVER_CONFIG[name]['label']} is not running")
        _stop_uvicorn_server(handle)

    def is_server_running(self, name: str) -> bool:
        return name in self.server_handles

    def stop_all_servers(self) -> None:
        for name in list(self.server_handles.keys()):
            try:
                self.stop_server(name)
            except RuntimeError:
                logger.warning("Failed to stop %s during shutdown", name)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # pragma: no cover - GUI only
        self.stop_all_servers()
        super().closeEvent(event)


def main() -> None:
    sys.stdout.write("Starting virtualoffice application...
")
    app_module = sys.modules["__main__"].__package__
    metadata = importlib.metadata.metadata(app_module)

    server_handles: List[ServerHandle] = []
    exit_code = 0
    try:
        server_handles.append(_start_uvicorn_server("email", email_app, EMAIL_HOST, EMAIL_PORT))
        server_handles.append(_start_uvicorn_server("chat", chat_app, CHAT_HOST, CHAT_PORT))
        server_handles.append(_start_uvicorn_server("sim", create_sim_app(), SIM_HOST, SIM_PORT))

        QtWidgets.QApplication.setApplicationName(metadata["Formal-Name"])
        app = QtWidgets.QApplication(sys.argv)

        def _shutdown_servers() -> None:
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
