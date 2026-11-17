# Python code reference

These pages describe the core implementation on **latest `main`**. AutoAPI reads Python source and docstrings without importing the application, starting Qt, creating native workers, or loading models.

Read the [architecture](../architecture.md) before using controller or service interfaces. Ownership, asynchronous completion, generations, and playback intent are part of their calling contract.

## Find the owning module

| Area | Reference |
| --- | --- |
| Cross-process records and progress | {py:mod}`voiceleaf.domain` |
| Data paths and settings | {py:mod}`voiceleaf.config` |
| PDF service and document coordination | {py:mod}`voiceleaf.pdf`, {py:mod}`voiceleaf.documents` |
| Serial worker protocol | {py:mod}`voiceleaf.workers` |
| Text cleanup, chunks, and timing alignment | {py:mod}`voiceleaf.text`, {py:mod}`voiceleaf.timing` |
| Model manifest and verified downloads | {py:mod}`voiceleaf.models` |
| CPU synthesis and paired audio cache | {py:mod}`voiceleaf.tts` |
| Playback intent and Qt media adapter | {py:mod}`voiceleaf.playback`, {py:mod}`voiceleaf.audio` |
| SQLite library | {py:mod}`voiceleaf.persistence` |

The [source package on GitHub](https://github.com/Dewmith/Text2Voice/tree/main/src/voiceleaf) also includes the window, dialogs, theme, startup, and packaging checks. The generated reference concentrates on the core interfaces rather than private UI callbacks.

```{toctree}
:maxdepth: 2

../_autoapi/voiceleaf/index
```
