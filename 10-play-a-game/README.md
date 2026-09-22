# 10 - Rock paper scissors against a model that cannot play

Jev never picks a move. It answers one question - what will this person throw
next - and three lines of ordinary code play whatever beats the answer. The
prediction is worked out and locked before you throw, then shown to you
afterwards along with the probabilities behind it.

## Run

From the repo root:

```bash
source .venv/bin/activate
cd 10-play-a-game
uvicorn app:app --port 8010 --reload
```

Open http://localhost:8010, and http://localhost:8010/whiteboard.html for the
boards. Needs `JEV_API_KEY` in the repo-root `.env`.

## The scripted opponents

The panel on the right plays a scripted opponent so you can see how much of this
is pattern-finding and how much is luck. Measured over 24 rounds each:

| Opponent | Jev's win rate | Guessed right |
|---|---|---|
| throws rock every time | 100% | 100% |
| rock, paper, scissors on repeat | 33% | 33% |
| keeps a winning throw, changes a losing one | 21% | 21% |
| genuinely random | 42% | 42% |

Two of those are worth sitting with.

Against the repeating cycle it does badly, and the round-by-round shows why: it
keeps predicting the throw you just made. It catches a habit instantly and lags a
sequence by one. Working the rotation out is a reasoning job, and this model is
explicitly not built for those.

Against a random opponent nothing can beat one in three over the long run. Any
single run wanders either side of it; 42% over 24 rounds is noise, not skill.

Numbers move between runs. Run it before you record.

## Files

```
app.py     the game, the prediction, the scripted opponents
static/    the board, the scoreboard, the whiteboard
```

The game lives in memory in a single object, which is fine for one player on one
machine and would need a session key for anything else.
