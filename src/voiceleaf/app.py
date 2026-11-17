"""Desktop entry point. No server, account, or network initialization."""

import argparse
import logging
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from voiceleaf.config import AppPaths, Settings
from voiceleaf.logging_setup import configure_logging
from voiceleaf.ui.main_window import VoiceLeafWindow
from voiceleaf.ui.theme import apply_theme


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VoiceLeaf: an offline PDF audiobook reader")
    parser.add_argument("pdf", nargs="?", help="Optional PDF to open")
    checks = parser.add_mutually_exclusive_group()
    checks.add_argument("--smoke-test", action="store_true", help="Open the main window briefly and exit, without first-run setup")
    checks.add_argument("--verify-package", action="store_true", help="Verify native workers offline and exit (no models required)")
    args = parser.parse_args(argv)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("VoiceLeaf")
    app.setOrganizationName("VoiceLeaf")
    apply_theme(app)
    try:
        paths = AppPaths.discover()
        paths.ensure()
        configure_logging(paths.logs)
        if args.verify_package:
            from voiceleaf.package_verification import verify_package
            return verify_package(paths)
        settings = Settings.load(paths.settings_file)
        window = VoiceLeafWindow(paths, settings, args.pdf, show_setup=not args.smoke_test)
    except Exception as exc:
        logging.getLogger(__name__).exception("Startup failed")
        if not (args.smoke_test or args.verify_package):
            QMessageBox.critical(None, "VoiceLeaf could not start", f"Check that the local data folder is writable and dependencies are installed.\n\n{exc}")
        return 1

    def exception_hook(exc_type, value, traceback):
        logging.getLogger(__name__).error("Unhandled UI error", exc_info=(exc_type, value, traceback))
        window.show_error(f"An unexpected error occurred. Details are in the local logs.\n\n{value}")

    sys.excepthook = exception_hook
    window.show()
    if args.smoke_test:
        QTimer.singleShot(2500, window.close)
    logging.getLogger(__name__).info("VoiceLeaf started with Python %s", sys.version.split()[0])
    return app.exec()
