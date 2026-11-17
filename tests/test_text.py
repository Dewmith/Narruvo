import re

from narruvo.domain import PageText, TextBlock
from narruvo.text import chunk_pages, clean_pages, normalize_text, reading_order


def test_normalizes_broken_lines_and_ligatures():
    assert normalize_text("A beau-\ntiful   ﬂower\n grows.\n\n Next paragraph.\u00ad") == "A beautiful flower grows.\n\nNext paragraph."


def test_chunks_preserve_text_and_page_mappings():
    first = "Dr. Green reads a book. The library is quiet. " * 30
    last = "A second page finishes the story. " * 20
    chunks = chunk_pages([(0, first), (1, " \n "), (2, last)])
    assert {c.page_index for c in chunks} == {0, 2}
    assert [c.index for c in chunks] == list(range(len(chunks)))
    assert all(0 < len(c.text) <= 600 for c in chunks)
    assert " ".join(c.text for c in chunks).split() == (first + last).split()
    assert all(len(c.text_hash) == 64 for c in chunks)


def test_long_sentence_and_unbroken_token_are_not_lost():
    text = "a " * 1000 + "z" * 1500
    chunks = chunk_pages([(4, text)])
    assert all(len(c.text) <= 600 and c.page_index == 4 for c in chunks)
    assert re.sub(r"\s", "", "".join(c.text for c in chunks)) == re.sub(r"\s", "", text)


def test_empty_pages_produce_no_chunks():
    assert chunk_pages([]) == []
    assert chunk_pages([(0, ""), (1, "\n\t")]) == []


def test_repeated_margin_header_removed_but_body_repetition_preserved():
    pages = [PageText(i, 600, 800, (
        TextBlock(30, 10, 250, 30, "Book title"),
        TextBlock(30, 100, 500, 150, "Important repeated body text."),
        TextBlock(280, 770, 300, 790, str(i + 1)),
    )) for i in range(4)]
    cleaned = clean_pages(pages)
    assert all(text == "Important repeated body text." for _, text in cleaned)


def test_one_page_heading_is_not_removed_as_repeated():
    page = PageText(0, 600, 800, (TextBlock(30, 10, 200, 30, "A useful title"),))
    assert clean_pages([page]) == [(0, "A useful title")]


def test_clear_columns_read_left_then_right():
    blocks = [TextBlock(330, 100, 560, 130, "Right one"), TextBlock(40, 100, 260, 130, "Left one"),
              TextBlock(330, 180, 560, 210, "Right two"), TextBlock(40, 180, 260, 210, "Left two")]
    assert [b.text for b in reading_order(blocks, 600)] == ["Left one", "Left two", "Right one", "Right two"]

