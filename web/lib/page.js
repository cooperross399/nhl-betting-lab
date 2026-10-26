// Shared header, tabs and helpers for the NHL-only plain pages (Game, Record, Methods).
// The .dc.html pages are shared across three labs; these three are NHL's alone.
export const TABS = [
  ["Tonight", "Board.dc.html"], ["Props", "Board.dc.html#props"], ["Results", "Results.dc.html"],
  ["Season", "Season.dc.html"], ["Record", "Record.html"], ["Tracker", "Tracker.html"],
];

export function chrome(current) {
  const tabs = TABS.map(([label, href]) =>
    `<a href="${href}"${label === current ? ' aria-current="page" class="on"' : ""}>${label}</a>`).join("");
  return `<a href="#main" class="skip">Skip to content</a>
  <header class="mast"><a href="https://maverickhightower.com/" class="brand" aria-label="Maverick Hightower home">
    <span class="mh" aria-hidden="true">MH</span><span class="bt"><span class="k">Maverick Hightower</span><span class="n">NHL Projections</span></span></a>
    <nav aria-label="Site" class="site"><a href="Methods.html"${current === "Methods" ? ' aria-current="page"' : ""}>Methods</a><a href="https://maverickhightower.com/about.html">About</a></nav></header>
  <nav aria-label="Board sections" class="tabs">${tabs}</nav>`;
}

export const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export const pct = (p, d = 0) => (typeof p === "number" && isFinite(p) ? `${(p * 100).toFixed(d)}%` : "—");
export const mult = (x) => (typeof x === "number" && isFinite(x) ? x.toFixed(2) : "—");
export const signedPts = (d) => (typeof d === "number" && isFinite(d) ? `${d > 0 ? "+" : d < 0 ? "−" : "±"}${Math.abs(d * 100).toFixed(1)} pts` : "—");
export const american = (p) => {
  if (typeof p !== "number" || !(p > 0 && p < 1)) return "—";
  const v = p >= 0.5 ? Math.round((-100 * p) / (1 - p)) : Math.round((100 * (1 - p)) / p);
  return v > 0 ? `+${v}` : `−${Math.abs(v)}`;
};

export async function getJSON(path) {
  try {
    const r = await fetch(path, { cache: "no-store" });
    if (!r.ok) return null;
    return await r.json();
  } catch (e) {
    return null;
  }
}
