const $ = (id) => document.getElementById(id);
const pct = (p) => `${Math.round(p * 100)}%`;
const fmtTime = (s) => (s < 1 ? `${Math.round(s * 1000)}<small>ms</small>` : `${s.toFixed(2)}<small>s</small>`);

const TAG = { code: "tag", jev: "tag good", llm: "tag warn" };

function bars(options) {
  return Object.entries(options)
    .sort((a, b) => b[1] - a[1])
    .map(([name, p]) => `
      <div class="bar">
        <span class="name">${name}</span>
        <span class="track"><span class="fill" style="width:${(p * 100).toFixed(1)}%"></span></span>
        <span class="num">${pct(p)}</span>
      </div>`)
    .join("");
}

function yesNo(p) {
  return `${p >= 0.5 ? "yes" : "no"} <span class="hint">(${pct(Math.max(p, 1 - p))} sure)</span>`;
}

function showVerdict(d) {
  $("verdict-wrap").hidden = false;
  $("owner").textContent = d.owner_text;
  $("owner-sure").textContent = `${pct(d.owner_confidence)} sure`;
  $("owner-bars").innerHTML = bars(d.owner_spread);
  $("time").innerHTML = fmtTime(d.seconds);
  $("reasons").innerHTML = [
    ["Are the answers known in advance?", yesNo(d.fixed_answers)],
    ["Does it have to write prose?", yesNo(d.writes_text)],
    ["How much reasoning?", `${d.reasoning_text} <span class="hint">(${d.reasoning_score.toFixed(2)} of 3)</span>`],
  ].map(([q, v]) => `<div class="answer"><div class="q">${q}</div><div class="v" style="font-size:19px">${v}</div></div>`).join("");
}

async function decide() {
  const text = $("job").value.trim();
  if (!text) return;
  $("error").textContent = "";
  $("decide").disabled = true;
  try {
    const res = await fetch("/api/decide", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ text }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || res.statusText);
    showVerdict(data);
  } catch (err) {
    $("error").textContent = String(err.message || err);
  } finally {
    $("decide").disabled = false;
  }
}

async function runAll() {
  $("run-all").disabled = true;
  $("batch-stats").textContent = "running twelve calls in parallel…";
  $("rows").innerHTML = "";
  try {
    const res = await fetch("/api/batch", { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || res.statusText);
    $("rows").innerHTML = data.rows.map((r) => r.error
      ? `<tr><td>${r.job}</td><td colspan="5" class="err">${r.error}</td></tr>`
      : `<tr>
          <td>${r.job}</td>
          <td><span class="${TAG[r.owner] || "tag"}">${r.owner_text}</span></td>
          <td class="num">${pct(r.owner_confidence)}</td>
          <td>${yesNo(r.fixed_answers)}</td>
          <td>${yesNo(r.writes_text)}</td>
          <td>${r.reasoning_text}</td>
        </tr>`).join("");
    $("batch-stats").textContent =
      `twelve jobs in ${data.seconds.toFixed(2)}s, $${data.cost.toFixed(6)} total`;
  } catch (err) {
    $("error").textContent = String(err.message || err);
    $("batch-stats").textContent = "";
  } finally {
    $("run-all").disabled = false;
  }
}

$("decide").onclick = decide;
$("run-all").onclick = runAll;

fetch("/api/tasks")
  .then((r) => r.json())
  .then(({ tasks }) => {
    $("examples").innerHTML = tasks.map((t, i) => `<option value="${i}">${t}</option>`).join("");
    $("examples").onchange = (e) => { $("job").value = tasks[e.target.value]; };
  });
