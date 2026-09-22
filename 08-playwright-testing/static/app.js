const $ = (id) => document.getElementById(id);
const pct = (p) => `${Math.round(p * 100)}%`;
let scenarios = {};

function stepCard(s) {
  if (s.error) {
    return `<div class="step fail"><h3><span>${s.what}</span><span class="verdict">error</span></h3>
      <p class="err">${s.error}</p></div>`;
  }
  const bars = Object.entries(s.state_spread || {})
    .sort((a, b) => b[1] - a[1])
    .map(([k, v]) => `<div class="bar"><span class="name">${k}</span>
      <span class="track"><span class="fill" style="width:${(v * 100).toFixed(1)}%"></span></span>
      <span class="num">${pct(v)}</span></div>`).join("");
  return `
    <div class="step ${s.result}">
      <h3><span>${s.what}</span><span class="verdict">${s.result}</span></h3>
      <div class="row">
        <div style="flex:1 1 340px">
          <p class="hint" style="margin-top:0">the test expected: ${s.expect}</p>
          <div class="stats" style="gap:18px;margin-bottom:12px">
            <div class="stat"><div class="k">page state</div><div class="v" style="font-size:19px">${s.state}</div></div>
            <div class="stat"><div class="k">expectation holds</div><div class="v" style="font-size:19px">${pct(s.matches)}</div></div>
            <div class="stat"><div class="k">can carry on</div><div class="v" style="font-size:19px">${pct(s.can_continue)}</div></div>
          </div>
          <div class="bars">${bars}</div>
          <p class="hint" style="margin-bottom:6px">message clarity: ${s.understandable_word} (${s.understandable_score.toFixed(2)} of 3)</p>
          <p class="hint">browser ${Math.round(s.browser_seconds * 1000)}ms &middot; judged in ${Math.round(s.judge_seconds * 1000)}ms</p>
          <details><summary class="hint">what the model was shown</summary>
            <div class="seen">${s.page_text.replace(/</g, "&lt;")}</div></details>
        </div>
        <div style="flex:0 1 330px">
          ${s.screenshot ? `<img class="shot" src="data:image/png;base64,${s.screenshot}" alt="">` : ""}
        </div>
      </div>
    </div>`;
}

async function run() {
  const bug = document.querySelector('input[name="build"]:checked').value === "bug";
  $("error").textContent = "";
  $("run").disabled = true;
  $("status").textContent = "driving the browser…";
  $("steps").innerHTML = "";
  $("banner").innerHTML = "";
  try {
    const res = await fetch("/api/run", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ scenario: $("scenario").value, bug }),
    });
    const d = await res.json();
    if (!res.ok) throw new Error(d.error || res.statusText);
    const word = { pass: "Test passed", fail: "Test failed", unsure: "Not sure" }[d.result];
    $("banner").innerHTML = `<div class="banner ${d.result}">${word}</div>`;
    $("steps").innerHTML = d.steps.map(stepCard).join("");
    $("status").textContent =
      `${d.steps.length} steps in ${d.seconds.toFixed(2)}s · judging took ${Math.round(d.judge_seconds * 1000)}ms of that · $${d.cost.toFixed(6)}`;
  } catch (err) {
    $("error").textContent = String(err.message || err);
    $("status").textContent = "";
  } finally {
    $("run").disabled = false;
  }
}

$("run").onclick = run;

fetch("/api/scenarios").then((r) => r.json()).then((d) => {
  scenarios = d.scenarios;
  const names = Object.keys(scenarios);
  $("scenario").innerHTML = names.map((n) => `<option>${n}</option>`).join("");
  const showPlan = () => {
    $("plan").textContent = "steps: " + scenarios[$("scenario").value].join(" → ");
  };
  $("scenario").onchange = showPlan;
  showPlan();
});
