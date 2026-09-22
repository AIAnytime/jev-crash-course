const $ = (id) => document.getElementById(id);
const pct = (p) => `${Math.round(p * 100)}%`;
let samples = {};

const ABOUT = {
  term_renewal: "term and renewal", fees: "fees", liability: "liability",
  service_levels: "service levels", data: "data", termination: "termination",
  governing_law: "governing law", assignment: "assignment",
  confidentiality: "confidentiality", other: "other",
};

const FAVOURS = { us: "us", them: "the other side", balanced: "balanced" };

function clauseRow(c) {
  if (c.error) {
    return `<tr><td>${c.heading}</td><td colspan="4" class="err">${c.error}</td></tr>`;
  }
  const flags = [
    c.needs_redraft >= 0.5 ? `<span class="tag bad">redraft</span>` : "",
    c.unusual >= 0.5 ? `<span class="tag warn">unusual</span>` : "",
  ].join(" ");
  const favourTag = c.favours === "them" ? "tag warn" : c.favours === "us" ? "tag good" : "tag";
  return `
    <tr class="clause" data-n="${c.number}">
      <td>${c.heading}</td>
      <td>${ABOUT[c.kind] || c.kind}</td>
      <td><span class="${favourTag}">${FAVOURS[c.favours] || c.favours}</span></td>
      <td><span class="risk r${c.risk_level}"><span class="dot"></span>${c.risk_word}</span></td>
      <td>${flags}</td>
    </tr>
    <tr class="detail" id="d${c.number}" hidden>
      <td colspan="5">
        <p style="margin:0 0 10px">${c.text}</p>
        <div class="bars" style="max-width:420px">
          ${Object.entries(c.risk_spread).map(([k, v]) => `
            <div class="bar"><span class="name">${k}</span>
              <span class="track"><span class="fill" style="width:${(v * 100).toFixed(1)}%"></span></span>
              <span class="num">${pct(v)}</span></div>`).join("")}
        </div>
        <p class="hint" style="margin:10px 0 0">
          risk score ${c.risk_score.toFixed(2)} of 3 &middot;
          favours ${FAVOURS[c.favours]} at ${pct(c.favours_confidence)} &middot;
          unusual ${pct(c.unusual)} &middot; needs redrafting ${pct(c.needs_redraft)}
        </p>
      </td>
    </tr>`;
}

function paint(d) {
  const sorted = [...d.clauses].sort((a, b) => (b.risk_score ?? -1) - (a.risk_score ?? -1));
  $("rows").innerHTML = sorted.map(clauseRow).join("");
  $("rows").querySelectorAll("tr.clause").forEach((tr) => {
    tr.onclick = () => {
      const detail = $(`d${tr.dataset.n}`);
      detail.hidden = !detail.hidden;
    };
  });
  $("checklist").innerHTML = d.checklist.map((i) => `
    <div class="check ${i.present ? "yes" : "no"}">
      <span class="mark">${i.present ? "✓" : "✗"}</span>
      <span>${i.question}<br><span class="hint">${pct(i.probability)} sure it is there</span></span>
    </div>`).join("");
  $("s-clauses").textContent = d.summary.clauses;
  $("s-negotiate").textContent = d.summary.to_negotiate;
  $("s-missing").textContent = d.summary.missing_protections;
  $("s-time").innerHTML = `${d.seconds.toFixed(2)}<small>s</small>`;
  $("s-cost").textContent = `$${d.cost.toFixed(5)}`;
  $("status").textContent = `${d.calls} calls, run at the same time`;
}

async function run() {
  $("error").textContent = "";
  $("run").disabled = true;
  $("status").textContent = "reading every clause…";
  try {
    const res = await fetch("/api/review", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ text: $("text").value, reviewing_for: $("side").value }),
    });
    const d = await res.json();
    if (!res.ok) throw new Error(d.error || res.statusText);
    paint(d);
  } catch (err) {
    $("error").textContent = String(err.message || err);
    $("status").textContent = "";
  } finally {
    $("run").disabled = false;
  }
}

$("run").onclick = run;

fetch("/api/samples").then((r) => r.json()).then((d) => {
  samples = d.samples;
  const names = Object.keys(samples);
  $("samples").innerHTML = names.map((n) => `<option>${n}</option>`).join("");
  $("samples").onchange = (e) => { $("text").value = samples[e.target.value]; };
  $("text").value = samples[names[0]];
  $("side").innerHTML = Object.entries(d.perspectives)
    .map(([k, v]) => `<option value="${k}">${v}</option>`).join("");
});
