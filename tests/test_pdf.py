import pytest

from narruvo.pdf import PdfError, PdfService


def test_extract_render_and_finalize_real_pdf(sample_pdf):
    service = PdfService()
    try:
        info = service.open(str(sample_pdf))
        assert info.title == "A small book" and info.page_count == 3
        assert len(info.document_id) == 64
        for index in range(info.page_count):
            page = service.extract(index)
            assert page.page_index == index and page.blocks
        pages, chunks = service.finalize()
        assert "morning breeze" in pages[0][1]
        assert all("recurring header" not in text.lower() for _, text in pages)
        assert {chunk.page_index for chunk in chunks} == {0, 1, 2}
        rendered = service.render(1, 1.0)
        assert rendered.width > 0 and rendered.height > 0
        assert len(rendered.samples) == rendered.height * rendered.stride
        with pytest.raises(PdfError, match="outside"):
            service.render(99, 1)
    finally:
        service.close()


def test_missing_and_invalid_files(tmp_path):
    service = PdfService()
    with pytest.raises(PdfError, match="found"):
        service.open(str(tmp_path / "missing.pdf"))
    corrupt = tmp_path / "corrupt.pdf"
    corrupt.write_bytes(b"%PDF-1.7\nthis is not a PDF")
    with pytest.raises(PdfError, match="corrupt|opened"):
        service.open(str(corrupt))
    assert service.document is None


def test_encrypted_pdf_reports_password(tmp_path):
    import pymupdf
    path = tmp_path / "protected.pdf"
    with pymupdf.open() as document:
        document.new_page().insert_text((50, 80), "Secret")
        document.save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="secret")
    service = PdfService()
    with pytest.raises(PdfError, match="password protected"):
        service.open(str(path))
    assert service.document is None


def test_image_only_and_blank_pdf_have_no_narration(tmp_path):
    import pymupdf
    path = tmp_path / "scanned.pdf"
    with pymupdf.open() as document:
        page = document.new_page()
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20), False)
        pix.clear_with(128)
        page.insert_image(pymupdf.Rect(30, 40, 500, 700), pixmap=pix)
        document.new_page()
        document.save(path)
    service = PdfService()
    try:
        service.open(str(path))
        service.extract(0)
        service.extract(1)
        pages, chunks = service.finalize()
        assert pages == [(0, ""), (1, "")] and chunks == []
        assert service.render(0, 0.4).samples
    finally:
        service.close()


def test_columns_in_a_real_pdf(tmp_path):
    import pymupdf
    path = tmp_path / "columns.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=600, height=800)
        for x, y, text in [(330, 110, "Right first"), (40, 110, "Left first"), (330, 220, "Right second"), (40, 220, "Left second")]:
            page.insert_text((x, y), text)
        document.save(path)
    service = PdfService()
    try:
        service.open(str(path))
        service.extract(0)
        pages, _ = service.finalize()
        assert pages[0][1].index("Left second") < pages[0][1].index("Right first")
    finally:
        service.close()

