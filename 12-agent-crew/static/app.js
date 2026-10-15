const $ = (id) => document.getElementById(id);
const pct = (p) => `${Math.round(p * 100)}%`;
const secs = (s) => (s < 1 ? `${Math.round(s * 1000)}ms` : `${s.toFixed(1)}s`);

let briefs = [];

function setStep(name, state) {
  const el = document.querySelector(`.step[data-step="${name}"]`);
  if (!el) return;
  if (state === "on") {
    document.querySelectorAll(".step.on").forEach((s) => s.classList.replace("on", "done"));
    el.classList.add("on");
  } else {
    el.classList.remove("on");
    el.classList.add("done");
  }
}

function resetFlow() {
  document.querySelectorAll(".step").forEach((s) => s.classList.remove("on", "done"));
}

function bar(label, value, max, note) {
  const share = Math.max(0, Math.min(1, value / max));
  return `
    <div class="bar" style="margin-bottom:7px">
      <span class="name">${label}</span>
      <span class="track"><span class="fill" style="width:${(share * 100).toFixed(1)}%"></span></span>
      <span class="num">${note}</span>
    </div>`;
}

function drawGate(g, model) {
  const yes = (p) => `${p >= 0.5 ? "yes" : "no"} <span class="hint">(${pct(Math.max(p, 1 - p))} sure)</span>`;
  $("gate").innerHTML = `
    <div class="stats" style="margin-bottom:16px">
      <div class="stat"><div class="k">decided in</div><div class="v">${secs(g.seconds)}</div></div>
      <div class="stat"><div class="k">crew runs?</div><div class="v" style="font-size:20px">${g.proceed ? "yes" : "no, blocked"}</div></div>
    </div>
    <div style="font-size:14px;line-height:2">
      <div>Clear enough to write from: <b>${yes(g.clear_enough)}</b></div>
      <div>Needs web research: <b>${yes(g.needs_research)}</b></div>
      <div>Audience: <b>${g.audience}</b> <span class="hint">(${pct(g.audience_confidence)})</span></div>
      <div>Depth: <b>${g.depth.value}</b></div>
    </div>
    <p class="hint" style="margin:12px 0 0">writer model: ${model || ""}</p>`;
}

function drawSpend(spend) {
  const total = spend.jev.cost + spend.llm.cost || 1;
  const totalTime = spend.jev.seconds + spend.llm.seconds || 1;
  $("spend").innerHTML = `
    <div class="stats" style="margin-bottom:6px">
      <div class="stat"><div class="k">Jev</div><div class="v" style="font-size:20px">$${spend.jev.cost.toFixed(6)}</div></div>
      <div class="stat"><div class="k">LLM</div><div class="v" style="font-size:20px">$${spend.llm.cost.toFixed(5)}</div></div>
    </div>
    <div class="split">
      <span class="jev" style="width:${(spend.jev.cost / total * 100).toFixed(2)}%"></span>
      <span class="llm" style="width:${(spend.llm.cost / total * 100).toFixed(2)}%"></span>
    </div>
    <div class="legend"><span><i style="background:var(--accent)"></i>Jev</span><span><i style="background:#7048e8"></i>LLM</span></div>
    <p class="hint" style="margin:14px 0 0">
      ${spend.jev.calls} Jev calls, ${secs(spend.jev.seconds)} &middot;
      ${spend.llm.calls} LLM calls, ${secs(spend.llm.seconds)}<br>
      Jev is ${(spend.jev.seconds / totalTime * 100).toFixed(1)}% of the time spent.
    </p>`;
}

function scoreRow(s) {
  const rows = [
    bar("on brief", s.on_brief, 1, s.on_brief.toFixed(2)),
    s.grounded === null ? "" : bar("grounded", s.grounded, 1, s.grounded.toFixed(2)),
    bar("clarity", s.clarity.score, 3, s.clarity.score.toFixed(2)),
    bar("hype (lower better)", s.hype.score, 3, s.hype.score.toFixed(2)),
  ];
  return `<div class="bars">${rows.join("")}</div>`;
}

function addRound(n, text) {
  const wrap = $("rounds-out");
  if (wrap.querySelector(".hint")) wrap.innerHTML = "";
  const el = document.createElement("div");
  el.className = "round";
  el.id = `round-${n}`;
  el.innerHTML = `
    <h3><span>Draft ${n}</span><span class="hint" id="v-${n}">scoring…</span></h3>
    <div class="body">
      <div class="draft">${text.replace(/</g, "&lt;")}</div>
      <div id="scores-${n}" style="margin-top:14px"></div>
    </div>`;
  wrap.appendChild(el);
}

