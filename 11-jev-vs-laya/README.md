# 11 - Jev vs Laya

Two models that do the same job: answer fixed questions about text and hand back
numbers, never sentences. Jev is a hosted API billed per token. Laya is an open
model under Apache 2.0 that downloads once and runs on your own machine.

Both get the same four questions, the same reviews, and the same answer key: the
reviewer's star rating, which neither is shown.

## Run

From the repo root:

```bash
source .venv/bin/activate
pip install laya
cd 11-jev-vs-laya
uvicorn app:app --port 8011 --reload
```

Open http://localhost:8011, and http://localhost:8011/whiteboard.html for the
boards. Needs `JEV_API_KEY` in the repo-root `.env`.

The first Laya call downloads the weights from Hugging Face. That is several
gigabytes and takes a while, so press **Load Laya into memory** once and let it
finish before recording. Loading the cached weights afterwards takes about 30
seconds; every call after that is local compute.

## What was measured

200 reviews, one run, on an Apple GPU through Metal. Jev with 20 calls in
flight, Laya one at a time.

| | Jev | Laya |
|---|---|---|
| how often right | 0.805 | 0.800 |
| calibration error | 0.120 | 0.088 |
| Brier | 0.141 | 0.132 |
| median call | 380 ms | 229 ms |
| slowest call | 3311 ms | 973 ms |
| wall clock, all 200 | 5.3 s | 49.7 s |
| cost | $0.0054 | nothing |

Four things worth saying carefully.

**The accuracy gap is not real.** 0.805 against 0.800 over 200 rows has a
standard error of about 0.040 on the difference. That is a tie. The honest claim
is that a 322M parameter model on a laptop matched a hosted frontier decision
model on this task, not that either one won.

**Per-call latency and throughput point in opposite directions.** Laya is
faster on any single call because there is no network in the way, and its tail is
far tighter: 973 ms at worst against 3311 ms. But Jev finished all 200 in 5.3
seconds against 49.7, because you can put twenty calls in flight and only one
copy of Laya runs at a time on one machine.

**They agree less than the scoreboard suggests.** Same accuracy, but they picked
the same topic on only about half the reviews, and the same churn level on about
three in five. Two models can score identically and still disagree constantly.
That matters if you are thinking of swapping one for the other.

**Numbers move.** One run, one machine, one afternoon. Re-run before quoting.

## The six languages tab

Laya ships a separate multilingual checkpoint and its own documentation says the
English one fails outside Latin script. That tab runs the same complaint in six
languages through Jev, through Laya's English checkpoint, and through Laya's
multilingual one, so you can see where each stops. The first run loads a second
set of weights.

## Files

```
app.py        the server: side by side, the benchmark, the language test
engines.py    the questions written once, rendered for each engine
metrics.py    calibration error, Brier, reliability bins
data/         the same 1,000 reviews project 04 uses
```

`engines.py` is the part worth reading. The questions are plain dictionaries,
rendered into typed objects for one engine and dictionaries for the other. That
is the entire porting effort between the two.
