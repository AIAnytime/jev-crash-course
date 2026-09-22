const $ = (id) => document.getElementById(id);
const pct = (p) => `${Math.round(p * 100)}%`;

function setScore(s) {
  $("s-rounds").textContent = s.rounds;
  $("s-you").textContent = s.you;
  $("s-jev").textContent = s.jev;
  $("s-draws").textContent = s.draws;
  $("s-acc").textContent = s.rounds ? pct(s.prediction_accuracy) : "—";
}

function setButtons(on) {
  document.querySelectorAll("[data-throw]").forEach((b) => { b.disabled = !on; });
}

async function lock() {
  setButtons(false);
  $("lock").textContent = "locking in a prediction…";
  try {
    const res = await fetch("/api/lock", { method: "POST" });
    const d = await res.json();
    if (!res.ok) throw new Error(d.error || res.statusText);
    $("lock").textContent =
      `prediction locked in ${Math.round(d.seconds * 1000)}ms, after watching ${d.rounds_seen} rounds`;
  } catch (err) {
    $("error").textContent = String(err.message || err);
    $("lock").textContent = "";
  } finally {
    setButtons(true);
  }
}

async function play(choice) {
  setButtons(false);
  $("error").textContent = "";
  try {
    const res = await fetch("/api/throw", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ choice }),
    });
    const d = await res.json();
    if (!res.ok) throw new Error(d.error || res.statusText);

    $("you-played").textContent = d.you;
    $("jev-played").textContent = d.jev;
    const word = { you: "you win", jev: "Jev wins", draw: "draw" }[d.outcome];
    $("outcome").className = `outcome ${d.outcome}`;
    $("outcome").textContent = word;
    setScore(d.score);

    $("spread").innerHTML = Object.entries(d.spread)
      .sort((a, b) => b[1] - a[1])
      .map(([name, p]) => `
        <div class="bar">
          <span class="name">${name}${name === d.you ? " (yours)" : ""}</span>
          <span class="track"><span class="fill" style="width:${(p * 100).toFixed(1)}%"></span></span>
          <span class="num">${pct(p)}</span>
        </div>`).join("");
    $("pattern").textContent =
      `it expected ${d.expected} and you threw ${d.you}. ` +
      `chance it thinks you are following a pattern: ${pct(d.pattern)}`;

    $("rounds").innerHTML = d.history.map((h) =>
      `<span class="${h.result_for_you}">${h.you} v ${h.jev}</span>`).join("");
    $("status").textContent = `$${d.score.cost.toFixed(5)} of model calls so far`;
  } catch (err) {
    $("error").textContent = String(err.message || err);
  } finally {
    lock();
  }
}

document.querySelectorAll("[data-throw]").forEach((b) => {
  b.onclick = () => play(b.dataset.throw);
});

$("new").onclick = async () => {
  const s = await (await fetch("/api/new", { method: "POST" })).json();
  setScore(s);
  $("you-played").textContent = "—";
  $("jev-played").textContent = "—";
  $("outcome").textContent = "";
  $("rounds").innerHTML = "";
  $("spread").innerHTML = `<p class="hint" style="margin:0">Throw something.</p>`;
  $("pattern").textContent = "";
  lock();
};

async function simulate() {
  $("simulate").disabled = true;
  const total = Number($("rounds").value);
  $("sim-status").textContent = `playing 0 of ${total}…`;
  const poll = setInterval(async () => {
    try {
      const p = (await (await fetch("/api/bots")).json()).progress;
      $("sim-status").textContent = `playing ${p.done} of ${p.total}…`;
    } catch (_) { /* busy */ }
  }, 400);
  try {
    const res = await fetch("/api/simulate", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ rounds: total, bot: $("bot").value }),
    });
    const d = await res.json();
    if (!res.ok) throw new Error(d.error || res.statusText);
    const edge = d.jev_win_rate - 1 / 3;
    $("sim-out").innerHTML = `
      <div class="stats">
        <div class="stat"><div class="k">Jev won</div><div class="v">${d.jev_wins}<small>/${d.rounds}</small></div></div>
        <div class="stat"><div class="k">win rate</div><div class="v">${pct(d.jev_win_rate)}</div></div>
        <div class="stat"><div class="k">vs one in three</div><div class="v">${edge >= 0 ? "+" : ""}${(edge * 100).toFixed(1)}<small>pts</small></div></div>
        <div class="stat"><div class="k">guessed right</div><div class="v">${pct(d.prediction_accuracy)}</div></div>
      </div>
      <p class="hint" style="margin:12px 0 0">${d.description} &middot; ${d.seconds.toFixed(1)}s &middot; $${d.cost.toFixed(5)}</p>`;
    $("sim-status").textContent = "";
  } catch (err) {
    $("sim-out").innerHTML = `<p class="err">${err.message || err}</p>`;
    $("sim-status").textContent = "";
  } finally {
    clearInterval(poll);
    $("simulate").disabled = false;
  }
}

$("simulate").onclick = simulate;

fetch("/api/bots").then((r) => r.json()).then(({ bots }) => {
  $("bot").innerHTML = Object.entries(bots)
    .map(([k, v]) => `<option value="${k}">${v}</option>`).join("");
  $("bot").value = "win_stay_lose_shift";
});

lock();
