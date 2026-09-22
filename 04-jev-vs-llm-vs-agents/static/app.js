const $ = (id) => document.getElementById(id);
const pct = (p) => `${Math.round(p * 100)}%`;
const money = (c) => `$${c < 0.01 ? c.toFixed(5) : c.toFixed(4)}`;

let totalRows = 100;

document.querySelectorAll(".tabs button").forEach((b) => {
  b.onclick = () => {
    document.querySelectorAll(".tabs button").forEach((x) => x.classList.toggle("on", x === b));
    document.querySelectorAll("[data-panel]").forEach((p) => {
      p.hidden = p.dataset.panel !== b.dataset.tab;
    });
  };
});

function laneCard(lane) {
  const share = totalRows ? lane.done / totalRows : 0;
  return `
    <div class="lane ${lane.name}">
      <h3><span>${lane.label}</span><span class="hint">${lane.finished ? "done" : "running"}</span></h3>
      <div class="track"><div class="fill" style="width:${(share * 100).toFixed(1)}%"></div></div>
      <div class="stats">
        <div class="stat"><div class="k">rows</div><div class="v">${lane.done}<small>/${totalRows}</small></div></div>
        <div class="stat"><div class="k">wall clock</div><div class="v">${lane.wall_s.toFixed(2)}<small>s</small></div></div>
        <div class="stat"><div class="k">cost</div><div class="v">${money(lane.cost)}</div></div>
      </div>
      <div class="stats" style="margin-top:14px">
        <div class="stat"><div class="k">rows / sec</div><div class="v" style="font-size:20px">${lane.rows_per_s.toFixed(1)}</div></div>
        <div class="stat"><div class="k">median call</div><div class="v" style="font-size:20px">${Math.round(lane.p50_latency * 1000)}<small>ms</small></div></div>
        <div class="stat"><div class="k">tokens in/out</div><div class="v" style="font-size:20px">${lane.input_tokens}<small>/${lane.output_tokens}</small></div></div>
      </div>
      ${lane.errors ? `<p class="err">${lane.errors} rows errored</p>` : ""}
    </div>`;
}

function drawLanes(lanes) {
  $("lanes").innerHTML = lanes.map(laneCard).join("");
}

function reliabilityChart(lane) {
  const W = 300, H = 300, pad = 34;
  const x = (v) => pad + v * (W - pad * 2);
  const y = (v) => H - pad - v * (H - pad * 2);
  const pts = lane.bins.filter((b) => b.n > 0);
  const path = pts.map((b, i) => `${i ? "L" : "M"} ${x(b.confidence).toFixed(1)} ${y(b.accuracy).toFixed(1)}`).join(" ");
  const dots = pts.map((b) =>
    `<circle cx="${x(b.confidence).toFixed(1)}" cy="${y(b.accuracy).toFixed(1)}" r="${Math.min(7, 2 + Math.sqrt(b.n))}" fill="#1971c2" fill-opacity="0.65"/>`).join("");
  return `
    <svg viewBox="0 0 ${W} ${H}" style="width:100%;max-width:320px">
      <rect x="${pad}" y="${pad}" width="${W - pad * 2}" height="${H - pad * 2}" fill="#fff" stroke="#e2ded6"/>
      <line x1="${x(0)}" y1="${y(0)}" x2="${x(1)}" y2="${y(1)}" stroke="#c9c4ba" stroke-dasharray="5 5"/>
      <path d="${path}" fill="none" stroke="#1971c2" stroke-width="2"/>
      ${dots}
      <text x="${W / 2}" y="${H - 8}" font-size="11" text-anchor="middle" fill="#6b6b6b">how sure it said it was</text>
      <text x="12" y="${H / 2}" font-size="11" text-anchor="middle" fill="#6b6b6b" transform="rotate(-90 12 ${H / 2})">how often it was right</text>
    </svg>`;
}

function drawCalibration(cal) {
  const lanes = Object.values(cal);
  if (!lanes.length) {
    $("calibration").innerHTML = `<p class="hint">No sentiment answers came back.</p>`;
    return;
  }
  $("calibration").innerHTML = `<div class="row">${lanes.map((lane) => `
    <div>
      <h3>${lane.label}</h3>
      <div class="stats" style="margin-bottom:12px">
        <div class="stat"><div class="k">right</div><div class="v">${pct(lane.accuracy)}</div></div>
        <div class="stat"><div class="k">calibration error</div><div class="v">${lane.ece.toFixed(3)}</div></div>
        <div class="stat"><div class="k">brier</div><div class="v">${lane.brier.toFixed(3)}</div></div>
      </div>
      ${reliabilityChart(lane)}
      <p class="hint">${lane.n} rows with a sentiment answer. Lower calibration error is better; zero is perfect.</p>
    </div>`).join("")}</div>`;
}

