"""Check built documentation links and assets without fetching remote URLs."""

import argparse
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


class PageLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        for key in ("id", "name" if tag == "a" else "id"):
            if values.get(key):
                self.ids.add(values[key])
        for key in ("href", "src", "action", "data", "poster"):
            if values.get(key):
                self.links.append(values[key])


def check_site(root: Path, project_path: str = "/Text2Voice/") -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    pages: dict[Path, PageLinks] = {}
    for path in root.rglob("*.html"):
        page = PageLinks()
        page.feed(path.read_text(encoding="utf-8"))
        pages[path] = page
    if not pages:
        return [f"No HTML pages found in {root}"]
    for required in ("index.html", "search.html", "searchindex.js", "reference/index.html", "_autoapi/voiceleaf/workers/index.html", "_autoapi/voiceleaf/domain/index.html", ".nojekyll"):
        if not (root / required).is_file():
            errors.append(f"Missing required output: {required}")
    if (root / "VERIFICATION.html").exists() or (root / "screenshots").exists():
        errors.append("Historical verification and README screenshots must stay outside published output")

    for source, page in pages.items():
        for link in page.links:
            parsed = urlsplit(link)
            path = unquote(parsed.path)
            if parsed.netloc:
                if parsed.hostname != "dewmith.github.io" or not path.startswith(project_path):
                    continue
                path = path.removeprefix(project_path)
                target = root / path
            elif parsed.scheme:
                continue
            elif path.startswith("/"):
                if not path.startswith(project_path):
                    errors.append(f"{source.relative_to(root)}: link escapes project path: {link}")
                    continue
                target = root / path.removeprefix(project_path)
            else:
                target = source.parent / path if path else source
            target = target.resolve()
            if not target.is_relative_to(root):
                errors.append(f"{source.relative_to(root)}: link escapes output directory: {link}")
                continue
            if target.is_dir():
                target /= "index.html"
            if not target.is_file():
                errors.append(f"{source.relative_to(root)}: missing target: {link}")
                continue
            fragment = unquote(parsed.fragment)
            if fragment and target in pages and fragment not in pages[target].ids:
                errors.append(f"{source.relative_to(root)}: missing anchor: {link}")
    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--project-path", default="/Text2Voice/")
    args = parser.parse_args()
    errors = check_site(args.output, args.project_path)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"Documentation links, anchors, API pages, search, and project-path assets passed: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
