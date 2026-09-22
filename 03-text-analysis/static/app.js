const $ = (id) => document.getElementById(id);
const pct = (p) => `${Math.round(p * 100)}%`;
const ms = (s) => `${Math.round(s * 1000)}<small>ms</small>`;

function bars(options) {
  if (!options) return "";
  return `<div class="bars">${Object.entries(options)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([name, p]) => `
      <div class="bar">
        <span class="name" title="${name}">${name}</span>
        <span class="track"><span class="fill" style="width:${(p * 100).toFixed(1)}%"></span></span>
        <span class="num">${pct(p)}</span>
      </div>`).join("")}</div>`;
}

function card(a) {
  return `<div class="answer">
    <div class="q">${a.label}</div>
    <div class="v">${a.value}</div>
    <div class="sure">${pct(a.confidence)} sure</div>
    ${bars(a.options)}
  </div>`;
}

function flag(a) {
  if (!a) return "";
  const yes = a.value === "yes";
  return `<span class="tag ${yes ? "bad" : ""}">${yes ? "yes" : "no"} ${pct(a.confidence)}</span>`;
}

async function post(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

async function analyse() {
  const text = $("text").value.trim();
  if (!text) return;
  $("error").textContent = "";
  $("run").disabled = true;
  $("time").textContent = "…";
  try {
    const d = await post("/api/analyze", { text });
    $("time").innerHTML = ms(d.seconds);
    $("count").textContent = d.answers.length;
    $("cost").textContent = `$${d.cost.toFixed(6)}`;
    $("answers").innerHTML = d.answers.map(card).join("");
  } catch (err) {
    $("error").textContent = String(err.message || err);
    $("time").textContent = "—";
  } finally {
    $("run").disabled = false;
  }
}

async function compare() {
  const text = $("text").value.trim();
  if (!text) return;
  $("error").textContent = "";
  $("compare").disabled = true;
  $("compare-wrap").hidden = false;
  try {
    const d = await post("/api/compare", { text });
    $("c-one").innerHTML = ms(d.one.seconds);
    $("c-six").innerHTML = ms(d.six.seconds);
    const diff = d.six.seconds - d.one.seconds;
    $("c-diff").innerHTML = `${diff >= 0 ? "+" : ""}${Math.round(diff * 1000)}<small>ms</small>`;
  } catch (err) {
    $("error").textContent = String(err.message || err);
  } finally {
    $("compare").disabled = false;
  }
}

async function runBatch() {
  const lines = $("lines").value.split("\n").map((l) => l.trim()).filter(Boolean);
  if (!lines.length) return;
  $("run-batch").disabled = true;
  $("batch-stats").textContent = "running…";
  try {
    const d = await post("/api/batch", { lines });
    $("rows").innerHTML = d.rows.map((r) => r.error
      ? `<tr><td>${r.text}</td><td colspan="6" class="err">${r.error}</td></tr>`
      : `<tr>
          <td>${r.text.length > 70 ? r.text.slice(0, 70) + "…" : r.text}</td>
          <td>${r.answers.sentiment.value}</td>
          <td>${r.answers.intent.value}</td>
          <td>${r.answers.language.value}</td>
          <td>${flag(r.answers.has_personal_info)}</td>
          <td>${flag(r.answers.is_abusive)}</td>
          <td class="num">${Math.round(r.seconds * 1000)}</td>
        </tr>`).join("");
    $("batch-stats").textContent =
      `${d.rows.length} lines in ${d.seconds.toFixed(2)}s · ${d.per_second.toFixed(1)} per second · median call ${Math.round(d.median_call * 1000)}ms · $${d.cost.toFixed(6)}`;
  } catch (err) {
    $("error").textContent = String(err.message || err);
    $("batch-stats").textContent = "";
  } finally {
    $("run-batch").disabled = false;
  }
}

$("run").onclick = analyse;
$("compare").onclick = compare;
$("run-batch").onclick = runBatch;

fetch("/api/samples")
  .then((r) => r.json())
  .then(({ samples }) => {
    $("samples").innerHTML = samples.map((t, i) => `<option value="${i}">${t.slice(0, 44)}…</option>`).join("");
    $("samples").onchange = (e) => { $("text").value = samples[e.target.value]; };
    $("text").value = samples[0];
    $("lines").value = samples.join("\n");
  });
