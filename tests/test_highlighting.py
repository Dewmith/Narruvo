from types import SimpleNamespace

import pytest

from narruvo.domain import PageText, PdfInfo, PdfLine, ReadingLine, SpeechCue, TextBlock, TextChunk
from narruvo.pdf import PdfService, RenderedPage
from narruvo.text import chunk_prepared_pages, prepare_pages
from narruvo.timing import align_cues, estimated_cues
from narruvo.ui.viewer import PdfViewer


def timed(phonemes, step=0.05):
    return [SimpleNamespace(phoneme=char, start=index * step, end=(index + 1) * step) for index, char in enumerate(phonemes)]


def test_phoneme_alignment_preserves_number_and_context_word_boundaries():
    text = "The 123 cats."
    spoken = "ði wʌnhʌndɹəd twɛnti θɹiː kæts."
    cues, estimated = align_cues(text, timed(spoken), ["ðə", "wʌnhʌndɹəd twɛnti θɹiː", "kæts."], round(len(spoken) * 50))
    assert not estimated
    assert [text[cue.text_start:cue.text_end] for cue in cues] == ["The", "123", "cats."]
    assert cues[1].start_ms == spoken.index("w") * 50
    assert cues[2].start_ms == spoken.index("k") * 50
    assert all(left.end_ms <= right.start_ms for left, right in zip(cues, cues[1:]))


def test_missing_phonemes_are_interpolated_without_shifting_later_words():
    cues, estimated = align_cues("Hi — there", timed("hi there"), ["hi", "", "there"], 400)
    assert estimated and len(cues) == 3
    assert cues[-1].start_ms == 150
    assert cues[1].end_ms <= cues[2].start_ms


def test_legacy_models_and_unusable_alignment_have_safe_fallback():
    expected = estimated_cues("A simple line.", 2000)
    assert expected[0].start_ms == 0 and expected[-1].end_ms == 2000
    assert align_cues("A simple line.", [], [], 2000) == (expected, True)
    fallback, estimated = align_cues("hello", timed("zzzz"), ["hello"], 200)
    assert estimated and fallback == (SpeechCue(0, 200, 0, 5),)


def test_normalized_hyphenated_lines_keep_pdf_and_text_coordinates():
    source = (PdfLine("A beau-", (40, 100, 140, 120)), PdfLine("tiful ﬂower grows.", (40, 125, 220, 145)))
    block = TextBlock(40, 100, 220, 145, "\n".join(line.text for line in source), source)
    pages = prepare_pages([PageText(0, 600, 800, (block,))])
    assert pages[0].text == "A beautiful flower grows."
    assert pages[0].text[pages[0].lines[0].start:pages[0].lines[0].end] == "A beau"
    chunks = chunk_prepared_pages(pages)
    assert len(chunks) == 1 and len(chunks[0].lines) == 2
    word = SpeechCue(0, 1000, 2, 11)
    overlapping = [line for line in chunks[0].lines if line.start < word.text_end and line.end > word.text_start]
    assert len(overlapping) == 2  # A word broken across PDF lines needs both boxes.


def test_repeated_lines_and_chunk_boundaries_map_to_their_own_occurrences():
    source = tuple(PdfLine("Same text.", (30, 100 + index * 20, 200, 116 + index * 20)) for index in range(3))
    block = TextBlock(30, 100, 200, 156, "\n".join(line.text for line in source), source)
    pages = prepare_pages([PageText(0, 600, 800, (block,))])
    chunks = chunk_prepared_pages(pages, target=5, maximum=12)
    assert len(chunks) == 3
    assert [chunk.lines[0].rect for chunk in chunks] == [line.rect for line in source]
    assert [chunk.lines[0].page_start for chunk in chunks] == [0, 11, 22]


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_pdf_line_boxes_follow_rendered_page_rotation(tmp_path, rotation):
    import pymupdf
    path = tmp_path / "rotated.pdf"
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((50, 100), "A line on a rotated page.")
        page.set_rotation(rotation)
        document.save(path)
    service = PdfService()
    try:
        info = service.open(str(path))
        service.extract(0)
        pages, chunks = service.finalize()
        assert pages[0][1] == "A line on a rotated page."
        width, height = info.page_sizes[0]
        x0, y0, x1, y1 = chunks[0].lines[0].rect
        assert 0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height
    finally:
        service.close()


def viewer_fixture(qtbot):
    viewer = PdfViewer()
    qtbot.addWidget(viewer)
    viewer.resize(650, 450)
    viewer.set_document(PdfInfo("test", "test.pdf", "Test", 2, ((300, 800), (300, 800))))
    first, second = "😀 First line.", "Second line here."
    page_text = first + "\n\n" + second
    viewer.set_texts([(0, page_text), (1, page_text)])
    chunk = TextChunk(0, 0, first + " " + second, (
        ReadingLine(0, len(first), 0, len(first), (30, 50, 220, 70)),
        ReadingLine(len(first) + 1, len(first) + 1 + len(second), len(first) + 2, len(page_text), (30, 650, 230, 670)),
    ))
    viewer.show()
    viewer.timer.stop()
    viewer.show_render(RenderedPage(0, 300, 800, 900, bytes([255]) * 300 * 800 * 3))
    return viewer, chunk, first, second


def test_pdf_and_text_highlighting_toggle_and_unicode(qtbot):
    viewer, chunk, first, _ = viewer_fixture(qtbot)
    viewer.set_reading_highlight(chunk, SpeechCue(0, 500, 2, 7))
    assert viewer.page_image.highlight_rects == (chunk.lines[0].rect,)
    assert viewer.text.extraSelections()[0].cursor.selectedText() == first
    center = viewer.page_image.highlight_bounds()[0].center().toPoint()
    color = viewer.page_image.grab().toImage().pixelColor(center)
    assert color.green() > color.red() and color.red() < 250
    viewer.highlight_toggle.setChecked(False)
    assert not viewer.page_image.highlight_rects and not viewer.text.extraSelections()
    viewer.highlight_toggle.setChecked(True)
    assert viewer.page_image.highlight_rects


def test_highlight_tracks_zoom_scroll_and_waits_for_correct_page(qtbot):
    viewer, chunk, first, second = viewer_fixture(qtbot)
    cue = SpeechCue(500, 1000, len(first) + 1, len(chunk.text))
    viewer.set_reading_highlight(chunk, cue)
    qtbot.wait(20)
    assert viewer.scroll.verticalScrollBar().value() > 0
    assert viewer.text.extraSelections()[0].cursor.selectedText() == second
    original_width = viewer.page_image.highlight_bounds()[0].width()
    viewer.show_render(RenderedPage(0, 600, 1600, 1800, bytes([255]) * 600 * 1600 * 3))
    assert viewer.page_image.highlight_bounds()[0].width() == pytest.approx(original_width * 2)
    high_dpi = viewer.page_image.pixmap()
    high_dpi.setDevicePixelRatio(2)
    viewer.page_image.setPixmap(high_dpi)
    viewer.page_image.adjustSize()
    assert viewer.page_image.highlight_bounds()[0].width() == pytest.approx(original_width)
    viewer.set_page(1)
    viewer.timer.stop()
    next_chunk = TextChunk(1, 1, chunk.text, chunk.lines)
    viewer.set_reading_highlight(next_chunk, cue)
    assert not viewer.page_image.highlight_rects
    viewer.show_render(RenderedPage(1, 300, 800, 900, bytes([255]) * 300 * 800 * 3))
    assert viewer.page_image.highlight_rects
    viewer.clear_reading_highlight()
    assert not viewer.text.extraSelections() and not viewer.page_image.highlight_rects