function judgeRound(n, d) {
  const head = $(`v-${n}`);
  head.className = `verdict ${d.verdict}`;
  head.textContent = d.verdict;
  const problems = d.problems.length
    ? `<div style="margin-top:12px">${d.problems.map((p) => `<div class="problem">${p}</div>`).join("")}</div>`
    : `<p class="hint" style="margin:12px 0 0">Everything cleared the bar.</p>`;
  $(`scores-${n}`).innerHTML = scoreRow(d.scores) +
    `<p class="hint" style="margin:10px 0 0">judged in ${secs(d.seconds)}</p>` + problems;
}

function run() {
  const brief = $("brief").value.trim();
  if (!brief) return;
  $("error").textContent = "";
  $("run").disabled = true;
  $("rounds-out").innerHTML = "";
  $("final-wrap").hidden = true;
  $("sources-wrap").hidden = true;
  resetFlow();

  const params = new URLSearchParams({
    brief, max_rounds: $("rounds").value, model: $("model").value,
  });
  const source = new EventSource(`/api/run?${params}`);

  source.onmessage = (event) => {
    const d = JSON.parse(event.data);
    if (d.spend) drawSpend(d.spend);

    switch (d.stage) {
      case "error":
        $("error").textContent = d.message;
        source.close(); $("run").disabled = false;
        break;
      case "gate_start": setStep("gate", "on"); break;
      case "gate":
        setStep("gate", "done");
        drawGate(d.data, $("model").value);
        break;
      case "research_start":
        setStep("research", "on");
        if (!d.search_available) {
          $("error").textContent =
            "No TAVILY_API_KEY set, so the researcher works from what the model already knows.";
        }
        break;
      case "research": {
        setStep("research", "done");
        const s = d.sources;
        $("sources-wrap").hidden = false;
        $("sources").innerHTML = s.sources.length
          ? `<p class="hint" style="margin-top:0">searched: ${s.queries.map((q) => `"${q}"`).join(", ")}</p>` +
            s.sources.map((x) => `<div class="src"><a href="${x.url}" target="_blank">${x.title || x.url}</a></div>`).join("")
          : `<p class="hint" style="margin:0">No sources retrieved.</p>`;
        break;
      }
      case "writing": setStep("writing", "on"); break;
      case "draft":
        setStep("writing", "done");
        setStep("judged", "on");
        addRound(d.round, d.text);
        break;
      case "judged": judgeRound(d.round, d); break;
      case "rewriting":
        setStep("rewriting", "on");
        break;
      case "stalled":
        $("error").textContent =
          `Stopped after round ${d.round}: the rewrite did not move the draft closer to passing, so another lap would just cost money.`;
        break;
      case "done": {
        setStep("done", "done");
        source.close();
        $("run").disabled = false;
        $("final-wrap").hidden = !d.final;
        if (d.final) $("final").textContent = d.final;
        const note = d.reason ? ` — ${d.reason}` : "";
        $("rounds-out").insertAdjacentHTML("beforeend",
          `<p class="hint">verdict: <b>${d.verdict}</b> after ${d.rounds} round${d.rounds === 1 ? "" : "s"}, ${secs(d.elapsed)} total${note}</p>`);
        break;
      }
    }
  };

  source.onerror = () => { source.close(); $("run").disabled = false; };
}

$("run").onclick = run;

fetch("/api/config").then((r) => r.json()).then((c) => {
  briefs = c.briefs;
  $("examples").innerHTML = briefs.map((b, i) => `<option value="${i}">${b.slice(0, 52)}…</option>`).join("");
  $("examples").onchange = (e) => { $("brief").value = briefs[e.target.value]; };
  $("brief").value = briefs[0];
  $("model").innerHTML = c.llm_models.map((m) =>
    `<option ${m === c.llm_model ? "selected" : ""}>${m}</option>`).join("");
  $("keys").innerHTML =
    `<b>Jev ${c.jev ? "ready" : "missing"}</b> &middot; <b>LLM ${c.llm ? "ready" : "missing"}</b> &middot; ` +
    `<b>web search ${c.search ? "on" : "off"}</b> &middot; publishes at on-brief ${c.thresholds.on_brief}, ` +
    `clarity ${c.thresholds.clarity_min}, hype under ${c.thresholds.hype_max}`;
});
