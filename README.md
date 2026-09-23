# Jev Crash Course

Eleven small, runnable projects built around Jev, a model that makes decisions
instead of writing text. Each folder is one lesson: a web demo you can start in
one command, a whiteboard that explains the idea, and a README.

Every demo makes live API calls. Nothing here is simulated, mocked, or recorded.

[![Watch the Playlist](https://img.youtube.com/vi/rwNrCHS3BM8/0.jpg)](https://www.youtube.com/playlist?list=PLUSsSoiGR7aM)

## What Jev is, in one paragraph

Most models you have used generate text one token at a time, which is where the
seconds and most of the cost go. Jev does not do that. You give it some text and
a set of questions with fixed possible answers, and it returns a probability for
each. Three question types are the entire surface: yes or no, pick one of a
list, and score on a rubric you write. It cannot chat, cannot summarise, and
cannot write your email. What it can do is make a judgement call in a few hundred
milliseconds, for a fraction of a cent, in a form your code can branch on.

## The projects

| | Folder | What it shows | Port |
|---|---|---|---|
| 01 | `01-what-is-jev` | Three question types, side by side with a language model | 8001 |
| 02 | `02-where-to-use-jev` | Sorting jobs into plain code, Jev, or a language model | 8002 |
| 03 | `03-text-analysis` | Six questions about a piece of text in one round trip | 8003 |
| 04 | `04-jev-vs-llm-vs-agents` | Head to head with an LLM and an agent, calibration measured | 8004 |
| 05 | `05-text-measure` | Measuring writing while you type | 8005 |
| 06 | `06-jev-in-sql` | A thousand rows reviewed inside a single SQL query | 8006 |
| 07 | `07-contract-review` | Clause-by-clause triage, and what a contract is missing | 8007 |
| 08 | `08-playwright-testing` | Browser tests whose assertions are written in English | 8008 |
| 09 | `09-prompt-injection` | What an injection can and cannot reach | 8009 |
| 10 | `10-play-a-game` | Rock paper scissors, and where instinct stops | 8010 |
| 11 | `11-jev-vs-laya` | The hosted model against an open one you run yourself | 8011 |

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file in the repo root:

```
JEV_API_KEY=your-key-here
OPENAI_API_KEY=your-key-here
```

Every project walks up the directory tree to find that file. The Jev key is
required. The OpenAI key is only used by projects 01, 04 and 09, and only for the
lane they compare against, so everything else runs without it.

Two projects need one extra step:

```bash
python -m playwright install chromium     # project 08 drives a real browser
```

Project 11 downloads an open model from Hugging Face on its first run. That is
several gigabytes and takes a while.

## Running one

```bash
source .venv/bin/activate
cd 03-text-analysis
uvicorn app:app --port 8003 --reload
```

The demo is at `http://localhost:8003` and the whiteboard that explains it is at
`http://localhost:8003/whiteboard.html`.

Each project runs on its own port, so you can have several open at once.

## Inside a project folder

```
app.py              the server, and the questions it asks
static/index.html   the demo page
static/app.js       page logic, plain JavaScript, no build step
static/boards.json  the whiteboard content
README.md           how to run it, and what to watch out for
```

There is no build tooling anywhere in this repo. The pages are hand-written HTML,
CSS and JavaScript served by FastAPI. Some projects add their own modules, such
as `jevkit/` in project 04 or `engines.py` in project 11.

## The whiteboards

Every project ships a short visual explainer at `/whiteboard.html`. Arrow keys
step through it, `R` replays the current board, `F` goes fullscreen. The content
is in `static/boards.json`: a few boxes, arrows and notes positioned on a
1280x720 canvas.

## About the numbers

The timings, costs and accuracy figures quoted in the project READMEs were
measured on one machine, on one afternoon, against list prices. They will not
match yours, and some of them move between runs.

Where a result is within noise, the README says so rather than rounding it into a
headline. Project 11 is the clearest example: an open model running locally
scored 0.800 against Jev's 0.805 over 200 reviews, which is a tie given the
sample size, not a win for either side. Re-run anything before you quote it.

## Credits

Jev is by TypeSafe. Project 11 also uses [Laya](https://github.com/NandhaKishorM/laya),
an open decision model from Convai Innovations, licensed Apache 2.0. The app
reviews used as test data in projects 04, 06 and 11 are public app-store reviews.

## License

MIT, see [LICENSE](LICENSE).
