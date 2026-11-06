// Builds assets/languages.svg: a terminal-style card of the owner's languages.
// Exits non-zero on any API error, so a failed run keeps the last good card.
import { writeFileSync } from "node:fs";

const USER = process.env.USERNAME;
const TOKEN = process.env.LANGS_TOKEN || process.env.GITHUB_TOKEN;
const MAX_ROWS = 8;
const SEGMENTS = 25;

async function api(path) {
  const res = await fetch(`https://api.github.com${path}`, {
    headers: {
      Accept: "application/vnd.github+json",
      "User-Agent": "language-card",
      ...(TOKEN && { Authorization: `Bearer ${TOKEN}` }),
    },
  });
  if (!res.ok) throw new Error(`${path}: ${res.status} ${await res.text()}`);
  return res.json();
}

async function listRepos() {
  // LANGS_TOKEN (optional) can see private repos; GITHUB_TOKEN sees public ones.
  const base = process.env.LANGS_TOKEN
    ? "/user/repos?affiliation=owner"
    : `/users/${USER}/repos?type=owner`;
  const repos = [];
  for (let page = 1; ; page++) {
    const batch = await api(`${base}&per_page=100&page=${page}`);
    repos.push(...batch);
    if (batch.length < 100) return repos.filter((r) => !r.fork);
  }
}

const esc = (s) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

function render(rows, langCount, repoCount) {
  const rowH = 24;
  const top = 62;
  const height = top + rows.length * rowH + 46;
  let body = "";
  rows.forEach(({ name, pct }, i) => {
    const y = top + i * rowH;
    const lit = Math.max(1, Math.round((pct / 100) * SEGMENTS));
    let segs = "";
    for (let s = 0; s < SEGMENTS; s++) {
      const on = s < lit;
      segs += `<rect x="${165 + s * 10}" y="${y - 12}" width="8" height="14" class="${on ? "on" : "off"}"${on ? ` style="animation-delay:${i * 80 + s * 25}ms"` : ""}/>`;
    }
    body += `<text class="l" x="20" y="${y}">${esc(name)}</text>${segs}<text class="p" x="475" y="${y}" text-anchor="end">${pct.toFixed(1)}%</text>\n`;
  });
  const footY = top + rows.length * rowH + 16;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 495 ${height}" width="495" height="${height}" role="img" aria-label="Most used languages: ${esc(rows.map((r) => `${r.name} ${r.pct.toFixed(1)}%`).join(", "))}">
<style>
text{font-family:Consolas,"DejaVu Sans Mono","Liberation Mono","Courier New",monospace;font-size:14px;font-weight:700}
.t{fill:#00ff41;font-size:15px}.l{fill:#b6ffcb}.p{fill:#00ff41}.f{fill:#00ff41;fill-opacity:.8;font-size:13px}
.on{fill:#00ff41;animation:lit .15s linear both}.off{fill:#00ff41;fill-opacity:.12}
@keyframes lit{from{opacity:0}}
@media (prefers-reduced-motion:reduce){.on{animation:none}}
</style>
<rect x="1" y="1" width="493" height="${height - 2}" rx="6" fill="#000" stroke="#00ff41"/>
<text class="t" x="20" y="30">root@antech:~# ./scan --languages</text>
${body}<text class="f" x="20" y="${footY}">[+] scan complete: ${langCount} languages across ${repoCount} repos</text>
</svg>
`;
}

const repos = await listRepos();
const totals = {};
for (const repo of repos) {
  const langs = await api(`/repos/${repo.full_name}/languages`);
  for (const [name, bytes] of Object.entries(langs)) {
    totals[name] = (totals[name] ?? 0) + bytes;
  }
}
const sum = Object.values(totals).reduce((a, b) => a + b, 0);
if (!sum) throw new Error("no language data found");
const rows = Object.entries(totals)
  .sort((a, b) => b[1] - a[1])
  .slice(0, MAX_ROWS)
  .map(([name, bytes]) => ({ name, pct: (bytes / sum) * 100 }))
  .filter((r) => r.pct >= 0.05);
writeFileSync("assets/languages.svg", render(rows, Object.keys(totals).length, repos.length));
console.log(rows.map((r) => `${r.name} ${r.pct.toFixed(1)}%`).join("\n"));
