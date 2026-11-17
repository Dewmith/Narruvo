"""One serial process per native library; Qt only receives tagged plain data."""

import logging
import multiprocessing as mp
import queue
from collections import deque
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal


def _process_main(kind: str, commands, results, data_root: str) -> None:
    root = Path(data_root)
    (root / "logs").mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(root / "logs" / f"{kind}-worker.log", encoding="utf-8")],
    )
    service = None
    try:
        if kind == "pdf":
            from voiceleaf.pdf import PdfService
            service = PdfService()
        else:
            from voiceleaf.tts import KokoroEngine
            service = KokoroEngine(root / "audio")
        while True:
            message = commands.get()
            if message is None:
                break
            job_id, operation, arguments = message
            try:
                value = getattr(service, operation)(*arguments)
                results.put((job_id, True, value))
            except Exception as exc:
                logging.getLogger(__name__).exception("%s worker operation %s failed", kind, operation)
                results.put((job_id, False, str(exc)))
    finally:
        if kind == "pdf" and service:
            service.close()


class ProcessWorker(QObject):
    """GUI-side queue for one lazily spawned, serial native service process.

    Requests and results carry job identifiers and plain picklable data.
    Controllers check generations and playback intent when signals arrive.
    """

    result = Signal(int, object)
    failed = Signal(int, str)

    def __init__(self, kind: str, data_root: Path, parent: QObject | None = None):
        super().__init__(parent)
        self.kind, self.data_root = kind, data_root
        self.context = mp.get_context("spawn")
        self.commands = self.context.Queue()
        self.results = self.context.Queue()
        self.process = None
        self.pending: deque = deque()
        self.active: int | None = None
        self.next_id = 0
        self.closed = False
        self.timer = QTimer(self)
        self.timer.setInterval(30)
        self.timer.timeout.connect(self._poll)
        self.timer.start()

    def submit(self, operation: str, *arguments, priority: bool = False) -> int:
        """Queue a service call and return its monotonically increasing job ID.

        Priority changes pending order without interrupting active work.
        Submitting after shutdown raises ``RuntimeError``.
        """
        if self.closed:
            raise RuntimeError("The worker is closed")
        self.next_id += 1
        message = (self.next_id, operation, arguments)
        (self.pending.appendleft if priority else self.pending.append)(message)
        self._dispatch()
        return self.next_id

    def cancel_pending(self, operation: str | None = None) -> list[int]:
        """Remove matching queued calls and return their IDs; active work remains."""
        cancelled = [job[0] for job in self.pending if operation is None or job[1] == operation]
        self.pending = deque(job for job in self.pending if job[0] not in cancelled)
        return cancelled

    def _dispatch(self) -> None:
        if self.active is not None or not self.pending or self.closed:
            return
        if self.process is None:
            self.process = self.context.Process(target=_process_main, args=(self.kind, self.commands, self.results, str(self.data_root)), daemon=True, name=f"voiceleaf-{self.kind}")
            self.process.start()
        message = self.pending.popleft()
        self.active = message[0]
        self.commands.put(message)

    def _poll(self) -> None:
        try:
            while True:
                job_id, success, value = self.results.get_nowait()
                if job_id == self.active:
                    self.active = None
                (self.result if success else self.failed).emit(job_id, value)
        except queue.Empty:
            pass
        if self.process is not None and self.process.exitcode is not None and not self.closed:
            active = self.active
            self.active = None
            self.pending.clear()
            self.process.close()
            self.process = None
            if active is not None:
                self.failed.emit(active, f"The {self.kind} worker stopped unexpectedly. Retry the operation; details are in the logs.")
        self._dispatch()

    def shutdown(self) -> None:
        """Release queues and stop polling, terminating a busy process if necessary."""
        if self.closed:
            return
        self.closed = True
        self.timer.stop()
        self.pending.clear()
        if self.process:
            self.commands.put(None)
            self.process.join(timeout=0.15)
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(timeout=0.5)
            self.process.close()
        for channel in (self.commands, self.results):
            channel.cancel_join_thread()
            channel.close()
