# Physical-field animations from native frames

`export_gui_field_animation(session_id, states, color_range, fps=10,
width=1280, height=720)` is distinct from `export_gui_animation`.

- Each field value, deletion-filtered scene and source PNG is produced in the
  owned visible LS-PrePost session. The physical mask is explicitly LASSO MDLOPT2.
- FFmpeg/libx264 assembles the native PNG sequence. Output metadata identifies
  this encoder and `native_movie_command=false`; it is not described as an
  LS-PrePost Movie-command MP4.
- The older `export_gui_animation` retains its native Movie-command contract
  and still rejects a physical-mask scene without per-frame replay. Native
  first=last testing produced an extra state-1 frame, so it was not accepted
  as a one-frame encoder.

## Request and scene contract

First render the **current state** using `render_gui_field` with
`validity_policy="alive"`. The current verified solid/shell field supplies its
quantity, units, layer, selected parts and averaging. Do not change parts or
leave a general selection before exporting. Camera and titles are retained.

Provide strictly increasing, unique 1-based saved states and explicit fixed
color bounds. Every output frame uses **all physically present entities in
the selected parts**. Manual Blank is intentionally ignored for these frames,
then restored afterwards together with the initial state, part visibility and
field/color definition. This scope is different from a movie of the current
static Blank subset. The baseline scene must be verified so it can be restored.

The implementation clears the previous frame's Blank for the requested domain,
then reloads that state's physical mask, checks native flags and exact CSV
membership, and captures the native PNG. A later state's deleted entities must
not accidentally stay hidden in an earlier state. Missing masks/fields, empty
physical display scopes or uncertain native completion fail; incomplete frames
are not encoded. Restoration failures return failure and mark the session
uncertain rather than silently offering a replay.

Playback uses one frame per selected saved state at uniform FPS. Physical times
are preserved in `frames.json` and metadata; irregular time spacing is not
resampled or represented as uniform physical time. Frame PNGs retain native
viewport resolution; MP4 uses aspect-preserving resize and white letterboxing
to the requested even dimensions. FFprobe verifies dimensions, rate, duration,
codec and decoded frame count; FFmpeg decodes the entire resulting video.

Existing limits remain: 1..1800 frames, 1..60 FPS, width64..3840/height64..2160,
600 million output and source pixel-frames, native field/visibility budgets and
the retained custom-fringe scalar-buffer budget. This is not a global model-size
claim. No camera refit, title suffix, unit conversion or inferred layer change
is performed during export.

## Recording and verified scope

Record view setup and `render_gui_field` before this context-dependent operation.
Internal frame renders are child jobs and do not become independent recording
steps. Parameterize the movie's `states`, bounds or playback settings in the
usual workflow system.

Visible maximized LS-PrePost 4.13.4 acceptance passed on the public projectile
family using `tools/run_physical_movie_acceptance.py`:

- States1/8/16 retained5664/5405/5050 solid elements respectively.
- Fixed bounds0..0.03 in unresolved source units; 640x480 H264,5FPS,3frames,
  0.6seconds, full decode passed.
- A four-step recording (view, field, manual hide, movie) replayed with states8/16
  and produced2frames. The manually hidden present element was rendered during
  export and restored to hidden afterwards; source-family fingerprints matched.
- Local evidence: `native-physical-movie-ca7e56216d6b47c9809cddcb2e384c3f` in the
  dated task directory. Synthetic tests cover bad requests, encoder failure and
  restoring state/Blank/fringe after a failed native frame.

Shell implementation, other versions and headless execution still need their
own native animation acceptance. All-deleted frames currently fail explicitly
rather than creating a misleading zero-stress picture.
