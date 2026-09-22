const $ = (id) => document.getElementById(id);
const pct = (p) => `${Math.round(p * 100)}%`;
const LANE = { jev: "Jev", llm: "language model" };

function summaryCard(lane, s) {
  return `
    <div>
      <h3>${LANE[lane] || lane}</h3>
      <div class="panel">
        <div class="stats">
          <div class="stat"><div class="k">answers changed</div><div class="v">${s.flipped}<small>/${s.attempts}</small></div></div>
          <div class="stat"><div class="k">abuse calls flipped</div><div class="v">${s.abuse_flips}</div></div>
          <div class="stat"><div class="k">priority changed</div><div class="v">${s.priority_flips}</div></div>
        </div>
        <p class="hint" style="margin:14px 0 0">
          biggest drop in the abusive probability: ${s.largest_shift.toFixed(2)}
        </p>
      </div>
    </div>`;
}

function detailColumn(lane, rows, clean) {
  const before = clean[lane]?.["abusive complaint"]?.abusive ?? 0;
  const items = rows.filter((r) => r.lane === lane && r.message === "abusive complaint" && !r.error);
  return `
    <div>
      <h3>${LANE[lane] || lane}</h3>
      <p class="hint">clean answer: ${pct(before)} abusive</p>
      ${items.map((r) => {
        const flipped = r.flipped_abuse;
        return `<div class="shift" style="padding:7px 0;border-bottom:1px solid var(--line)">
          <span style="flex:1">${r.attack}</span>
          <span>${r.abusive_before.toFixed(2)}</span>
          <span class="arrow">&rarr;</span>
          <b class="${flipped ? "down" : "same"}">${r.abusive_after.toFixed(2)}</b>
          ${flipped ? `<span class="tag bad">flipped</span>` : ""}
        </div>`;
      }).join("")}
    </div>`;
}

async function run() {
  $("run").disabled = true;
  $("error").textContent = "";
  $("status").textContent = "running every message against every attack…";
  try {
    const res = await fetch("/api/run?lanes=jev,llm", { method: "POST" });
    const d = await res.json();
    if (!res.ok) throw new Error(d.error || res.statusText);

    for (const lane of d.lanes) {
      const rows = d.rows.filter((r) => r.lane === lane && !r.error);
      d.summary[lane].abuse_flips = rows.filter((r) => r.flipped_abuse).length;
      d.summary[lane].priority_flips = rows.filter((r) => r.flipped_priority).length;
    }
    $("summary").innerHTML = d.lanes.map((l) => summaryCard(l, d.summary[l])).join("");

    const head = `<div class="h">what was smuggled in</div>` +
      d.lanes.map((l) => `<div class="h cell">${LANE[l] || l}</div>`).join("");
    $("grid").innerHTML = head + Object.entries(d.by_attack).map(([attack, per]) =>
      `<div>${attack}</div>` + d.lanes.map((l) =>
        `<div class="cell ${per[l] ? "moved" : "held"}">${per[l] ? "moved" : "held"}</div>`).join("")
    ).join("");

    $("detail").innerHTML = d.lanes.map((l) => detailColumn(l, d.rows, d.clean)).join("");
    $("status").textContent = `${d.rows.length} runs in ${d.seconds.toFixed(1)}s`;
  } catch (err) {
    $("error").textContent = String(err.message || err);
    $("status").textContent = "";
  } finally {
    $("run").disabled = false;
  }
}

async function tryOne() {
  $("try").disabled = true;
  $("try-status").textContent = "asking twice, with and without…";
  try {
    const res = await fetch("/api/try", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ message: $("message").value, attack: $("attack").value }),
    });
    const d = await res.json();
    if (!res.ok) throw new Error(d.error || res.statusText);
    $("try-out").innerHTML = `
      <div class="stats">
        <div class="stat"><div class="k">abusive, clean</div><div class="v">${pct(d.clean.abusive)}</div></div>
        <div class="stat"><div class="k">abusive, attacked</div><div class="v">${pct(d.attacked.abusive)}</div></div>
        <div class="stat"><div class="k">moved by</div><div class="v">${(d.abusive_shift * 100).toFixed(1)}<small>pts</small></div></div>
        <div class="stat"><div class="k">priority</div><div class="v" style="font-size:20px">${d.priority_before} → ${d.priority_after}</div></div>
        <div class="stat"><div class="k">answer changed</div><div class="v" style="font-size:20px">${d.flipped ? "yes" : "no"}</div></div>
      </div>`;
    $("try-status").textContent = "";
  } catch (err) {
    $("try-out").innerHTML = `<p class="err">${err.message || err}</p>`;
    $("try-status").textContent = "";
  } finally {
    $("try").disabled = false;
  }
}

$("run").onclick = run;
$("try").onclick = tryOne;
