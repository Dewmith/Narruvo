# Narruvo development

- Target Python 3.12, Windows 10/11 x64, and the versions in pyproject.toml.
- Keep the app offline. Network access belongs only in explicit model setup.
- Never commit PDFs, model binaries, generated audio, local databases, or logs.
- Keep PyMuPDF in its dedicated process; never call it from GUI threads.
- Keep Kokoro initialization, hashing, synthesis, and cache maintenance off the GUI thread.
- Workers exchange plain dataclasses/bytes and tagged requests. Never send Qt objects across processes.
- Preserve generation checks and playback intent when changing asynchronous behavior.
- PDF originals stay in place; removing a library entry must not remove the PDF.
- Use pathlib, type annotations, parameterized SQLite statements, and standard logging.
- Run `.venv\Scripts\python.exe -m pytest` after meaningful changes.
- Real model tests are opt-in: `-m integration`; ordinary tests need no model download.
- Validate small-window layout and entry-point launch after UI changes.
- Do not commit, push, or create Git branches unless the user explicitly asks.

