# Q08 r413a: real batch XYPlot

Actual Git revision: `4f148fb0a130f8b85ce2b6ded2968033a6aacd2d`; clean tracked tree.

3 passed / 0 failed; six real headless native plot jobs.

| Case | Curves | Axes | Range | Native/CSV samples verified |
|---|---:|---|---|---:|
| test_single_curve_and_semilog_0 | 1 | Log-Lin | None, None | 4 |
| test_single_curve_and_semilog_0 | 1 | Lin-Lin | [0.5, 2.5], None | 4 |
| test_ten_curves_log_axes_and_r0 | 10 | Log-Log | None, None | 43 |
| test_ten_curves_log_axes_and_r0 | 10 | Log-Log | [0.1, 10.0], [0.1, 1000.0] | 43 |
| test_ten_curves_log_axes_and_r0 | 10 | Lin-Lin | None, None | 43 |
| test_three_load_cases_force_di0 | 3 | Lin-Lin | [0.0, 4.0], [0.0, 25.0] | 15 |

Three original synthetic CSV load cases include unequal grids and a backtracking displacement loop. Ten curves test legend/linear/log-log/ranges; one curve tests semilog and legend off. Original CSV bytes were checked after the run and retained.
PNG and XY readback originate from the same native plot window; exported CSV exactly preserves declared float32 native storage, with XY readback rtol=5e-11/atol=0. No model-unit inference, conversion or resampling. Image decoding/color checks and cross-image differences pass. The 4.13 three-case PNG was also visually inspected.
No visible GUI, Win32 session, UU or solver. Raw PNG/CSV/XY, commands and logs remain outside Git; file hashes and dimensions are recorded in evidence.json.
