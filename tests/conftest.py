import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture
def sample_pdf(tmp_path):
    import pymupdf

    path = tmp_path / "sample.pdf"
    document = pymupdf.open()
    document.set_metadata({"title": "A small book"})
    for index in range(3):
        page = document.new_page()
        page.insert_text((50, 28), "A recurring header")
        paragraph = (f"Chapter {index + 1}. A leaf turns gently in the morning breeze. "
                     "This book can be read and heard completely offline. ") * 9
        page.insert_textbox(pymupdf.Rect(50, 100, 540, 720), paragraph, fontsize=12)
        page.insert_text((290, 820), str(index + 1))
    document.save(path)
    document.close()
    return path

