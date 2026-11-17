# Development and contribution

Start with [environment setup](getting-started.md) and the [architecture](architecture.md). The repository's [AGENTS.md](https://github.com/Dewmith/Narruvo/blob/main/AGENTS.md) records constraints that must remain true as the app evolves.

## Work on a focused change

1. Reproduce the issue or write down the intended behavior and acceptance criteria.
2. Identify the owner: UI, controller, PDF process, TTS process, persistence, packaging, or documentation.
3. Make a small change with the relevant regression coverage.
4. Run [ordinary tests](testing.md), then opt into integration checks when the affected behavior needs real models or multimedia.
5. Update the handbook and affected docstrings in the same pull request.
6. Review CI results before merging. Documentation publishes from `main`; Windows release assets are built from the release tag.

For AI-assisted work, keep commits, pushes, and branch creation under explicit user instruction, as required by the repository guidance.

## Code conventions

- Target Python 3.12 and the versions in `pyproject.toml`.
- Use `pathlib.Path`, type annotations, standard logging, and parameterized SQLite statements.
- Put cross-process data in plain dataclasses and keep Qt objects in the GUI process.
- Prefer bounded work and explicit cancellation to background tasks that run indefinitely.
- Keep file replacement atomic for settings, downloads, audio, and timing metadata.
- Treat model installation as an explicit action. Ordinary startup, reading, and uncached narration must work offline after setup.

## Change asynchronous behavior safely

Before changing a controller or worker operation, answer these questions in the pull request:

| Question | Why it matters |
| --- | --- |
| Which process owns the work? | PyMuPDF and TTS operations have dedicated native workers |
| What identifies the request and its generation? | Old native results may arrive after navigation or stop |
| What happens to current playback intent? | A completed result must not resume paused/stopped playback |
| What work can be cancelled? | Pending work can be removed; active native work may finish |
| Which cached audio paths remain protected? | Pruning must not remove media still referenced by playback |
| How does shutdown complete? | Queues, media, and native processes need bounded cleanup |

Exercise rapid controls, document changes, pending voice/rate changes, and shutdown. Preserve the behavior described in [playback state and intent](architecture.md#playback-state-and-intent).

## Data and compatibility changes

PDFs belong to the user and stay at their original locations. Relocation, changed-content detection, and library removal must preserve that rule.

For cache format changes, update the appropriate processing/audio identity and document regeneration behavior. Cached timing metadata must agree with its WAV and source text. For database changes, define a migration and compatibility policy rather than relying on table creation to alter an existing database. Current storage behavior is described in [cache and persistence](architecture.md#cache-and-persistence).

Do not commit model binaries, fixture PDFs, generated audio, local databases, logs, virtual environments, generated API pages, or HTML build output. Generate fixtures in temporary directories and development artifacts under `.artifacts/`.

## Document core interfaces

The [Python reference](reference/index.md) is generated from source. Use concise class/function docstrings that describe ownership, parameters, units, return values, and meaningful errors. Existing Google-style or NumPy-style docstrings are supported.

Document behavior that callers cannot infer from a signature: whether an operation queues work, preserves intent, invalidates generations, reads a whole file, or requires the caller to be in a worker process. Keep usage explanations in the handbook and routine installation/reading guidance in the [user README](https://github.com/Dewmith/Narruvo/blob/main/README.md).

## Pull-request completion checks

- Relevant ordinary tests pass, and new tests check externally observable behavior or a regression.
- Changes involving models, playback, timing, or decoding have appropriate opt-in verification.
- UI changes have a real entry-point launch check and a 1024×768 layout check.
- Packaging changes pass the installed-executable and uninstall checks.
- Documentation builds without warnings and its internal links/assets pass validation.
- The PR explains the resulting behavior, validation, and any remaining practical limits.

See [testing](testing.md), [packaging](packaging.md), and [maintaining documentation](maintaining-docs.md) for commands.
