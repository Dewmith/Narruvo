# Architecture and data flow

Narruvo separates Qt coordination from native PDF and speech work. The GUI owns widgets, media playback, and short persistence operations. Each native service runs serially in its own spawned process.

## Process boundaries

```{mermaid}
flowchart TB
    GUI["GUI process<br/>Widgets · playback · SQLite"]
    PDF["PDF process<br/>Open · extract · render"]
    TTS["TTS process<br/>Load · hash · synthesize · cache"]
    GUI <-->|"Job IDs and PDF records"| PDF
    GUI <-->|"Job IDs and audio records"| TTS
```

| Owner | Work performed | Important boundary |
| --- | --- | --- |
| GUI thread | Widgets, view updates, request scheduling, media playback, small SQLite transactions | Native extraction, model initialization, and cache maintenance stay in workers |
| PDF process | Open/hash PDFs, extract text geometry, prepare chunks, render RGB pixels | PyMuPDF is used serially in this process |
| TTS process | Load/hash models, discover voices, synthesize, align speech timings, maintain audio cache | CPU inference and file hashing stay off the GUI thread |
| Setup download task | Explicit downloads, progress, cancellation, checksum verification | Network access begins with a setup action |

The application entry point calls `freeze_support()` before importing GUI modules. The frozen executable reuses that entry point for worker processes.

## Worker protocol and stale results

{py:class}`narruvo.workers.ProcessWorker` owns one serial command queue per service. The process starts lazily when the first request is dispatched.

- Requests are `(job_id, operation, arguments)` tuples.
- Results are `(job_id, success, value)` tuples. Failure values contain an error message.
- Payloads use plain records, scalars, collections, and bytes. Qt objects stay in their owning process.
- A 30 ms Qt timer polls completed results and emits controller-facing signals.
- Pending requests can be removed. An already running native operation may finish before a newer request starts.

Controllers attach **generation identifiers** to their job metadata. Opening another document, stopping narration, or replacing a recipe invalidates old work. A result is accepted only if its metadata still matches the controller's current generation. Document rendering also checks the requested page/scale pair, so an old render cannot replace the current view.

:::{important}
Queue cancellation and stale-result rejection solve different problems. Removing pending requests reduces wasted work; generation checks protect state when an operation was already running. Preserve both when changing asynchronous behavior.
:::

## Document preparation

1. {py:class}`narruvo.documents.DocumentController` submits an open request.
2. {py:class}`narruvo.pdf.PdfService` validates and hashes the original file, then returns a {py:class}`narruvo.domain.PdfInfo` record.
3. Extraction proceeds page by page, allowing early rendering while the remaining pages are prepared.
4. Text processing conservatively detects reading order, removes recurring margins, normalizes whitespace, and creates page-bound chunks.
5. Plain geometry records preserve the mapping from cleaned text to physical PDF lines. RGB render bytes become Qt images only after returning to the GUI.

Content hashes identify documents independently of their path. Identical contents at a new location retain identity; changed contents at an existing path start a separate reading session. Library removal deletes a SQLite record and does not remove the original file.

## Playback state and intent

{py:class}`narruvo.playback.PlaybackController` separates visible state from **intent** (`play`, `pause`, or `stop`). Generating audio is asynchronous; completion alone is not permission to play it.

- Pausing during generation retains pause intent. A completed section must remain paused.
- Stopping invalidates synthesis jobs, unloads current media, and resets the section position.
- Selecting a section preserves or explicitly replaces autoplay intent.
- Navigating to a page stops narration and selects readable text on or after that page. Trailing blank pages do not wrap to earlier content.
- Voice and rate have separate **active** and **preferred** values. Current audio retains its recipe; subsequent sections use the preference.
- Prefetch is bounded to the next two sections. Requests and retained results use text position, voice, and rate to identify a recipe.

{py:class}`narruvo.audio.AudioPlayer` adapts Qt Multimedia load/readiness, seek, and end-of-media events. Its calls and objects belong to the GUI thread. Loading a media source and deciding to start it remain separate steps.

## Speech timing and highlighting

Kokoro's timed phonemes are aligned with individual-word pronunciations in {py:mod}`narruvo.timing`. The result is a sequence of {py:class}`narruvo.domain.SpeechCue` records containing audio milliseconds and source-text offsets.

Chunk-to-page mappings retain physical line rectangles through normalization and dehyphenation. Playback position selects a cue; its text range identifies the PDF and Text-view lines to highlight. Pausing holds the highlight, seeking updates it, and stopping clears it. Older model exports or unusable alignment fall back to estimated timing.

## Cache and persistence

{py:class}`narruvo.tts.KokoroEngine` writes PCM WAVs and timing JSON sidecars atomically. Cache identity includes the audio/text processing versions, model and voice-bank fingerprints, text, voice, language, and synthesis rate. A WAV without valid matching timing metadata is regenerated.

{py:class}`narruvo.tts.AudioCache` prunes toward a 2 GB limit while protecting referenced audio paths. Pruning, clearing, initialization, hashing, and synthesis all run in the TTS process.

| Store | Contents |
| --- | --- |
| `settings.json` | Preferred voice/rate, volume, selected models, setup state, last document |
| `library.sqlite3` | Content identity, source path, recent-document metadata, saved reading progress |
| `models/` | Explicitly downloaded model files |
| `audio/` | Generated WAVs and timing sidecars |
| `logs/` | Rotating app log and per-worker diagnostics |

The default data root is `%LOCALAPPDATA%\Narruvo`; `NARRUVO_DATA_DIR` overrides it. {py:class}`narruvo.persistence.Library` uses parameterized statements, short transactions, and SQLite WAL mode. Schema `user_version` is currently 1; newer schemas are rejected rather than silently rewritten.

If the new default directory does not exist, an existing `%LOCALAPPDATA%\VoiceLeaf` directory is reused in place so a rename does not orphan libraries, model files, or stored absolute paths. The legacy `VOICELEAF_DATA_DIR` override remains a fallback; `NARRUVO_DATA_DIR` takes priority. Discovery does not copy, move, hash, or prune data.

Progress saves include view page, section index/hash, feasible audio offset, active and preferred recipes, and completion. Reopening restores a position without autoplay. See [testing and debugging](testing.md) for the regressions these boundaries protect.
