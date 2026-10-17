# Synthetic workload sweep

Seed 7; 4,096 events per workload, first 256 used only for warm-up.
Table sizes: 4, 16, 64, 256. Fresh predictor state for every case.

## Results at 64 entries

| Workload | Static NT | One bit | Two bit | Gshare |
| --- | ---: | ---: | ---: | ---: |
| loop | 3.12% | 93.75% | 96.88% | 96.88% |
| alternating | 50.00% | 0.00% | 50.00% | 100.00% |
| correlated | 52.60% | 51.46% | 50.47% | 73.91% |
| aliasing | 50.00% | 100.00% | 100.00% | 100.00% |
| random | 51.07% | 51.20% | 50.05% | 48.57% |

## What the cases isolate

- Loop: 31 taken outcomes followed by one exit; hysteresis avoids relearning after each exit.
- Alternating: one PC alternates N/T; history can distinguish outcomes that a last-outcome bit cannot.
- Correlated: random branch A followed by branch B with the same outcome; A remains unpredictable, while B has useful history.
- Aliasing: PCs 0x1000 and 0x1040 have opposite fixed outcomes. They collide at 4/16 entries and separate at 64/256.
- Random: independent fair outcomes provide a control with no intended learnable pattern.

Initial state: one-bit N, two-bit/gshare weakly N, global history zero. History width equals log2(entries).
The predictors have equal entry counts, not equal bit budgets. State excludes tags, targets, control, and SRAM overhead.
These handcrafted cases demonstrate behavior; they are not representative application traces or evidence of BOOM/FPGA speedup.
