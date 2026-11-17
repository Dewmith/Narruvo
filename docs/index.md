# Developer handbook

<div class="vl-intro">
<p class="vl-eyebrow">VoiceLeaf · latest main</p>
<p>Understand the process boundaries, change the reader safely, and ship a verified Windows release.</p>
<p>VoiceLeaf is a Windows PDF audiobook reader built with Python, PySide6, and CPU Kokoro synthesis. This handbook covers its implementation and development lifecycle.</p>
</div>

<div class="vl-links">
<a href="getting-started.html"><strong>Set up development →</strong><span>Python 3.12, the local environment, and a first run.</span></a>
<a href="architecture.html"><strong>Understand the architecture →</strong><span>Processes, generations, playback intent, and data flow.</span></a>
<a href="testing.html"><strong>Verify a change →</strong><span>Ordinary tests, opt-in models, and package checks.</span></a>
<a href="reference/index.html"><strong>Explore the Python reference →</strong><span>Core types, services, controllers, and processing functions.</span></a>
</div>

## The development loop

1. [Set up the supported environment](getting-started.md) and reproduce the behavior.
2. [Understand the owning process and state](architecture.md) before changing code.
3. Implement a focused change using the [development conventions](development.md).
4. Run the relevant [tests and acceptance checks](testing.md), and update these docs.
5. Open a pull request. CI tests and packages the Windows app; documentation CI checks this site.
6. Follow the [release procedure](packaging.md) to publish a versioned installer.

## Implementation boundaries

- **Offline operation:** runtime reading and fresh narration use local files. Model downloads require an explicit setup action.
- **Native process isolation:** PDF operations belong in the PDF worker; model loading, hashing, synthesis, and cache maintenance belong in the TTS worker.
- **Asynchronous correctness:** requests carry job identifiers and controller generations. Results must respect current playback intent.
- **User-owned documents:** PDFs stay where they are. Library removal only removes a database entry.

The [repository instructions](https://github.com/Dewmith/Text2Voice/blob/main/AGENTS.md) remain the source for development constraints.

:::{note}
These pages describe **latest `main`**, with the package version read from project metadata. For downloading, installing, setting up voices, and using the app, see the [user README](https://github.com/Dewmith/Text2Voice/blob/main/README.md).
:::

```{toctree}
:maxdepth: 2
:caption: Developer handbook
:hidden:

getting-started
architecture
development
testing
packaging
reference/index
maintaining-docs
```
