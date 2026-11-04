# Q07 4.10 batch numerical comparisons

Git revision: `2f3242ca488561cd780d5fc5f3282c82686630d8`; working_tree_dirty=false.
Git diff SHA256: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` (all tracked staged/unstaged changes; untracked excluded).
Passed: 20; failed: 0; skipped: 0. Headless execution only.
Full records, including both endpoints; rtol=2e-5, atol=1e-6*max(abs(reference)).
The 16 BW cases use four synthetic engineering-shaped inputs; the four SAE cases retain the existing sine mixture.

| Filter / input | Nominal Hz | Time unit | Samples | Maximum absolute error | Validity |
|---|---:|---|---:|---:|---|
| BW / impact_ringdown | 60 | ms | 6001 | 0.0001221156249 | 当前有效（登记范围） |
| BW / impact_ringdown | 60 | s | 6001 | 0.0001221156249 | 当前有效（登记范围） |
| BW / impact_ringdown | 600 | ms | 6001 | 0.0001221 | 当前有效（登记范围） |
| BW / impact_ringdown | 600 | s | 6001 | 0.0001221 | 当前有效（登记范围） |
| BW / offset_step | 60 | ms | 3001 | 3.052250003e-05 | 当前有效（登记范围） |
| BW / offset_step | 60 | s | 3001 | 3.052250003e-05 | 当前有效（登记范围） |
| BW / offset_step | 600 | ms | 3001 | 3.051351564e-05 | 当前有效（登记范围） |
| BW / offset_step | 600 | s | 3001 | 3.051351564e-05 | 当前有效（登记范围） |
| BW / short_impulse | 60 | ms | 41 | 2.328352938e-09 | 当前有效（登记范围） |
| BW / short_impulse | 60 | s | 41 | 2.328352938e-09 | 当前有效（登记范围） |
| BW / short_impulse | 600 | ms | 41 | 3.725756084e-09 | 当前有效（登记范围） |
| BW / short_impulse | 600 | s | 41 | 3.725756084e-09 | 当前有效（登记范围） |
| BW / sine_mix | 60 | ms | 4001 | 1.907825194e-06 | 当前有效（登记范围） |
| BW / sine_mix | 60 | s | 4001 | 1.907825194e-06 | 当前有效（登记范围） |
| BW / sine_mix | 600 | ms | 4001 | 1.907806642e-06 | 当前有效（登记范围） |
| BW / sine_mix | 600 | s | 4001 | 1.907806642e-06 | 当前有效（登记范围） |
| SAE / sine_mix | 60 | ms | 4001 | 8.392373438e-05 | 当前有效（登记范围） |
| SAE / sine_mix | 60 | s | 4001 | 5.000000414e-10 | 当前有效（登记范围） |
| SAE / sine_mix | 600 | ms | 4001 | 9.536862304e-06 | 当前有效（登记范围） |
| SAE / sine_mix | 600 | s | 4001 | 2.861098633e-06 | 当前有效（登记范围） |
