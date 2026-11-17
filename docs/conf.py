"""Static developer documentation; never import the desktop application here."""

import sys
import tomllib
from html import escape
from pathlib import Path

from sphinx.errors import ExtensionError

DOCS = Path(__file__).resolve().parent
ROOT = DOCS.parent
METADATA = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]

project = "VoiceLeaf"
author = "VoiceLeaf contributors"
copyright = "2026, VoiceLeaf contributors"
release = METADATA["version"]
version = release
language = "en"

extensions = [
    "myst_parser",
    "autoapi.extension",
    "sphinx.ext.napoleon",
    "sphinx.ext.githubpages",
    "sphinxcontrib.mermaid",
]
source_suffix = {".md": "markdown", ".rst": "restructuredtext"}
root_doc = "index"
exclude_patterns = ["VERIFICATION.md", "screenshots/**", "_build/**", "Thumbs.db", ".DS_Store"]
myst_enable_extensions = ["colon_fence", "deflist", "fieldlist"]
myst_heading_anchors = 3

autoapi_type = "python"
autoapi_dirs = [str(ROOT / "src" / "voiceleaf")]
autoapi_root = "_autoapi"
autoapi_keep_files = False
autoapi_add_toctree_entry = False
autoapi_ignore = ["*/ui/*", "*/app.py", "*/__main__.py", "*/package_verification.py", "*/logging_setup.py"]
autoapi_options = ["members", "undoc-members", "show-inheritance", "show-module-summary"]
autoapi_member_order = "bysource"
autoapi_python_class_content = "class"
napoleon_google_docstring = True
napoleon_numpy_docstring = True

# Internal cross-references must resolve. These external types have no local
# inventory; ignoring them avoids network-dependent intersphinx downloads.
nitpicky = True
nitpick_ignore_regex = [
    (r"py:.*", r"(?:PySide6|collections|datetime|logging|multiprocessing|pathlib|queue|threading|typing|typing_extensions|abc)(?:\..*)?"),
    (r"py:.*", r"(?:QObject|Path|Event|Callable|Protocol)"),
]

html_theme = "furo"
html_title = "VoiceLeaf developer docs"
html_baseurl = "https://dewmith.github.io/Text2Voice/"
html_logo = "_static/leaf.svg"
html_favicon = "_static/leaf.svg"
html_static_path = ["_static"]
html_css_files = ["voiceleaf.css"]
html_theme_options = {
    "announcement": f"Latest main &nbsp;·&nbsp; package {escape(release)}",
    "source_repository": "https://github.com/Dewmith/Text2Voice/",
    "source_branch": "main",
    "source_directory": "docs/",
    "light_css_variables": {
        "color-brand-primary": "#286345",
        "color-brand-content": "#286345",
        "color-background-primary": "#fcfdfb",
        "color-background-secondary": "#f2f6f1",
        "color-admonition-title--note": "#286345",
        "color-admonition-title-background--note": "#e7f2e9",
    },
    "dark_css_variables": {
        "color-brand-primary": "#9cceae",
        "color-brand-content": "#a8d5b8",
        "color-background-primary": "#141b1a",
        "color-background-secondary": "#192320",
        "color-background-hover": "#25362d",
        "color-foreground-primary": "#e5eee9",
        "color-foreground-secondary": "#b5c6bc",
        "color-admonition-title--note": "#9cceae",
        "color-admonition-title-background--note": "#25362d",
    },
}
html_show_sourcelink = True
html_copy_source = False
html_last_updated_fmt = None
pygments_style = "friendly"
pygments_dark_style = "monokai"
mermaid_version = "11.12.1"
mermaid_light_theme = "neutral"
mermaid_height = "auto"


def source_edit_links(app, pagename, templatename, context, doctree) -> None:
    """Point generated API pages to real source files, rather than generated RST."""
    if not pagename.startswith("_autoapi/"):
        return
    module = pagename.removeprefix("_autoapi/").removesuffix("/index")
    source = ROOT / "src" / f"{module}.py"
    if not source.is_file():
        source = ROOT / "src" / module / "__init__.py"
    if source.is_file():
        relative = source.relative_to(ROOT).as_posix()
        context["theme_source_edit_link"] = f"https://github.com/Dewmith/Text2Voice/edit/main/{relative}"
    else:
        context["theme_source_repository"] = ""


def ensure_static_build(app, exception=None) -> None:
    """Fail if a future documentation change starts importing native app code."""
    forbidden = {"voiceleaf", "PySide6", "pymupdf", "fitz", "kokoro_onnx", "onnxruntime", "phonemizer", "soundfile"}
    imported = sorted(name for name in forbidden if name in sys.modules)
    if imported:
        raise ExtensionError(f"Documentation must parse source without importing application modules: {', '.join(imported)}")


def setup(app):
    app.connect("html-page-context", source_edit_links)
    app.connect("builder-inited", ensure_static_build)
    app.connect("build-finished", ensure_static_build)
