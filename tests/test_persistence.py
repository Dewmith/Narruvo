from voiceleaf.domain import PdfInfo, ReadingProgress
from voiceleaf.persistence import Library


def info(path="C:/book.pdf", identity="abc"):
    return PdfInfo(identity, path, "Book's title", 12, ())


def test_database_initializes_and_progress_survives_restart(tmp_path):
    path = tmp_path / "library.sqlite3"
    library = Library(path)
    assert library.recent() == []
    library.upsert(info())
    progress = ReadingProgress(7, 15, 4290, "af_sarah", 0.9, "am_michael", 1.25, "chunkhash")
    library.save_progress("abc", progress)
    library.close()
    reopened = Library(path)
    try:
        assert reopened.get("abc").progress == progress
        assert reopened.recent()[0].title == "Book's title"
        assert reopened.connection.execute("PRAGMA user_version").fetchone()[0] == 1
    finally:
        reopened.close()


def test_reopening_and_relocating_keeps_progress(tmp_path):
    library = Library(tmp_path / "library.sqlite3")
    try:
        library.upsert(info())
        library.save_progress("abc", ReadingProgress(view_page=5))
        restored = library.upsert(info("D:/moved.pdf"))
        assert restored.view_page == 5
        assert library.get("abc").path == "D:/moved.pdf"
        assert len(library.recent()) == 1
    finally:
        library.close()


def test_changed_content_resets_progress_and_remove_keeps_original(tmp_path):
    original = tmp_path / "book.pdf"
    original.write_bytes(b"original")
    library = Library(tmp_path / "library.sqlite3")
    try:
        library.upsert(info(str(original)))
        library.save_progress("abc", ReadingProgress(view_page=9))
        restored = library.upsert(info(str(original), "newhash"))
        assert restored.view_page == 0 and library.get("abc") is None
        library.remove("newhash")
        assert library.recent() == [] and original.read_bytes() == b"original"
    finally:
        library.close()

