# Jarvis-Modell-Benchmark — Ergebnisse

Datensätze: 257. Qualität: Routing = Exact-Match-Genauigkeit, offene Kategorien = Ø der blinden Claude-Bewertung (1–10). Speed im Schnellmodus (think=False).

### Routing

| Modell | Genauigkeit | Median-Latenz | Ø-Latenz | Prefill (≈TTFT) | Tokens/s | n |
|---|---|---|---|---|---|---|
| gemma4:e2b | 88% | 0.52s | 0.52s | 0.28s | 90.99 | 16 |
| qwen3.5:9b | 88% | 1.22s | 1.20s | 0.93s | 29.79 | 16 |
| ornith:9b | 81% | 2.22s | 2.13s | 1.88s | 24.52 | 16 |
| gemma2:2b | 62% | 0.38s | 0.42s | 0.24s | 67.89 | 16 |
| qwen3:1.7b | 50% | 0.16s | 0.19s | 0.08s | 119.49 | 16 |
| llama3.2:1b | 44% | 0.18s | 0.23s | 0.05s | 102.86 | 16 |
| qwen2.5:0.5b | 25% | 0.13s | 0.14s | 0.03s | 214.17 | 16 |

### Chat

| Modell | Qualität (Ø/10) | Median-Latenz | Ø-Latenz | Prefill (≈TTFT) | Tokens/s | n |
|---|---|---|---|---|---|---|
| claude:haiku | 8.6 | 2.77s | 3.06s | — | 64.57 | 12 |
| ornith:9b | 6.3 | 8.89s | 12.06s | 1.40s | 11.82 | 12 |
| qwen3.5:9b | 6.2 | 11.17s | 14.97s | 0.59s | 14.42 | 12 |
| gemma4:e2b | 6.2 | 3.16s | 4.19s | 0.13s | 52.84 | 12 |
| deepseek-r1:14b | 3.4 | 76.76s | 65.05s | 0.73s | 6.53 | 12 |

### Coding

| Modell | Qualität (Ø/10) | Median-Latenz | Ø-Latenz | Prefill (≈TTFT) | Tokens/s | n |
|---|---|---|---|---|---|---|
| ornith:9b | 8.7 | 9.56s | 12.91s | 1.73s | 10.87 | 10 |
| qwen3.5:9b | 7.5 | 33.67s | 29.15s | 0.94s | 12.58 | 10 |
| deepseek-r1:14b | 3.3 | 84.67s | 83.92s | 1.28s | 5.93 | 10 |

### Reasoning

| Modell | Qualität (Ø/10) | Median-Latenz | Ø-Latenz | Prefill (≈TTFT) | Tokens/s | n |
|---|---|---|---|---|---|---|
| qwen3.5:9b | 8.4 | 4.98s | 7.22s | 0.97s | 12.91 | 11 |
| ornith:9b | 8.2 | 7.66s | 8.55s | 1.93s | 11.06 | 11 |
| deepseek-r1:14b-think | 7.2 | 38.22s | 36.72s | 1.00s | 9.55 | 11 |
| gemma4:e2b | 6.7 | 1.22s | 2.04s | 0.17s | 54.96 | 11 |
| deepseek-r1:14b | 6.6 | 67.14s | 69.93s | 1.50s | 6.35 | 11 |
