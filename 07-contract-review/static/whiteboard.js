// Renders boards.json as hand-drawn SVG boards. Arrow keys step through them.
// Board coordinates are laid out on a fixed 1280x720 canvas.

const W = 1280;
const H = 720;
const SVG = "http://www.w3.org/2000/svg";

const TONES = {
  plain: { stroke: "#1e1e1e", fill: "none" },
  accent: { stroke: "#1971c2", fill: "#e7f0f9" },
  good: { stroke: "#2f9e44", fill: "#e9f7ec" },
  bad: { stroke: "#c92a2a", fill: "#fbecec" },
  warn: { stroke: "#e8590c", fill: "#fdf1e7" },
  muted: { stroke: "#9b968c", fill: "none" },
};

let deck = { title: "", boards: [] };
let board = 0;
let step = 0;

function rng(seed) {
  let s = 0;
  for (const ch of String(seed)) s = (s * 31 + ch.charCodeAt(0)) >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

function wobble(rnd, amount) {
  return (rnd() - 0.5) * amount;
}

function line(x1, y1, x2, y2, rnd, a = 2.4) {
  const mx = (x1 + x2) / 2 + wobble(rnd, a * 1.8);
  const my = (y1 + y2) / 2 + wobble(rnd, a * 1.8);
  return `M ${x1 + wobble(rnd, a)} ${y1 + wobble(rnd, a)} Q ${mx} ${my} ${x2 + wobble(rnd, a)} ${y2 + wobble(rnd, a)}`;
}

function rectPath(x, y, w, h, rnd) {
  const r = 12;
  return [
    line(x + r, y, x + w - r, y, rnd),
    `M ${x + w - r} ${y} Q ${x + w} ${y} ${x + w} ${y + r}`,
    line(x + w, y + r, x + w, y + h - r, rnd),
    `M ${x + w} ${y + h - r} Q ${x + w} ${y + h} ${x + w - r} ${y + h}`,
    line(x + w - r, y + h, x + r, y + h, rnd),
    `M ${x + r} ${y + h} Q ${x} ${y + h} ${x} ${y + h - r}`,
    line(x, y + h - r, x, y + r, rnd),
    `M ${x} ${y + r} Q ${x} ${y} ${x + r} ${y}`,
  ].join(" ");
}

function el(name, attrs = {}, parent = null) {
  const node = document.createElementNS(SVG, name);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (parent) parent.appendChild(node);
  return node;
}

function wrap(text, maxWidth, fontSize) {
  const perChar = fontSize * 0.46;
  const limit = Math.max(6, Math.floor(maxWidth / perChar));
  const out = [];
  for (const para of String(text).split("\n")) {
    let cur = "";
    for (const word of para.split(/\s+/)) {
      if (!cur.length) cur = word;
      else if ((cur + " " + word).length <= limit) cur += " " + word;
      else { out.push(cur); cur = word; }
    }
    out.push(cur);
  }
  return out;
}

function drawText(parent, text, cx, y, fontSize, color, anchor = "middle", maxWidth = 1e6) {
  const lines = wrap(text, maxWidth, fontSize);
  const lh = fontSize * 1.3;
  const node = el("text", {
    x: cx, y: y - ((lines.length - 1) * lh) / 2,
    "text-anchor": anchor, "dominant-baseline": "middle",
    "font-size": fontSize, fill: color,
  }, parent);
  lines.forEach((ln, i) => {
    el("tspan", { x: cx, dy: i === 0 ? 0 : lh }, node).textContent = ln;
  });
  return node;
}

function group(parent, stepIndex) {
  return el("g", { class: "reveal", "data-step": stepIndex || 0 }, parent);
}

function edgePoint(node, tx, ty) {
  const cx = node.x + node.w / 2;
  const cy = node.y + node.h / 2;
  const dx = tx - cx;
  const dy = ty - cy;
  if (!dx && !dy) return [cx, cy];
  const sx = dx === 0 ? Infinity : (node.w / 2 + 8) / Math.abs(dx);
  const sy = dy === 0 ? Infinity : (node.h / 2 + 8) / Math.abs(dy);
  const s = Math.min(sx, sy);
  return [cx + dx * s, cy + dy * s];
}

function drawBoard(b) {
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "xMidYMid meet" });
  const byId = {};
  for (const n of b.nodes || []) byId[n.id] = n;

  for (const n of b.nodes || []) {
    const g = group(svg, n.step);
    const tone = TONES[n.tone || "plain"] || TONES.plain;
    const rnd = rng(n.id + b.name);
    if (n.shape === "ellipse") {
      el("ellipse", {
        cx: n.x + n.w / 2, cy: n.y + n.h / 2, rx: n.w / 2, ry: n.h / 2,
        fill: tone.fill, stroke: tone.stroke, "stroke-width": 2.2,
      }, g);
    } else if (n.shape !== "none") {
      if (tone.fill !== "none") {
        el("path", { d: rectPath(n.x, n.y, n.w, n.h, rng(n.id + "f")), fill: tone.fill, stroke: "none" }, g);
      }
      el("path", {
        d: rectPath(n.x, n.y, n.w, n.h, rnd),
        fill: "none", stroke: tone.stroke, "stroke-width": 2.2,
        "stroke-linecap": "round", "stroke-dasharray": n.dashed ? "9 7" : "none",
      }, g);
    }
    if (n.head) {
      drawText(g, n.head, n.x + n.w / 2, n.y + 28, 19, "#8a857c", "middle", n.w - 24);
    }
    const ty = n.y + n.h / 2 + (n.head ? 14 : 0);
    drawText(g, n.text, n.x + n.w / 2, ty, n.size || 25, tone.stroke, "middle", n.w - 30);
    if (n.sub) {
      drawText(g, n.sub, n.x + n.w / 2, n.y + n.h - 26, 18, "#6c6a66", "middle", n.w - 24);
    }
  }

  for (const a of b.arrows || []) {
    const from = byId[a.from];
    const to = byId[a.to];
    if (!from || !to) continue;
    const g = group(svg, a.step);
    const tone = TONES[a.tone || "plain"] || TONES.plain;
    const [x2raw, y2raw] = edgePoint(to, from.x + from.w / 2, from.y + from.h / 2);
    const [x1, y1] = edgePoint(from, to.x + to.w / 2, to.y + to.h / 2);
    const rnd = rng(a.from + a.to + b.name);
    el("path", {
      d: line(x1, y1, x2raw, y2raw, rnd, 2),
      fill: "none", stroke: tone.stroke, "stroke-width": 2.2, "stroke-linecap": "round",
      "stroke-dasharray": a.dashed ? "8 7" : "none",
    }, g);
    const ang = Math.atan2(y2raw - y1, x2raw - x1);
    const hl = 15;
    for (const spread of [0.42, -0.42]) {
      el("path", {
        d: `M ${x2raw} ${y2raw} L ${x2raw - hl * Math.cos(ang - spread)} ${y2raw - hl * Math.sin(ang - spread)}`,
        stroke: tone.stroke, "stroke-width": 2.2, "stroke-linecap": "round", fill: "none",
      }, g);
    }
    if (a.text) {
      const mx = (x1 + x2raw) / 2 + (a.dx || 0);
      const my = (y1 + y2raw) / 2 + (a.dy || -18);
      const t = drawText(g, a.text, mx, my, 19, "#6c6a66", "middle", a.width || 220);
      t.setAttribute("paint-order", "stroke");
      t.setAttribute("stroke", "#fbf8f1");
      t.setAttribute("stroke-width", "6");
    }
  }

  for (const n of b.notes || []) {
    const g = group(svg, n.step);
    drawText(g, n.text, n.x, n.y, n.size || 21, n.color || "#6c6a66", n.anchor || "start", n.width || 420);
  }

  return svg;
}

