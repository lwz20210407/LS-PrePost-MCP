# Native view controls

`set_gui_display` now accepts `zoom_scale`, `pan_xy` and `rotation_xyz_degrees`, alongside standard views, parallel/perspective projection and `center=True` fit.

- `zoom_scale` is an **absolute native zoom setting**, within 0.01..100. It does not multiply the current zoom. Repeating the same setting is idempotent.
- `pan_xy` assigns two **absolute native view offsets**, within +/-100. It is not an incremental move, and the tool does not convert it into model coordinates or length units.
- `rotation_xyz_degrees` applies incremental global X, Y and Z view rotations in that order, each within +/-360 degrees. Zero components are skipped. The last nonzero rotation increment remains in the native toolbar setting.
- Operation order is standard view/display setup, incremental rotations, optional center-fit, then explicit zoom/pan. An explicit zoom therefore overrides the fitted scale; an explicit pan overrides the fitted offsets.

These commands move the view, not mesh nodes. Defaults retain the current camera. They do not change model/result titles, result units or default MinMax policy. All requested values are validated before native dispatch and are retained in managed recording, so zoom/pan/angles can be parameterized like other display settings.

Visible maximized 4.13.4 acceptance on a synthetic solid box verifies repeated zoom/pan settings give identical pixels, changed settings change the image, separate X/Y/Z rotations and their inverses restore the image, reference geometry/part flags/state remain unchanged, and recorded zoom can be replayed with another parameter. Inverse rotation comparisons permit symmetric one-pixel raster-edge movement and one RGB-level rounding after a Z inverse changed four edge pixels; repeated absolute setters remain pixel-exact. A representative private d3plot also passed zoom/pan idempotence, Z rotation/inverse and state/geometry/part preservation, with original file-family hashes unchanged. This is a bounded native validation, not a numeric camera-matrix API or cross-version guarantee.

For independent case replay, start with an explicit standard view/projection before incremental rotations. Repeating incremental angles without an orientation baseline can accumulate rotation; absolute zoom/pan alone do not reset orientation.

Native named view creation/selection and file export were separately probed: `view save` alone has no view data until a named view is created; native view selection restored the baseline image. The view format also stores appearance/color and can append loaded views. **Managed bookmarks, persistence across process/model changes, arbitrary rotation centers, selected-only fit and explicit screen-percentage margins are not yet exposed as verified tools.** Their raw command existence is not counted as completed support.

Driver: `tools/run_gui_camera_acceptance.py`. Baseline/operation PNGs and native logs stay in the caller's private output directory.
