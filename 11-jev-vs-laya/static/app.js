const $ = (id) => document.getElementById(id);
const pct = (p) => `${Math.round(p * 100)}%`;
const ms = (s) => (s < 1 ? `${Math.round(s * 1000)}<small>ms</small>` : `${s.toFixed(2)}<small>s</small>`);

document.querySelectorAll(".tabs button").forEach((b) => {
  b.onclick = () => {
    document.querySelectorAll(".tabs button").forEach((x) => x.classList.toggle("on", x === b));
    document.querySelectorAll("[data-panel]").forEach((p) => {
      p.hidden = p.dataset.panel !== b.dataset.tab;
    });
  };
});

function bars(probabilities, chosen) {
  return `<div class="bars">${Object.entries(probabilities)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
    .map(([name, p]) => `
      <div class="bar">
        <span class="name"${name === chosen ? ' style="color:var(--ink)"' : ""}>${name}</span>
        <span class="track"><span class="fill" style="width:${(p * 100).toFixed(1)}%"></span></span>
        <span class="num">${pct(p)}</span>
      </div>`).join("")}</div>`;
}

function answerCard(key, a, agree) {
  const badge = agree === undefined ? ""
    : `<span class="agree ${agree ? "same" : "diff"}">${agree ? "same" : "differs"}</span>`;
  return `
    <div class="answer" style="margin-bottom:12px">
      <div class="q" style="display:flex;justify-content:space-between">${key} ${badge}</div>
      <div class="v" style="font-size:20px">${a.value}</div>
      <div class="sure">${pct(a.confidence)} sure${a.kind === "score" ? ` &middot; ${a.score.toFixed(2)}` : ""}</div>
      ${bars(a.probabilities, a.value)}
    </div>`;
}

function laneCard(name, data, agreement) {
  if (!data || data.error) {
    return `<div><div class="lane ${name}"><h3>${name}</h3><p class="err">${(data && data.error) || "not run"}</p></div></div>`;
  }
  const label = name === "jev" ? "Jev" : "Laya";
  const where = name === "jev" ? "hosted API" : "on this machine";
  const keys = Object.keys(data.answers);
  return `
    <div>
      <div class="lane ${name}">
        <h3><span>${label}</span><span class="where">${where}</span></h3>
        <div class="stats" style="margin:14px 0 18px">
          <div class="stat"><div class="k">answered in</div><div class="v">${ms(data.seconds)}</div></div>
          <div class="stat"><div class="k">cost</div><div class="v">${data.cost ? "$" + data.cost.toFixed(6) : "$0"}</div></div>
        </div>
        ${keys.map((k) => answerCard(k, data.answers[k], name === "laya" ? agreement[k] : undefined)).join("")}
      </div>
    </div>`;
}

