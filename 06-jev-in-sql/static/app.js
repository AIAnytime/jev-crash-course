const $ = (id) => document.getElementById(id);
let presets = [];
let poller = null;

function startPolling() {
  const t0 = performance.now();
  poller = setInterval(async () => {
    try {
      const s = await (await fetch("/api/progress")).json();
      const secs = ((performance.now() - t0) / 1000).toFixed(1);
      $("status").textContent =
        `running ${secs}s · ${s.calls} calls made · $${s.cost.toFixed(5)} so far`;
      $("calls").textContent = s.calls;
    } catch (_) { /* the query is busy; try again next tick */ }
  }, 300);
}

function stopPolling() {
  clearInterval(poller);
  poller = null;
}

async function run() {
  $("error").textContent = "";
  $("run").disabled = true;
  $("body").innerHTML = `<tr><td class="hint">working…</td></tr>`;
  startPolling();
  try {
    const res = await fetch("/api/query", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ sql: $("sql").value, limit: Number($("limit").value) }),
    });
    const d = await res.json();
    if (!res.ok) throw new Error(d.error || res.statusText);
    $("time").innerHTML = `${d.seconds.toFixed(2)}<small>s</small>`;
    $("scanned").textContent = d.scanned;
    $("calls").textContent = d.calls;
    $("cached").textContent = d.cached;
    $("cost").textContent = `$${d.cost.toFixed(5)}`;
    $("head").innerHTML = `<tr>${d.columns.map((c) => `<th>${c}</th>`).join("")}</tr>`;
    $("body").innerHTML = d.rows.map((row) =>
      `<tr>${row.map((v) => {
        if (v === null) return `<td class="hint">null</td>`;
        if (typeof v === "number") return `<td class="num">${v}</td>`;
        return `<td class="${v.length > 60 ? "wrap" : ""}">${v}</td>`;
      }).join("")}</tr>`).join("");
    $("rowcount").textContent =
      `${d.row_count} rows returned${d.row_count > d.rows.length ? `, showing the first ${d.rows.length}` : ""}` +
      `${d.errors ? ` · ${d.errors} calls failed` : ""}`;
    $("status").textContent = `${d.calls} calls, ${d.cached} already cached`;
  } catch (err) {
    $("error").textContent = String(err.message || err);
    $("body").innerHTML = "";
    $("status").textContent = "";
  } finally {
    stopPolling();
    $("run").disabled = false;
  }
}

$("run").onclick = run;
$("clear").onclick = async () => {
  await fetch("/api/cache/clear", { method: "POST" });
  $("status").textContent = "cache emptied, the next run pays full price";
};

fetch("/api/presets").then((r) => r.json()).then((d) => {
  presets = d.presets;
  $("presets").innerHTML = presets.map((p, i) => `<option value="${i}">${p.name}</option>`).join("");
  $("presets").onchange = (e) => { $("sql").value = presets[e.target.value].sql; };
  $("sql").value = presets[0].sql;
  $("functions").innerHTML = d.functions.map((f) =>
    `<div class="fn"><code>${f.signature}</code><span class="hint">${f.returns}</span><span>${f.meaning}</span></div>`).join("");
  $("limit").max = d.rows_available;
});
