# CSV trace benchmark

Input: `example_trace.csv`; 144 events; 16 entries; 0 warm-up events.

| Predictor | Accuracy | Misses | State bits | Penalty cycles only |
| --- | ---: | ---: | ---: | ---: |
| Static not taken | 25.00% | 108 | 0 | 540 |
| One-bit BHT | 57.64% | 61 | 16 | 305 |
| Two-bit BHT | 65.97% | 49 | 32 | 245 |
| Gshare | 73.61% | 38 | 36 | 190 |

Penalty is an illustrative 5 cycles per miss, not a measured runtime or CPI.
Equal table entries do not mean equal storage: one-bit uses N bits, two-bit uses 2N, and gshare uses 2N + log2(N).
These results come from the supplied branch trace. No BOOM core, pipeline, cache, or FPGA was measured.
