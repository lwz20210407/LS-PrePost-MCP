# Native movie output

`export_gui_animation(session_id, last=None, fps=10, width=1280, height=720)` exports an H264 MP4 through the current owned visible LS-PrePost session. `last=None` means the entire loaded timeline. This is a native movie, not screen recording or a Python-generated replacement.

Current certified scope is **Windows 4.13.4, starting at state 1, increment 1, forward sequence**. The optional last state is inclusive. Arbitrary starts/steps produced an unexpected initial frame and incomplete sequence in native probes; one attempt also timed out. Those modes are deliberately absent from the public tool. GIF/AVI and old versions/headless need separate work.

- Requires `ffprobe` and `ffmpeg` on PATH for independent validation; neither is downloaded, and they do not transcode the result.
- Set explicit integer fps1–60 and even width64–3840/height64–2160. Bounds are at most1800frames and600million pixel-frames; smaller budgets may be needed for complex models.
- Uses the current camera, visibility, fringe and overlays. This does not infer the quantity, units, coordinate frame or shell layer. Frame timestamps are recorded with unspecified model time units; uniform playback fps is not physical real-time scaling.
- Verifies native completion plus the exact ordered state/frame log, H264 codec, decoded frame count, resolution, fps, duration and complete error-free decoding. An existing or partially written file is not success.
- Restores and verifies the original result state and checks model counts/part IDs. Animation is left stopped with first1/last-output/increment1. It does not claim to restore a prior playing animation or its bounds.
- Output, native command/log evidence, model inventory and decode metadata belong to a fresh job directory. Failures preserve evidence and publish no validated video artifact; uncertain native requests are not replayed automatically.

The tool is available through MCP/CLI and GUI workflows, so managed recording and parameter replay include it. A changed `last` parameter produced3then4frames in a recorded replay. A representative private57-state result exported57decodedframes; source-family hashes were unchanged. These are bounded native checks, not certification of all result types or field semantics.

Opt-in reproducible driver: `tools/run_gui_movie_acceptance.py --workspace <private-directory> --executable <lspp-exe> --source <d3plot>`. It launches/maximizes its own GUI and writes all result data only to the caller's private workspace. No private media belongs in Git.

Sources: [official Movie tutorial](https://lsdyna.ansys.com/movie1/), [official file-menu reference](https://lsdyna.ansys.com/file/), plus observed4.13.4 GUI command recording. The UI codec caption contains `H.264`, but the recorded command token is `MP4/H264`. Windows movie output uses native backslash paths; the slash-path/stepped probe is retained as failed evidence, not a certified alternative.

Curve-image export and field-aware cloud-plot output remain separate core tasks in the [delivery plan](DELIVERY_PLAN.md).
