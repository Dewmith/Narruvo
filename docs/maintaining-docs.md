# Maintain this website

The handbook uses Sphinx, Furo, MyST Markdown, and static AutoAPI source parsing. Search runs from generated static assets; diagrams use Mermaid 11.12.1 from jsDelivr in the browser. The documentation environment is separate from the Windows app and does not need Qt, PyMuPDF, Kokoro, ONNX Runtime, or models.

## Create a docs-only environment

From the repository root on Windows:

```powershell
py -3.12 -m venv .venv-docs
.\.venv-docs\Scripts\python.exe -m pip install -r docs\requirements.txt
.\.venv-docs\Scripts\python.exe -m pip check
```

On Linux:

```bash
python3.12 -m venv .venv-docs
.venv-docs/bin/python -m pip install -r docs/requirements.txt
.venv-docs/bin/python -m pip check
```

Use only the standalone requirements for this environment. Installing the application with an extra would also install its runtime dependencies. Documentation tools are pinned to releases compatible with Python 3.12; verify compatibility when upgrading them.

## Build and validate

```powershell
.\.venv-docs\Scripts\python.exe -m sphinx -b html -W --keep-going docs build\docs\html
.\.venv-docs\Scripts\python.exe scripts\check_docs.py build\docs\html
```

On Linux, replace the executable path with `.venv-docs/bin/python` and use forward slashes.

Warnings fail the build. Nitpicky cross-reference checking verifies internal Python targets; external types without a local inventory are deliberately rendered without fetching remote inventories. `check_docs.py` validates generated HTML links, anchors, local assets, required reference/search output, and the GitHub Pages project path. It makes no network requests.

The configuration reads the package version from `pyproject.toml` with `tomllib`. It never imports `narruvo`. A build guard also rejects imports of the application or its native runtime modules.

## Preview locally

After building:

```powershell
.\.venv-docs\Scripts\python.exe -m http.server 8000 --bind 127.0.0.1 --directory build\docs\html
```

Open [localhost:8000](http://localhost:8000/). Stop the server with Ctrl+C. Rebuild after source changes, then refresh the browser. Check search, mobile navigation, both color themes, code blocks, and diagrams when changing presentation.

## Write a page

Pages are Markdown files under `docs/`. Add each new handbook page to the root `index.md` table of contents. Use sentence-case headings, repository-relative commands, generic Windows paths, and concise explanations of behavior and ownership.

- Link to another page using its `.md` filename; MyST resolves the generated HTML target.
- Use explicit cross-references such as `` {py:class}`narruvo.workers.ProcessWorker` `` for core Python interfaces.
- Use fenced MyST directives for notes, tables of contents, and Mermaid diagrams.
- Keep user installation and reading guidance in the [README](https://github.com/Dewmith/Narruvo/blob/main/README.md). Link to it when a developer needs the user flow.
- Add focused docstrings to the owning source module; AutoAPI regenerates its reference pages on the next build.

The historical `VERIFICATION.md` report and README's `screenshots/` directory are excluded from published sources. Their repository paths remain available. Generated API sources, virtual environments, HTML, and QA artifacts are ignored by Git.

## Publish through GitHub Pages

The planned public address is [dewmith.github.io/Narruvo](https://dewmith.github.io/Narruvo/). The site describes latest `main`, with a package-version label rather than separate release documentation snapshots.

1. Configure **Settings → Pages → Build and deployment → Source → GitHub Actions**.
2. Review and push the documentation files and `.github/workflows/docs.yml` to `main`.
3. Follow the **Developer documentation** Actions run and its `github-pages` deployment.
4. Verify navigation, search, diagrams, and assets at the project URL.

Pull requests build and validate documentation. Successful builds on `main` publish through the official Pages artifact/deployment actions. Only the deployment job receives `pages: write` and `id-token: write`; PR builds use read-only repository permissions. A failed build or link check prevents deployment.

The workflow runs for documentation, core Python source, project metadata, README, repository guidance, and docs-checker/workflow changes. It also supports manual runs; production publication is restricted to `main`. The source/edit links point to `main` on GitHub, and Sphinx's base URL includes `/Narruvo/`.

When changing the repository name or domain, update the Sphinx base URL, link-checker's project path, README documentation link, and publication settings together.