async function post(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: body === undefined ? "{}" : JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

async function warm() {
  $("warm").disabled = true;
  $("one-status").textContent = "loading the weights, this takes a moment the first time…";
  try {
    const d = await post("/api/warm");
    $("one-status").textContent = `Laya loaded in ${d.seconds.toFixed(1)}s on ${d.device}`;
    loadConfig();
  } catch (err) {
    $("error").textContent = String(err.message || err);
    $("one-status").textContent = "";
  } finally {
    $("warm").disabled = false;
  }
}

async function ask() {
  $("ask").disabled = true;
  $("error").textContent = "";
  $("one-status").textContent = "asking both…";
  try {
    const d = await post("/api/ask", { text: $("text").value });
    $("lanes").innerHTML = laneCard("jev", d.jev, d.agreement) + laneCard("laya", d.laya, d.agreement);
    const same = Object.values(d.agreement).filter(Boolean).length;
    const total = Object.keys(d.agreement).length;
    $("one-status").textContent = total ? `${same} of ${total} answers matched` : "";
  } catch (err) {
    $("error").textContent = String(err.message || err);
    $("one-status").textContent = "";
  } finally {
    $("ask").disabled = false;
  }
}

function reliabilityChart(lane, colour) {
  const W = 260, H = 260, pad = 30;
  const x = (v) => pad + v * (W - pad * 2);
  const y = (v) => H - pad - v * (H - pad * 2);
  const pts = (lane.bins || []).filter((b) => b.n > 0);
  const path = pts.map((b, i) => `${i ? "L" : "M"} ${x(b.confidence).toFixed(1)} ${y(b.accuracy).toFixed(1)}`).join(" ");
  return `
    <svg viewBox="0 0 ${W} ${H}" style="width:100%;max-width:280px">
      <rect x="${pad}" y="${pad}" width="${W - pad * 2}" height="${H - pad * 2}" fill="#fff" stroke="#e2ded6"/>
      <line x1="${x(0)}" y1="${y(0)}" x2="${x(1)}" y2="${y(1)}" stroke="#c9c4ba" stroke-dasharray="5 5"/>
      <path d="${path}" fill="none" stroke="${colour}" stroke-width="2"/>
      ${pts.map((b) => `<circle cx="${x(b.confidence).toFixed(1)}" cy="${y(b.accuracy).toFixed(1)}" r="${Math.min(7, 2 + Math.sqrt(b.n))}" fill="${colour}" fill-opacity="0.6"/>`).join("")}
      <text x="${W / 2}" y="${H - 6}" font-size="10" text-anchor="middle" fill="#6b6b6b">how sure it said it was</text>
    </svg>`;
}

function benchLane(name, lane) {
  const colour = name === "jev" ? "#1971c2" : "#7048e8";
  return `
    <div>
      <div class="lane ${name}">
        <h3><span>${lane.label}</span><span class="where">${lane.where}</span></h3>
        <div class="stats" style="margin:14px 0">
          <div class="stat"><div class="k">right</div><div class="v">${pct(lane.accuracy)}</div></div>
          <div class="stat"><div class="k">calibration error</div><div class="v">${lane.ece.toFixed(3)}</div></div>
          <div class="stat"><div class="k">brier</div><div class="v">${lane.brier.toFixed(3)}</div></div>
        </div>
        <div class="stats" style="margin-bottom:16px">
          <div class="stat"><div class="k">median call</div><div class="v" style="font-size:20px">${ms(lane.median_call)}</div></div>
          <div class="stat"><div class="k">wall clock</div><div class="v" style="font-size:20px">${lane.wall.toFixed(1)}<small>s</small></div></div>
          <div class="stat"><div class="k">cost</div><div class="v" style="font-size:20px">${lane.cost ? "$" + lane.cost.toFixed(5) : "$0"}</div></div>
        </div>
        ${reliabilityChart(lane, colour)}
        <p class="hint">${lane.concurrency > 1 ? `${lane.concurrency} calls in flight` : `one at a time on ${lane.device || "this machine"}`}${lane.errors ? ` &middot; ${lane.errors} errored` : ""}</p>
      </div>
    </div>`;
}

async function runBench() {
  $("run-bench").disabled = true;
  $("bench-status").textContent = "starting…";
  const poll = setInterval(async () => {
    try {
      const p = await (await fetch("/api/progress")).json();
      $("bench-status").textContent = `${p.stage} · ${p.done} of ${p.total}`;
    } catch (_) { /* busy */ }
  }, 400);
  try {
    const d = await post("/api/bench", {
      n: Number($("n").value),
      concurrency: Number($("concurrency").value),
    });
    $("bench-lanes").innerHTML = benchLane("jev", d.jev) + benchLane("laya", d.laya);
    $("agreement").innerHTML = Object.entries(d.agreement).map(([k, v]) => `
      <div class="bar">
        <span class="name">${k}</span>
        <span class="track"><span class="fill" style="width:${(v * 100).toFixed(1)}%"></span></span>
        <span class="num">${pct(v)}</span>
      </div>`).join("");
    const rows = [...d.samples].sort((a, b) =>
      (a.jev.value === a.laya.value) - (b.jev.value === b.laya.value));
    $("samples").innerHTML = rows.map((s) => {
      const cell = (a) => `<span class="${a.value === s.truth ? "hit" : "miss"}">${a.value}</span> <span class="hint">${pct(a.confidence)}</span>`;
      return `<tr>
        <td class="wrap">${s.text}…</td>
        <td class="num">${s.stars}</td>
        <td>${s.truth}</td>
        <td>${cell(s.jev)}</td>
        <td>${cell(s.laya)}</td>
      </tr>`;
    }).join("");
    $("bench-status").textContent = `${d.rows} reviews through both`;
  } catch (err) {
    $("bench-status").textContent = "";
    $("samples").innerHTML = `<tr><td colspan="5" class="err">${err.message || err}</td></tr>`;
  } finally {
    clearInterval(poll);
    $("run-bench").disabled = false;
  }
}

async function runLanguages() {
  $("run-langs").disabled = true;
  $("lang-status").textContent = "running, the multilingual weights load on first use…";
  try {
    const d = await post("/api/languages");
    const cell = (x) => {
      if (!x || x.error) return `<td class="err">${(x && x.error) ? "failed" : "—"}</td>`;
      const a = x.answers.sentiment;
      return `<td>${a.value} <span class="hint">${pct(a.confidence)} · ${Math.round(x.seconds * 1000)}ms</span></td>`;
    };
    $("langs").innerHTML = d.rows.map((r) => `
      <tr>
        <td><b>${r.language}</b><br><span class="hint">${r.text.slice(0, 44)}…</span></td>
        <td>${r.script}</td>
        ${cell(r.jev)}${cell(r.laya_english)}${cell(r.laya_multilingual)}
      </tr>`).join("");
    $("lang-status").textContent = "every line is the same complaint";
  } catch (err) {
    $("lang-status").textContent = "";
    $("langs").innerHTML = `<tr><td colspan="5" class="err">${err.message || err}</td></tr>`;
  } finally {
    $("run-langs").disabled = false;
  }
}

function loadConfig() {
  fetch("/api/config").then((r) => r.json()).then((c) => {
    $("keys").innerHTML =
      `<b>${c.jev_ready ? "Jev key found" : "Jev key missing"}</b> &middot; ` +
      `<b>Laya ${c.laya_loaded ? `loaded on ${c.laya_device}` : "not loaded yet"}</b> &middot; ` +
      `${c.reviews} reviews cached`;
    $("questions").innerHTML = c.questions.map((q) => `
      <div class="answer" style="margin-bottom:10px">
        <div class="q">${q.kind === "noul" ? "yes or no" : q.kind === "choice" ? "pick one" : "score"}</div>
        <div style="font-size:16px">${q.instructions}</div>
      </div>`).join("");
  });
}

$("ask").onclick = ask;
$("warm").onclick = warm;
$("run-bench").onclick = runBench;
$("run-langs").onclick = runLanguages;
loadConfig();
