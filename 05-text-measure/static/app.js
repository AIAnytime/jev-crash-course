const $ = (id) => document.getElementById(id);
const pct = (p) => `${Math.round(p * 100)}%`;
let samples = {};

function meter(s) {
  const top = s.levels - 1;
  const share = top > 0 ? s.score / top : 0;
  return `
    <div class="meter">
      <div class="head"><b>${s.label}</b><span>${s.value}</span></div>
      <div class="track"><div class="fill" style="width:${(share * 100).toFixed(1)}%"></div></div>
      <div class="ticks"><span>${s.score.toFixed(2)} of ${top}</span><span>${pct(s.confidence)} sure</span></div>
    </div>`;
}

function flag(s) {
  const yes = s.value === "yes";
  return `<span class="tag ${yes ? "good" : "warn"}">${s.label}: ${s.value} (${pct(Math.max(s.probability, 1 - s.probability))})</span>`;
}

function paint(d) {
  $("time").innerHTML = `${Math.round(d.seconds * 1000)}<small>ms</small>`;
  $("words").textContent = d.words;
  $("cost").textContent = `$${d.cost.toFixed(6)}`;
  const scores = Object.values(d.scores);
  $("meters").innerHTML = scores.filter((s) => s.kind === "score").map(meter).join("");
  $("flags").innerHTML = scores.filter((s) => s.kind === "noul").map(flag).join("");
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

let inFlight = false;
async function measure() {
  const text = $("text").value.trim();
  if (!text || inFlight) return;
  inFlight = true;
  $("error").textContent = "";
  try {
    paint(await post("/api/measure", { text }));
  } catch (err) {
    $("error").textContent = String(err.message || err);
  } finally {
    inFlight = false;
  }
}

let timer = null;
$("text").addEventListener("input", () => {
  if (!$("live").checked) return;
  clearTimeout(timer);
  timer = setTimeout(measure, 700);
});

async function compare() {
  $("compare").disabled = true;
  $("compare-status").textContent = "measuring both…";
  try {
    const d = await post("/api/compare", { a: $("a").value, b: $("b").value });
    const keys = Object.keys(d.a.scores);
    const rows = keys.map((k) => {
      const a = d.a.scores[k];
      const b = d.b.scores[k];
      if (a.kind === "score") {
        const delta = b.score - a.score;
        const tag = Math.abs(delta) < 0.15 ? "tag" : delta > 0 ? "tag good" : "tag warn";
        return `<tr>
          <td>${a.label}</td>
          <td class="num">${a.score.toFixed(2)}</td>
          <td class="num">${b.score.toFixed(2)}</td>
          <td><span class="${tag}">${delta >= 0 ? "+" : ""}${delta.toFixed(2)}</span></td>
          <td class="hint">${b.value}</td>
        </tr>`;
      }
      return `<tr>
        <td>${a.label}</td>
        <td class="num">${pct(a.probability)}</td>
        <td class="num">${pct(b.probability)}</td>
        <td><span class="tag">${b.probability >= a.probability ? "+" : ""}${pct(b.probability - a.probability)}</span></td>
        <td class="hint">${b.value}</td>
      </tr>`;
    }).join("");
    $("compare-out").innerHTML = `
      <table>
        <thead><tr><th>Measure</th><th class="num">A</th><th class="num">B</th><th>Change</th><th>B reads as</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
    $("compare-status").textContent =
      `both measured in ${Math.round(d.seconds * 1000)}ms`;
  } catch (err) {
    $("compare-out").innerHTML = `<p class="err">${err.message || err}</p>`;
    $("compare-status").textContent = "";
  } finally {
    $("compare").disabled = false;
  }
}

$("measure").onclick = measure;
$("compare").onclick = compare;

fetch("/api/samples").then((r) => r.json()).then((d) => {
  samples = d.samples;
  const names = Object.keys(samples);
  $("samples").innerHTML = names.map((n) => `<option>${n}</option>`).join("");
  $("samples").onchange = (e) => { $("text").value = samples[e.target.value]; measure(); };
  $("text").value = samples[names[0]];
  $("a").value = samples[names[0]];
  $("b").value = samples[names[1]];
  measure();
});
