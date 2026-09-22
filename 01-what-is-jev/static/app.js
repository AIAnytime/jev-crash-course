const $ = (id) => document.getElementById(id);

const fmtTime = (s) => (s < 1 ? `${Math.round(s * 1000)}<small>ms</small>` : `${s.toFixed(2)}<small>s</small>`);
const fmtCost = (c) => `$${c.toFixed(6)}`;
const pct = (p) => `${Math.round(p * 100)}%`;

function bars(options) {
  if (!options) return "";
  const rows = Object.entries(options)
    .sort((a, b) => b[1] - a[1])
    .map(([name, p]) => `
      <div class="bar">
        <span class="name" title="${name}">${name}</span>
        <span class="track"><span class="fill" style="width:${(p * 100).toFixed(1)}%"></span></span>
        <span class="num">${pct(p)}</span>
      </div>`)
    .join("");
  return `<div class="bars">${rows}</div>`;
}

function card(answer) {
  return `
    <div class="answer">
      <div class="q">${answer.question}</div>
      <div class="v">${answer.value}</div>
      <div class="sure">${pct(answer.confidence)} sure</div>
      ${bars(answer.options)}
    </div>`;
}

async function run(which) {
  const text = $("text").value.trim();
  if (!text) return;
  $("error").textContent = "";
  const btn = which === "jev" ? $("run-jev") : $("run-llm");
  const label = btn.textContent;
  btn.disabled = true;
  btn.textContent = "asking…";
  $(`${which}-time`).textContent = "…";

  try {
    const res = await fetch(`/api/${which}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ text }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || res.statusText);
    $(`${which}-time`).innerHTML = fmtTime(data.seconds);
    $(`${which}-cost`).textContent = fmtCost(data.cost);
    $(`${which}-answers`).innerHTML = data.answers.map(card).join("");
    if (which === "llm") $("llm-raw").textContent = data.raw || "";
  } catch (err) {
    $("error").textContent = String(err.message || err);
    $(`${which}-time`).textContent = "—";
  } finally {
    btn.disabled = false;
    btn.textContent = label;
  }
}

$("run-jev").onclick = () => run("jev");
$("run-llm").onclick = () => run("llm");

fetch("/api/examples")
  .then((r) => r.json())
  .then(({ examples }) => {
    $("examples").innerHTML = examples
      .map((t, i) => `<option value="${i}">${t.slice(0, 46)}…</option>`)
      .join("");
    $("examples").onchange = (e) => { $("text").value = examples[e.target.value]; };
    $("text").value = examples[0];
  });
