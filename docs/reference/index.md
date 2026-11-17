# Python code reference

These pages describe the core implementation on **latest `main`**. AutoAPI reads Python source and docstrings without importing the application, starting Qt, creating native workers, or loading models.

Read the [architecture](../architecture.md) before using controller or service interfaces. Ownership, asynchronous completion, generations, and playback intent are part of their calling contract.

## Find the owning module

| Area | Reference |
| --- | --- |
| Cross-process records and progress | {py:mod}`narruvo.domain` |
| Data paths and settings | {py:mod}`narruvo.config` |
| PDF service and document coordination | {py:mod}`narruvo.pdf`, {py:mod}`narruvo.documents` |
| Serial worker protocol | {py:mod}`narruvo.workers` |
| Text cleanup, chunks, and timing alignment | {py:mod}`narruvo.text`, {py:mod}`narruvo.timing` |
| Model manifest and verified downloads | {py:mod}`narruvo.models` |
| CPU synthesis and paired audio cache | {py:mod}`narruvo.tts` |
| Playback intent and Qt media adapter | {py:mod}`narruvo.playback`, {py:mod}`narruvo.audio` |
| SQLite library | {py:mod}`narruvo.persistence` |

The [source package on GitHub](https://github.com/Dewmith/Narruvo/tree/main/src/narruvo) also includes the window, dialogs, theme, startup, and packaging checks. The generated reference concentrates on the core interfaces rather than private UI callbacks.

```{toctree}
:maxdepth: 2

../_autoapi/narruvo/index
```
