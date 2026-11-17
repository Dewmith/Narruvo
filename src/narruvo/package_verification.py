"""Bounded, offline verification through the application's real worker protocol."""

import logging
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QEventLoop, QTimer

from narruvo.config import AppPaths
from narruvo.domain import PackageCheckResult
from narruvo.workers import ProcessWorker

log = logging.getLogger(__name__)


def verify_package(paths: AppPaths, *, timeout_ms: int = 60_000) -> int:
    """Return 0 only after both isolated native workers report success."""
    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)
    workers: list[ProcessWorker] = []
    pending = {"pdf", "tts"}
    errors: list[str] = []

    def fail(message: str) -> None:
        errors.append(message)
        log.error("Package verification failed: %s", message)
        loop.quit()

    def completed(component: str, result: object) -> None:
        if not isinstance(result, PackageCheckResult) or result.component != component:
            fail(f"Unexpected verification result from {component}")
            return
        log.info("Package check %s: %s", component, result.detail)
        pending.discard(component)
        if not pending:
            loop.quit()

    timer.timeout.connect(lambda: fail(f"Timed out waiting for {', '.join(sorted(pending))}"))
    try:
        paths.ensure()
        with TemporaryDirectory(prefix="package-check-", dir=paths.root) as directory:
            try:
                for component in ("pdf", "tts"):
                    worker = ProcessWorker(component, Path(directory))
                    workers.append(worker)
                    worker.result.connect(lambda _job, result, name=component: completed(name, result))
                    worker.failed.connect(lambda _job, message, name=component: fail(f"{name}: {message}"))
                    arguments = (directory,) if component == "pdf" else (os.getenv("NARRUVO_TEST_MODELS") or None,)
                    worker.submit("verify_runtime", *arguments)
                timer.start(timeout_ms)
                loop.exec()
            finally:
                timer.stop()
                for worker in workers:
                    worker.shutdown()
                if errors or pending:
                    for path in (Path(directory) / "logs").glob("*.log"):
                        log.error("%s:\n%s", path.name, path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        log.exception("Package verification could not complete")
        return 1
    if errors or pending:
        return 1
    log.info("Package verification passed")
    return 0
