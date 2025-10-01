from __future__ import annotations

import importlib.metadata
import json
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

try:
    from virtualoffice.utils.completion_util import generate_text as _generate_persona_text
except Exception:  # pragma: no cover - optional OpenAI support
    _generate_persona_text = None


EMAIL_HOST = os.getenv("VDOS_EMAIL_HOST", "127.0.0.1")
EMAIL_PORT = int(os.getenv("VDOS_EMAIL_PORT", "8000"))
CHAT_HOST = os.getenv("VDOS_CHAT_HOST", "127.0.0.1")
CHAT_PORT = int(os.getenv("VDOS_CHAT_PORT", "8001"))
SIM_HOST = os.getenv("VDOS_SIM_HOST", "127.0.0.1")
SIM_PORT = int(os.getenv("VDOS_SIM_PORT", "8015"))
SIM_BASE_URL = os.getenv("VDOS_SIM_BASE_URL", f"http://{SIM_HOST}:{SIM_PORT}")
LOG_PATH = Path("virtualoffice.log")
DEBUG_AUTOKILL_SECONDS = os.getenv("VDOS_GUI_AUTOKILL_SECONDS")


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




class PersonDialog(QtWidgets.QDialog):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create Persona")
        self.resize(520, 720)
        self._payload: Optional[dict[str, Any]] = None

        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()

        self.name_input = QtWidgets.QLineEdit()
        self.role_input = QtWidgets.QLineEdit()
        self.timezone_input = QtWidgets.QLineEdit()
        self.work_hours_input = QtWidgets.QLineEdit()
        self.break_frequency_input = QtWidgets.QLineEdit()
        self.communication_style_input = QtWidgets.QLineEdit()
        self.email_input = QtWidgets.QLineEdit()
        self.chat_handle_input = QtWidgets.QLineEdit()
        self.department_head_checkbox = QtWidgets.QCheckBox("Is department head")
        self.skills_input = QtWidgets.QLineEdit()
        self.personality_input = QtWidgets.QLineEdit()
        self.objectives_input = QtWidgets.QPlainTextEdit()
        self.metrics_input = QtWidgets.QPlainTextEdit()
        self.schedule_input = QtWidgets.QPlainTextEdit()
        self.schedule_input.setPlaceholderText("09:00-10:00 Stand-up & triage")
        self.planning_guidelines_input = QtWidgets.QPlainTextEdit()
        self.event_playbook_input = QtWidgets.QPlainTextEdit()
        self.event_playbook_input.setPlaceholderText('{"campaign": ["Email client", "Prepare deck"]}')
        self.statuses_input = QtWidgets.QPlainTextEdit()

        form.addRow("Name", self.name_input)
        form.addRow("Role", self.role_input)
        form.addRow("Timezone", self.timezone_input)
        form.addRow("Work hours", self.work_hours_input)
        form.addRow("Break frequency", self.break_frequency_input)
        form.addRow("Communication style", self.communication_style_input)
        form.addRow("Email", self.email_input)
        form.addRow("Chat handle", self.chat_handle_input)
        form.addRow(self.department_head_checkbox)
        form.addRow("Skills (comma separated)", self.skills_input)
        form.addRow("Personality (comma separated)", self.personality_input)
        form.addRow("Objectives (one per line)", self.objectives_input)
        form.addRow("Metrics (one per line)", self.metrics_input)
        form.addRow("Schedule (one per line)", self.schedule_input)
        form.addRow("Planning guidelines (one per line)", self.planning_guidelines_input)
        form.addRow("Event playbook (JSON)", self.event_playbook_input)
        form.addRow("Statuses (one per line)", self.statuses_input)

        layout.addLayout(form)

        self.prompt_input = QtWidgets.QLineEdit()
        self.prompt_input.setPlaceholderText("Describe the persona (e.g., 'Full stack developer focused on dashboards')")
        layout.addWidget(QtWidgets.QLabel("AI prompt (optional)"))
        layout.addWidget(self.prompt_input)

        self.generate_button = QtWidgets.QPushButton("Generate with GPT-4o")
        self.generate_button.clicked.connect(self.generate_with_ai)
        layout.addWidget(self.generate_button)
        if _generate_persona_text is None:
            self.generate_button.setEnabled(False)
            self.generate_button.setToolTip("OpenAI support is not configured")

        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def generate_with_ai(self) -> None:
        if _generate_persona_text is None:
            QtWidgets.QMessageBox.information(self, "Unavailable", "OpenAI support is not configured.")
            return
        prompt = self.prompt_input.text().strip()
        if not prompt:
            QtWidgets.QMessageBox.warning(self, "Missing prompt", "Enter a short description before generating.")
            return
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            system_content = (
                "You create JSON personas for a workplace simulation. "
                "Return only JSON matching this schema: {"
                "\"name\", \"role\", \"timezone\", \"work_hours\", \"break_frequency\", \"communication_style\", "
                "\"email_address\", \"chat_handle\", \"is_department_head\" (bool), "
                "\"skills\" (list of strings), \"personality\" (list), \"objectives\" (list), \"metrics\" (list), "
                "\"schedule\" (list of {start, end, activity}), \"planning_guidelines\" (list), "
                "\"event_playbook\" (object mapping scenario -> list of steps), \"statuses\" (list). "
                "Ensure times are 24h format like 09:00."
            )
            messages = [
                {"role": "system", "content": system_content},
                {"role": "user", "content": prompt},
            ]
            raw_content, _ = _generate_persona_text(messages, model="gpt-4o")
            content = raw_content.strip()
            if content.startswith("```"):
                content = content.split("```", 2)[1]
                if content.startswith("json"):
                    content = content[4:]
            data = json.loads(content)
            self.populate_fields(data)
        except Exception as exc:  # pragma: no cover - UI safeguard
            QtWidgets.QMessageBox.critical(self, "Generation failed", f"Could not generate persona: {exc}")
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()

    def populate_fields(self, data: dict[str, Any]) -> None:
        self.name_input.setText(data.get("name", ""))
        self.role_input.setText(data.get("role", ""))
        self.timezone_input.setText(data.get("timezone", ""))
        self.work_hours_input.setText(data.get("work_hours", ""))
        self.break_frequency_input.setText(data.get("break_frequency", ""))
        self.communication_style_input.setText(data.get("communication_style", ""))
        self.email_input.setText(data.get("email_address", ""))
        self.chat_handle_input.setText(data.get("chat_handle", ""))
        self.department_head_checkbox.setChecked(bool(data.get("is_department_head", False)))
        self.skills_input.setText(", ".join(data.get("skills", [])))
        self.personality_input.setText(", ".join(data.get("personality", [])))
        self.objectives_input.setPlainText("\n".join(data.get("objectives", [])))
        self.metrics_input.setPlainText("\n".join(data.get("metrics", [])))
        schedule_lines = []
        for block in data.get("schedule", []) or []:
            start = block.get("start", "")
            end = block.get("end", "")
            activity = block.get("activity", "")
            if start and end:
                schedule_lines.append(f"{start}-{end} {activity}")
        self.schedule_input.setPlainText("\n".join(schedule_lines))
        self.planning_guidelines_input.setPlainText("\n".join(data.get("planning_guidelines", [])))
        event_playbook = data.get("event_playbook") or {}
        try:
            self.event_playbook_input.setPlainText(json.dumps(event_playbook, indent=2))
        except TypeError:
            self.event_playbook_input.setPlainText(str(event_playbook))
        self.statuses_input.setPlainText("\n".join(data.get("statuses", [])))

    def person_payload(self) -> dict[str, Any]:
        if self._payload is not None:
            return self._payload
        name = self.name_input.text().strip()
        role = self.role_input.text().strip()
        timezone = self.timezone_input.text().strip()
        work_hours = self.work_hours_input.text().strip()
        break_frequency = self.break_frequency_input.text().strip()
        communication_style = self.communication_style_input.text().strip()
        email = self.email_input.text().strip()
        chat = self.chat_handle_input.text().strip()
        if not all([name, role, timezone, work_hours, break_frequency, communication_style, email, chat]):
            raise ValueError("Fill in all required fields (name, role, timezone, work hours, break, communication, email, chat).")
        skills = _split_csv(self.skills_input.text())
        personality = _split_csv(self.personality_input.text())
        if not skills or not personality:
            raise ValueError("Provide at least one skill and one personality trait.")
        objectives = _split_lines(self.objectives_input.toPlainText()) or None
        metrics = _split_lines(self.metrics_input.toPlainText()) or None
        planning = _split_lines(self.planning_guidelines_input.toPlainText()) or None
        statuses = _split_lines(self.statuses_input.toPlainText()) or None
        schedule = _parse_schedule(self.schedule_input.toPlainText())
        playbook_text = self.event_playbook_input.toPlainText().strip()
        event_playbook = None
        if playbook_text:
            try:
                event_playbook = json.loads(playbook_text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Event playbook must be valid JSON: {exc}")
        payload: dict[str, Any] = {
            "name": name,
            "role": role,
            "timezone": timezone,
            "work_hours": work_hours,
            "break_frequency": break_frequency,
            "communication_style": communication_style,
            "email_address": email,
            "chat_handle": chat,
            "skills": skills,
            "personality": personality,
        }
        if objectives:
            payload["objectives"] = objectives
        if metrics:
            payload["metrics"] = metrics
        if schedule:
            payload["schedule"] = schedule
        if planning:
            payload["planning_guidelines"] = planning
        if event_playbook:
            payload["event_playbook"] = event_playbook
        if statuses:
            payload["statuses"] = statuses
        payload["is_department_head"] = self.department_head_checkbox.isChecked()
        self._payload = payload
        return payload

    def accept(self) -> None:
        try:
            self._payload = self.person_payload()
        except ValueError as exc:
            QtWidgets.QMessageBox.warning(self, "Invalid input", str(exc))
            return
        super().accept()


def _split_csv(raw: str) -> List[str]:
    return [item.strip() for item in raw.split(',') if item.strip()]


def _split_lines(raw: str) -> List[str]:
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _parse_schedule(raw: str) -> List[dict[str, str]]:
    schedule: List[dict[str, str]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(' ', 1)
        times = parts[0]
        if '-' not in times:
            raise ValueError(f"Schedule line must contain start-end times: {line}")
        start, end = times.split('-', 1)
        activity = parts[1].strip() if len(parts) > 1 else "Focus work"
        schedule.append({"start": start.strip(), "end": end.strip(), "activity": activity})
    return schedule

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
        self._selected_participant_ids: set[int] = set()
        self._sim_online = False

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
        self.department_head_combo = QtWidgets.QComboBox()
        self.department_head_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToContents)
        self.department_head_combo.addItem("Auto-select department head", None)
        self.department_head_combo.setEnabled(False)
        self.model_hint_input = QtWidgets.QLineEdit()
        self.random_seed_input = QtWidgets.QLineEdit()
        self.random_seed_input.setPlaceholderText("Optional")

        self.participant_list = QtWidgets.QListWidget()
        self.participant_list.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.participant_list.setAlternatingRowColors(True)
        self.participant_list.setFixedHeight(120)

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
        controls_layout.addWidget(self.department_head_combo, 7, 1, 1, 2)
        controls_layout.addWidget(QtWidgets.QLabel("Model Hint:"), 8, 0)
        controls_layout.addWidget(self.model_hint_input, 8, 1, 1, 2)
        controls_layout.addWidget(QtWidgets.QLabel("Random Seed:"), 9, 0)
        controls_layout.addWidget(self.random_seed_input, 9, 1)
        controls_layout.addWidget(self.seed_button, 10, 0, 1, 4)
        controls_layout.addWidget(QtWidgets.QLabel("Active Personas:"), 11, 0)
        controls_layout.addWidget(self.participant_list, 11, 1, 1, 3)

        reports_header = QtWidgets.QHBoxLayout()
        reports_header.addWidget(QtWidgets.QLabel("Person:"))
        self.person_combo = QtWidgets.QComboBox()
        self.person_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToContents)
        reports_header.addWidget(self.person_combo)
        self.refresh_people_button = QtWidgets.QPushButton("Refresh People")
        reports_header.addWidget(self.refresh_people_button)
        self.refresh_reports_button = QtWidgets.QPushButton("Refresh Reports")
        reports_header.addWidget(self.refresh_reports_button)
        self.create_person_button = QtWidgets.QPushButton("Create Person")
        reports_header.addWidget(self.create_person_button)
        self.current_task_label = QtWidgets.QLabel("Current task: —")
        reports_header.addWidget(self.current_task_label)
        reports_header.addStretch(1)

        self.report_tabs = QtWidgets.QTabWidget()
        self.daily_reports_view = QtWidgets.QPlainTextEdit()
        self.daily_reports_view.setReadOnly(True)
        self.simulation_reports_view = QtWidgets.QPlainTextEdit()
        self.simulation_reports_view.setReadOnly(True)
        self.token_usage_view = QtWidgets.QPlainTextEdit()
        self.token_usage_view.setReadOnly(True)
        self.hourly_plan_view = QtWidgets.QPlainTextEdit()
        self.hourly_plan_view.setReadOnly(True)
        self.events_view = QtWidgets.QPlainTextEdit()
        self.events_view.setReadOnly(True)
        self.report_tabs.addTab(self.daily_reports_view, "Daily Reports")
        self.report_tabs.addTab(self.simulation_reports_view, "Simulation Reports")
        self.report_tabs.addTab(self.token_usage_view, "Token Usage")
        self.report_tabs.addTab(self.hourly_plan_view, "Hourly Plan")
        self.report_tabs.addTab(self.events_view, "Events")

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
        self.create_person_button.clicked.connect(self.show_create_person_dialog)
        self.person_combo.currentIndexChanged.connect(self._on_person_changed)
        self.participant_list.itemChanged.connect(self._on_participant_item_changed)

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
            if name == "sim":
                self._sim_online = False
        else:
            state = "running" if self.is_running_cb(name) else "stopped"
            self.status_label.setText(f"{config['label']} {state}.")
        self.update_server_buttons()
        if name == "sim":
            if self.is_running_cb("sim"):
                self.refresh_state()
                self.refresh_people()
            else:
                self._sim_online = False
                self._set_simulation_controls_enabled(self._sim_available())

    def update_server_buttons(self) -> None:
        for name in SERVER_ORDER:
            config = self.server_config[name]
            running = self.is_running_cb(name)
            status_text = "running" if running else "stopped"
            self.server_status_labels[name].setText(f"{status_text} on {config['host']}:{config['port']}")
            self.server_start_buttons[name].setEnabled(not running)
            self.server_stop_buttons[name].setEnabled(running)

        sim_available = self._sim_available()
        self._set_simulation_controls_enabled(sim_available)
        if not sim_available:
            self.status_label.setText("Simulation server offline. Start it above or connect an external instance.")

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
        summary: dict[str, Any] = {}
        if payload:
            summary = {
                "project_name": payload.get("project_name"),
                "include_count": len(payload.get("include_person_ids", [])),
                "exclude_count": len(payload.get("exclude_person_ids", [])),
                "random_seed": payload.get("random_seed"),
                "model_hint": payload.get("model_hint"),
            }
        logger.info("GUI issuing simulation start request: %s", summary)
        try:
            response = self.http_client.post("/api/v1/simulation/start", json=payload, timeout=20)
            response.raise_for_status()
            data = response.json()
            logger.info("Simulation start succeeded: is_running=%s tick=%s", data.get("is_running"), data.get("current_tick"))
            return data
        except httpx.TimeoutException:
            logger.error("Simulation start request timed out after 20s")
            raise RuntimeError("Simulation start timed out; planner may be busy. Try again or enable the stub planner.")


    def _stop(self) -> dict:
        response = self.http_client.post("/api/v1/simulation/stop", timeout=20)
        response.raise_for_status()
        return response.json()

    def _state(self) -> dict:
        response = self.http_client.get("/api/v1/simulation", timeout=20)
        response.raise_for_status()
        return response.json()

    def _advance(self, ticks: int, reason: str) -> dict:
        payload = {"ticks": ticks, "reason": reason}
        response = self.http_client.post("/api/v1/simulation/advance", json=payload, timeout=20)
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
        response = self.http_client.post("/api/v1/people", json=payload, timeout=20)
        response.raise_for_status()
        return response.json()

    def _create_person(self, payload: dict) -> dict:
        response = self.http_client.post("/api/v1/people", json=payload, timeout=20)
        response.raise_for_status()
        return response.json()

    def show_create_person_dialog(self) -> None:
        if not self._sim_available():
            self.status_label.setText("Simulation server offline. Start it above.")
            return
        dialog = PersonDialog(self)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            try:
                payload = dialog.person_payload()
            except ValueError as exc:
                self.status_label.setText(f"Invalid input: {exc}")
                return
            self.status_label.setText("Creating persona…")
            self._run_request(lambda: self._create_person(payload), self._handle_create_person_response)

    def _handle_create_person_response(self, result: Optional[dict], error: Optional[Exception]) -> None:
        if error:
            self.status_label.setText(f"Create person failed: {error}")
            return
        person = result or {}
        self.status_label.setText(f"Created worker: {person.get('name', 'unknown')}")
        self.refresh_people()

    def refresh_people(self) -> None:
        if not self._sim_available():
            self.person_combo.blockSignals(True)
            self.person_combo.clear()
            self.person_combo.addItem("Simulation offline", None)
            self.person_combo.setEnabled(False)
            self.person_combo.blockSignals(False)
            self._populate_participant_list([])
            self._refresh_department_head_options([])
            return
        self._run_request(self._load_people, self._handle_people_response)

    def refresh_reports(self) -> None:
        if not self._sim_available():
            message = "Simulation server offline."
            self.daily_reports_view.setPlainText(message)
            self.simulation_reports_view.setPlainText(message)
            self.token_usage_view.setPlainText(message)
            self.hourly_plan_view.setPlainText(message)
            self.events_view.setPlainText(message)
            self.current_task_label.setText("Current task: —")
            return
        person_id = self._selected_person_id()
        if person_id is None:
            self.daily_reports_view.setPlainText("Select a persona to view daily reports.")
            self.simulation_reports_view.clear()
            self.token_usage_view.clear()
            self.hourly_plan_view.clear()
            self.events_view.clear()
            self.current_task_label.setText("Current task: —")
            return
        self._run_request(lambda: self._fetch_reports(person_id), self._handle_reports_response)

    def _load_people(self) -> List[dict]:
        response = self.http_client.get("/api/v1/people")
        response.raise_for_status()
        return response.json()

    def _handle_people_response(self, result: Optional[List[dict]], error: Optional[Exception]) -> None:
        self.person_combo.blockSignals(True)
        if error:
            self.people_cache = []
            self.person_combo.clear()
            self.person_combo.addItem(f"People load failed: {error}", None)
            self.person_combo.setEnabled(False)
            self._populate_participant_list([])
            self._refresh_department_head_options([])
        else:
            people = result or []
            self.people_cache = people
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
            self._populate_participant_list(people)
            self._refresh_department_head_options(people)
        self.person_combo.blockSignals(False)
        if not error and self.people_cache:
            self.refresh_reports()
        elif not self.people_cache:
            self.daily_reports_view.setPlainText("No daily reports yet.")
            self.simulation_reports_view.clear()
            self.token_usage_view.clear()
            self.hourly_plan_view.clear()
            self.events_view.clear()
            self.current_task_label.setText("Current task: ?")

    def _refresh_department_head_options(self, people: List[dict]) -> None:
        previous = self.department_head_combo.currentData()
        self.department_head_combo.blockSignals(True)
        self.department_head_combo.clear()
        self.department_head_combo.addItem("Auto-select department head", None)
        self.department_head_combo.setEnabled(False)
        if not people:
            self.department_head_combo.setEnabled(False)
            self.department_head_combo.blockSignals(False)
            return
        self.department_head_combo.setEnabled(True)
        available_names = {person['name'] for person in people}
        preferred = previous if isinstance(previous, str) and previous in available_names else None
        if preferred is None:
            head = next((person for person in people if person.get('is_department_head')), None)
            if head is not None:
                preferred = head['name']
        if preferred is None and people:
            preferred = people[0]['name']
        for person in people:
            label = f"{person['name']} ({person.get('role', 'Role unknown')})"
            self.department_head_combo.addItem(label, person['name'])
        if preferred is not None:
            index = self.department_head_combo.findData(preferred)
            if index != -1:
                self.department_head_combo.setCurrentIndex(index)
            else:
                self.department_head_combo.setCurrentIndex(0)
        else:
            self.department_head_combo.setCurrentIndex(0)
        self.department_head_combo.blockSignals(False)

    def _populate_participant_list(self, people: List[dict]) -> None:
        self.participant_list.blockSignals(True)
        self.participant_list.clear()
        if not people:
            placeholder = QtWidgets.QListWidgetItem('No personas available')
            placeholder.setFlags(QtCore.Qt.ItemIsEnabled)
            self.participant_list.addItem(placeholder)
            self.participant_list.setEnabled(False)
            self._selected_participant_ids.clear()
        else:
            self.participant_list.setEnabled(True)
            current_ids = {person['id'] for person in people}
            if self._selected_participant_ids:
                checked_ids = {pid for pid in self._selected_participant_ids if pid in current_ids}
                if not checked_ids:
                    checked_ids = current_ids
            else:
                checked_ids = current_ids
            self._selected_participant_ids = set(checked_ids)
            for person in people:
                label = f"{person['name']} ({person.get('role', 'Role unknown')})"
                item = QtWidgets.QListWidgetItem(label)
                item.setData(QtCore.Qt.UserRole, int(person['id']))
                item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
                state = QtCore.Qt.Checked if person['id'] in checked_ids else QtCore.Qt.Unchecked
                item.setCheckState(state)
                self.participant_list.addItem(item)
        self.participant_list.blockSignals(False)

    def _collect_participant_selection(self) -> tuple[list[int], list[int]]:
        selected: list[int] = []
        deselected: list[int] = []
        for index in range(self.participant_list.count()):
            item = self.participant_list.item(index)
            person_id = item.data(QtCore.Qt.UserRole)
            if person_id is None:
                continue
            if item.checkState() == QtCore.Qt.Checked:
                selected.append(int(person_id))
            else:
                deselected.append(int(person_id))
        self._selected_participant_ids = set(selected)
        return selected, deselected

    def _on_participant_item_changed(self, item: QtWidgets.QListWidgetItem) -> None:
        person_id = item.data(QtCore.Qt.UserRole)
        if person_id is None:
            return
        if item.checkState() == QtCore.Qt.Checked:
            self._selected_participant_ids.add(int(person_id))
        else:
            self._selected_participant_ids.discard(int(person_id))

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
        hourly = self.http_client.get(f"/api/v1/people/{person_id}/plans", params={"plan_type": "hourly", "limit": 1})
        hourly.raise_for_status()
        events = self.http_client.get("/api/v1/events")
        events.raise_for_status()
        return {"daily": daily.json(), "simulation": simulation.json(), "usage": usage.json(), "hourly": hourly.json(), "events": events.json()}

    def _handle_reports_response(self, result: Optional[Dict[str, Any]], error: Optional[Exception]) -> None:
        if error:
            message = f"Failed to load reports: {error}"
            self.daily_reports_view.setPlainText(message)
            self.simulation_reports_view.clear()
            self.token_usage_view.clear()
            self.hourly_plan_view.clear()
            self.events_view.clear()
            self.current_task_label.setText("Current task: —")
            return
        payload = result or {}
        self.daily_reports_view.setPlainText(self._format_daily_reports(payload.get("daily", [])))
        self.simulation_reports_view.setPlainText(self._format_simulation_reports(payload.get("simulation", [])))
        self.token_usage_view.setPlainText(self._format_token_usage(payload.get("usage") or {}))
        self.hourly_plan_view.setPlainText(self._format_hourly_plan(payload.get("hourly", [])))
        self.events_view.setPlainText(self._format_events(payload.get("events", [])))
        self._update_current_task(payload.get("hourly", []))

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
        return "\n".join(lines)

    def _format_hourly_plan(self, plans: List[dict]) -> str:
        if not plans:
            return "No hourly plan recorded yet."
        plan = plans[0]
        content = plan.get('content', '') or ''
        meta = f"Tick {plan.get('tick', '?')} (model={plan.get('model_used')}, tokens={plan.get('tokens_used')})"
        return f"{meta}\n\n{content}".strip()

    def _format_events(self, events: List[dict]) -> str:
        if not events:
            return "No events recorded yet."
        lines: List[str] = []
        for event in events[-10:]:
            targets = ', '.join(str(t) for t in event.get('target_ids', [])) or 'all'
            lines.append(f"#{event['id']} tick={event.get('at_tick')} type={event.get('type')} targets={targets}")
            payload = event.get('payload') or {}
            if payload:
                lines.append(f"  payload: {payload}")
        return "\n".join(lines)

    def _update_current_task(self, plans: List[dict]) -> None:
        task = "—"
        if plans:
            content = plans[0].get('content', '') or ''
            for line in content.splitlines():
                stripped = line.strip().lstrip('-•').strip()
                if stripped:
                    task = stripped
                    break
        self.current_task_label.setText(f"Current task: {task}")

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
        if not self.people_cache:
            self.status_label.setText("Add personas before starting the simulation.")
            return
        payload: Dict[str, Any] = {
            "project_name": project_name,
            "project_summary": project_summary,
            "duration_weeks": self.project_duration_spin.value(),
        }
        selected_ids, deselected_ids = self._collect_participant_selection()
        if not selected_ids:
            self.status_label.setText("Select at least one persona to include in the simulation.")
            return
        if selected_ids and len(selected_ids) != len(self.people_cache):
            payload["include_person_ids"] = selected_ids
        if deselected_ids:
            payload["exclude_person_ids"] = deselected_ids
        department_head = self.department_head_combo.currentData()
        if isinstance(department_head, str) and department_head:
            payload["department_head_name"] = department_head
        model_hint = self.model_hint_input.text().strip()
        if model_hint:
            payload["model_hint"] = model_hint
        seed_text = self.random_seed_input.text().strip()
        if seed_text:
            try:
                payload["random_seed"] = int(seed_text)
            except ValueError:
                self.status_label.setText("Random seed must be an integer value.")
                return
        self.status_label.setText("Simulation state: starting?")
        self._run_request(lambda: self._start(payload), self._handle_state_response)

    def stop_simulation(self) -> None:
        if not self._sim_available():
            self.status_label.setText("Simulation server offline. Start it above.")
            return
        self.status_label.setText("Simulation state: stopping…")
        self._run_request(self._stop, self._handle_state_response)

    def refresh_state(self) -> None:
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
            if isinstance(error, httpx.HTTPStatusError):
                self._sim_online = True
            elif isinstance(error, httpx.RequestError) and not self.is_running_cb("sim"):
                self._sim_online = False
            self._set_simulation_controls_enabled(self._sim_available())
            return
        state = result or {}
        self._sim_online = True
        running = "running" if state.get("is_running") else "stopped"
        tick = state.get("current_tick", 0)
        sim_time = state.get("sim_time", "Day 0 00:00")
        self.status_label.setText(f"Simulation state: {running} (tick {tick}, {sim_time})")
        self._set_simulation_controls_enabled(self._sim_available())
        self.refresh_people()
        self.refresh_reports()

    def _handle_advance_response(self, result: Optional[dict], error: Optional[Exception]) -> None:
        if error:
            self.status_label.setText(f"Advance failed: {error}")
            return
        summary = result or {}
        tick = summary.get("current_tick", "?")
        sim_time = summary.get("sim_time", "Day 0 00:00")
        emails = summary.get("emails_sent", 0)
        chats = summary.get("chat_messages_sent", 0)
        self.status_label.setText(f"Advanced to tick {tick} ({sim_time}) — emails {emails}, chats {chats}")
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
            self.log_view.setPlainText("\n".join(lines))
            cursor = self.log_view.textCursor()
            cursor.movePosition(QtGui.QTextCursor.End)
            self.log_view.setTextCursor(cursor)
        else:
            self.log_view.setPlainText("Log file not found yet.")

    def _set_simulation_controls_enabled(self, enabled: bool) -> None:
        widgets = [
            self.start_button,
            self.stop_button,
            self.advance_button,
            self.seed_button,
            self.tick_spin,
            self.reason_input,
            self.project_name_input,
            self.project_summary_input,
            self.project_duration_spin,
            self.department_head_combo,
            self.model_hint_input,
            self.random_seed_input,
            self.refresh_people_button,
            self.refresh_reports_button,
            self.participant_list,
            self.person_combo,
        ]
        for widget in widgets:
            widget.setEnabled(enabled)
        self.refresh_button.setEnabled(True)

    def _sim_available(self) -> bool:
        return self.is_running_cb("sim") or self._sim_online

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
    sys.stdout.write("Starting virtualoffice application...\n")
    app_module = sys.modules["__main__"].__package__
    metadata = importlib.metadata.metadata(app_module)

    main_window: Optional[virtualOffice] = None
    exit_code = 0
    try:
        QtWidgets.QApplication.setApplicationName(metadata["Formal-Name"])
        app = QtWidgets.QApplication(sys.argv)

        debug_timeout = None
        if DEBUG_AUTOKILL_SECONDS:
            try:
                debug_timeout = max(0, int(DEBUG_AUTOKILL_SECONDS))
            except ValueError:
                logger.warning(
                    "Ignoring invalid VDOS_GUI_AUTOKILL_SECONDS=%r", DEBUG_AUTOKILL_SECONDS
                )
                debug_timeout = None

        if debug_timeout:
            logger.info("Debug auto-shutdown enabled: exiting after %s seconds", debug_timeout)

            def _trigger_autokill() -> None:
                logger.info("Debug auto-shutdown timer fired; quitting application")
                app.quit()

            QtCore.QTimer.singleShot(debug_timeout * 1000, _trigger_autokill)

        logger.info("GUI ready; start services from the dashboard when needed.")

        main_window = virtualOffice()
        app.aboutToQuit.connect(main_window.stop_all_servers)
        main_window.show()
        exit_code = app.exec()
    finally:
        if main_window is not None:
            main_window.stop_all_servers()
        logger.info("virtualoffice application exited.")
        logger.info("Log saved to virtualoffice.log")

    sys.exit(exit_code)