function drawSamples(samples) {
  if (!samples || !samples.length) return;
  $("samples").innerHTML = samples.map((s) => {
    const lanes = Object.entries(s.by_lane)
      .filter(([, answers]) => Object.keys(answers).length)
      .map(([name, answers]) => {
        const parts = Object.entries(answers)
          .map(([k, a]) => `${k}: <b>${a.value}</b> ${pct(a.confidence)}`)
          .join(" &middot; ");
        return `<div class="hint" style="margin-bottom:4px"><span class="tag">${name}</span> ${parts}</div>`;
      }).join("");
    return `<tr><td style="max-width:420px">${s.review}…</td><td class="num">${s.stars}</td><td>${lanes}</td></tr>`;
  }).join("");
}

function start() {
  const lanes = [...document.querySelectorAll('.row input[type="checkbox"]')]
    .filter((c) => c.checked).map((c) => c.value);
  if (!lanes.length) return;
  totalRows = Number($("n").value);
  $("error").textContent = "";
  $("start").disabled = true;
  $("race-status").textContent = "connecting…";
  $("lanes").innerHTML = "";

  const params = new URLSearchParams({
    n: totalRows,
    concurrency: $("concurrency").value,
    lanes: lanes.join(","),
    model: $("model").value,
  });
  const source = new EventSource(`/api/race?${params}`);

  source.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.error) {
      $("error").textContent = data.error;
      source.close();
      $("start").disabled = false;
      return;
    }
    if (data.start) {
      $("race-status").textContent = `${data.rows} rows, ${data.lanes.length} lanes`;
      return;
    }
    if (data.lanes) drawLanes(data.lanes);
    if (data.done) {
      source.close();
      $("start").disabled = false;
      $("race-status").textContent = `finished in ${data.elapsed.toFixed(2)}s`;
      drawCalibration(data.calibration || {});
      drawSamples(data.samples);
    }
  };

  source.onerror = () => {
    source.close();
    $("start").disabled = false;
    $("race-status").textContent = "stream closed";
  };
}

async function runPattern() {
  $("run-pattern").disabled = true;
  $("pattern-status").textContent = "asking the language model for options…";
  $("pattern-out").innerHTML = "";
  try {
    const res = await fetch("/api/pattern", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ text: $("ticket").value }),
    });
    const d = await res.json();
    if (!res.ok) throw new Error(d.error || res.statusText);
    const options = d.actions.map((a) => `
      <tr class="${a.id === d.chosen ? "" : ""}">
        <td>${a.id === d.chosen ? "<b>" + a.id + "</b>" : a.id}</td>
        <td>${a.description}</td>
        <td class="num">${pct(d.spread[a.id] ?? 0)}</td>
      </tr>`).join("");
    $("pattern-out").innerHTML = `
      <div class="stats" style="margin-bottom:16px">
        <div class="stat"><div class="k">proposing</div><div class="v">${d.propose_seconds.toFixed(2)}<small>s</small></div></div>
        <div class="stat"><div class="k">deciding</div><div class="v">${Math.round(d.decide_seconds * 1000)}<small>ms</small></div></div>
        <div class="stat"><div class="k">picked</div><div class="v" style="font-size:20px">${d.chosen}</div></div>
        <div class="stat"><div class="k">risk</div><div class="v" style="font-size:20px">${d.risk_text}</div></div>
        <div class="stat"><div class="k">gate says</div><div class="v" style="font-size:20px">${d.gate}</div></div>
      </div>
      <table><thead><tr><th>Action</th><th>What it does</th><th class="num">Jev</th></tr></thead>
      <tbody>${options}</tbody></table>`;
    $("pattern-status").textContent = "";
  } catch (err) {
    $("pattern-status").textContent = "";
    $("pattern-out").innerHTML = `<p class="err">${err.message || err}</p>`;
  } finally {
    $("run-pattern").disabled = false;
  }
}

$("start").onclick = start;
$("run-pattern").onclick = runPattern;

fetch("/api/config").then((r) => r.json()).then((c) => {
  $("model").innerHTML = c.models.map((m) =>
    `<option ${m === c.default_model ? "selected" : ""}>${m}</option>`).join("");
  $("keys").innerHTML =
    `keys: <b>${c.jev_key ? "Jev found" : "Jev missing"}</b> &middot; ` +
    `<b>${c.openai_key ? "language model found" : "language model missing"}</b> &middot; ` +
    `${c.rows_available} reviews cached`;
  $("questions").innerHTML = c.questions.map((q) =>
    `<div class="answer" style="margin-bottom:10px">
       <div class="q">${q.kind === "noul" ? "yes or no" : q.kind === "choice" ? "pick one" : "score"}</div>
       <div style="font-size:16px">${q.instructions}</div>
     </div>`).join("");
});
