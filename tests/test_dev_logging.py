import io
import sys
from pathlib import Path

import virtualoffice.common.dev_logging as dev_logging


def _cleanup_stdio(original_stdout: io.TextIOBase, original_stderr: io.TextIOBase) -> None:
    """Restore stdio and close any open log file from dev_logging."""
    dev_logging._close_log_file()  # type: ignore[attr-defined]
    sys.stdout = original_stdout
    sys.stderr = original_stderr


def test_init_dev_logging_creates_log_and_mirrors(monkeypatch, tmp_path):
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    monkeypatch.chdir(tmp_path)
    env = {
        "VDOS_CHAT_HOST": "127.0.0.1",
        "VDOS_CHAT_PORT": "8001",
        "VDOS_EMAIL_HOST": "127.0.0.1",
        "VDOS_EMAIL_PORT": "8000",
        "VDOS_SIM_HOST": "127.0.0.1",
        "VDOS_SIM_PORT": "8015",
        "VDOS_DB_PATH": "src/virtualoffice/vdos.db",
        "OPENAI_API_KEY": "sk-test",
        "VDOS_LOG_DIR": str(tmp_path / "logs"),
    }

    try:
        dev_logging.init_dev_logging(env=env)
        log_dir = Path(tmp_path) / "logs"
        log_files = list(log_dir.glob("*_briefcase_dev.log"))
        assert len(log_files) == 1

        print("hello stdout")
        print("한글")  # non-ASCII should be preserved
        sys.stderr.write("stderr-line\n")
        sys.stdout.flush()
        sys.stderr.flush()

        contents = log_files[0].read_text(encoding="utf-8")
        assert "hello stdout" in contents
        assert "한글" in contents
        assert "stderr-line" in contents
        assert "VDOS_CHAT_PORT: 8001" in contents
        assert "OPENAI_API_KEY: [set]" in contents
    finally:
        _cleanup_stdio(original_stdout, original_stderr)


def test_init_dev_logging_respects_disable_flag(monkeypatch, tmp_path):
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    monkeypatch.chdir(tmp_path)
    env = {"VDOS_DEV_LOGGING_ENABLED": "false", "OPENAI_API_KEY": "sk-test"}

    try:
        dev_logging.init_dev_logging(env=env)
        assert sys.stdout is original_stdout
        assert sys.stderr is original_stderr
        assert not (Path(tmp_path) / "logs").exists()
    finally:
        _cleanup_stdio(original_stdout, original_stderr)


def test_tee_stdout_handles_log_failures_once():
    original = io.StringIO()

    class FailingWriter(io.StringIO):
        def write(self, s: str) -> int:  # type: ignore[override]
            raise IOError("boom")

        def flush(self) -> None:  # type: ignore[override]
            pass

    failing = FailingWriter()
    tee = dev_logging.TeeStream(original, failing)

    tee.write("first")
    tee.write("second")
    tee.flush()

    content = original.getvalue()
    assert "first" in content and "second" in content
    assert content.count("[VDOS-DEV-LOG] Logging to file disabled: boom") == 1