function maxStep(b) {
  let m = 0;
  const all = [...(b.nodes || []), ...(b.arrows || []), ...(b.notes || [])];
  for (const e of all) m = Math.max(m, e.step || 0);
  return m;
}

function render() {
  const b = deck.boards[board];
  const stage = document.getElementById("stage");
  stage.replaceChildren(drawBoard(b));
  requestAnimationFrame(() => {
    for (const g of stage.querySelectorAll(".reveal")) {
      if (Number(g.dataset.step) <= step) g.classList.add("shown");
    }
  });
  document.getElementById("deck-title").textContent = deck.title;
  document.getElementById("board-name").textContent = b.name || "";
  const dots = document.getElementById("dots");
  dots.replaceChildren(...deck.boards.map((_, i) => {
    const d = document.createElement("i");
    if (i === board) d.className = "on";
    return d;
  }));
  location.hash = `${board + 1}.${step}`;
}

function next() {
  if (step < maxStep(deck.boards[board])) step += 1;
  else if (board < deck.boards.length - 1) { board += 1; step = 0; }
  render();
}

function prev() {
  if (step > 0) step -= 1;
  else if (board > 0) { board -= 1; step = maxStep(deck.boards[board]); }
  render();
}

function fromHash() {
  const m = /^#(\d+)(?:\.(\d+))?/.exec(location.hash);
  if (!m) return;
  board = Math.min(Math.max(Number(m[1]) - 1, 0), deck.boards.length - 1);
  step = Math.max(Number(m[2] || 0), 0);
}

document.addEventListener("keydown", (e) => {
  if (e.key === "ArrowRight" || e.key === " ") { e.preventDefault(); next(); }
  else if (e.key === "ArrowLeft") { e.preventDefault(); prev(); }
  else if (e.key === "ArrowDown") { if (board < deck.boards.length - 1) { board += 1; step = 0; render(); } }
  else if (e.key === "ArrowUp") { if (board > 0) { board -= 1; step = 0; render(); } }
  else if (e.key === "r") { step = 0; render(); }
  else if (e.key === "a") { step = maxStep(deck.boards[board]); render(); }
  else if (e.key === "f") { document.documentElement.requestFullscreen?.(); }
});

document.addEventListener("click", next);

// cache-busted so edits to boards.json show up on reload
fetch("boards.json?v=" + Date.now())
  .then((r) => r.json())
  .then((data) => {
    deck = data;
    fromHash();
    render();
  })
  .catch((err) => {
    document.getElementById("stage").textContent = "Could not load boards.json: " + err;
  });
