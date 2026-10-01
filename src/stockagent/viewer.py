"""Builds a static page for clicking through what the agent did.

A score is a claim. A trace is the evidence. This turns traces into something a
reader can browse: every question, whether it passed, and the exact sequence of
tool calls and results behind the answer.

**Why redaction exists.** Tool results contain raw closing prices, and Twelve
Data licenses those for internal use and not for redistribution. Publishing the
traces unredacted on GitHub Pages would be exactly the redistribution the licence
forbids. So `redact=True` masks the raw figures inside tool results while leaving
everything else intact: the tool names, the arguments, the agent's reasoning,
whether it checked for a split, how many attempts it needed, what it cited.

That turns out to be most of what a reader wants. "Did it look up the corporate
actions before comparing two dates" is answerable from a redacted trace. The
exact price is not the interesting part, and the person who wants it can rebuild
the database with their own free key and run the viewer locally with redaction off.
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

# A bare number with two or more decimals, or any four-plus digit run: the shapes
# a raw price or volume takes. Percentages are left alone, because a return is
# derived data and publishing it is permitted.
_RAW_FIGURE = re.compile(r"(?<![%\d.])\b\d[\d,]*\.\d{2,}\b|\b\d{4,}\b")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def redact_figures(text: str) -> str:
    """Mask raw figures, keeping dates and structure readable."""
    if not text:
        return text
    # Dates are protected first so the four-digit year is not masked.
    placeholders: list[str] = []

    def keep(match: re.Match) -> str:
        placeholders.append(match.group(0))
        return f"\x00{len(placeholders) - 1}\x00"

    protected = _ISO_DATE.sub(keep, text)
    masked = _RAW_FIGURE.sub("[figure]", protected)
    for index, original in enumerate(placeholders):
        masked = masked.replace(f"\x00{index}\x00", original)
    return masked


@dataclass(frozen=True)
class ViewerData:
    title: str
    runs: list[dict]

    def to_json(self) -> str:
        return json.dumps(self.runs, indent=None, separators=(",", ":"))


def _redact_strings(value):
    """Mask figures in every string inside a nested structure."""
    if isinstance(value, str):
        return redact_figures(value)
    if isinstance(value, dict):
        return {key: _redact_strings(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [_redact_strings(inner) for inner in value]
    return value


def _redact_step(step: dict) -> dict:
    out = dict(step)
    # Tool results and model replies carry figures the model read back. So do a
    # tool call's arguments: final_answer's "text" is the answer itself, which was
    # a real leak the published-page test caught. Numeric fields such as
    # latency_ms and token counts are left alone -- they are ours, not the
    # provider's.
    for field in ("result", "reply", "text", "thought"):
        if field in out:
            out[field] = redact_figures(str(out[field]))
    if "arguments" in out:
        out["arguments"] = _redact_strings(out["arguments"])
    if "sources" in out:
        out["sources"] = _redact_strings(out["sources"])
    return out


def build_data(
    results_files: Sequence[Path],
    *,
    redact: bool = True,
    max_questions: int | None = None,
) -> ViewerData:
    """Read results and their traces into something the page can render."""
    runs = []
    for results_path in results_files:
        payload = json.loads(Path(results_path).read_text())
        traces = _load_traces(Path(results_path))

        questions = payload.get("questions", [])
        if max_questions is not None:
            questions = questions[:max_questions]

        rows = []
        for question in questions:
            trace = traces.get(question["question_id"], {})
            steps = trace.get("steps", [])
            if redact:
                steps = [_redact_step(step) for step in steps]
            rows.append(
                {
                    "id": question["question_id"],
                    "kind": question.get("kind", ""),
                    "market": question.get("market", ""),
                    "language": question.get("language", "en"),
                    "text": question.get("text", ""),
                    "passed": bool(question.get("passed")),
                    "stop": question.get("stop", ""),
                    "answer": redact_figures(question.get("answer", ""))
                    if redact
                    else question.get("answer", ""),
                    "expected": redact_figures(question.get("expected", ""))
                    if redact
                    else question.get("expected", ""),
                    # A grader's failure detail quotes the expected figure
                    # ("expected 1068.7000 USD, closest was..."), so it leaks a
                    # raw price just as surely as a tool result does.
                    "failures": [
                        {
                            "grader": failure.get("grader", ""),
                            "detail": redact_figures(str(failure.get("detail", "")))
                            if redact
                            else failure.get("detail", ""),
                        }
                        for failure in question.get("failures", [])
                    ],
                    "tokens": question.get("total_tokens", 0),
                    "latency_ms": question.get("latency_ms", 0),
                    "tools": question.get("tools_used", []),
                    "steps": steps,
                }
            )

        runs.append(
            {
                "run": payload.get("run", results_path.stem),
                "system": payload.get("system", ""),
                "eval_version": payload.get("eval_version", ""),
                "split": payload.get("split", ""),
                "accuracy": payload.get("accuracy", {}),
                "total": payload.get("total", len(rows)),
                "stops": payload.get("stops", {}),
                "questions": rows,
            }
        )

    return ViewerData(title="Agent traces", runs=runs)


def _load_traces(results_path: Path) -> dict[str, dict]:
    """The traces file sitting beside a results file."""
    name = results_path.name.replace("-results.json", "-traces.jsonl")
    candidate = results_path.with_name(name)
    if not candidate.exists():
        return {}
    traces = {}
    for line in candidate.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        traces[row.get("question_id", "")] = row
    return traces


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
 :root { --ink:#1a1a1a; --soft:#5a5a5a; --line:#e2e2e2; --bg:#fff;
         --pass:#1a7f37; --fail:#b42318; --panel:#f7f7f6; }
 @media (prefers-color-scheme: dark) {
   :root { --ink:#e8e8e8; --soft:#a0a0a0; --line:#333; --bg:#161616;
           --pass:#4ac26b; --fail:#ff7b72; --panel:#1f1f1f; }
 }
 * { box-sizing: border-box; }
 body { margin:0; background:var(--bg); color:var(--ink); font:15px/1.55
        ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; }
 .wrap { max-width:1100px; margin:0 auto; padding:24px 16px 64px; }
 h1 { font-size:22px; margin:0 0 4px; }
 .note { color:var(--soft); font-size:13px; margin:0 0 20px; }
 .runs { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:16px; }
 button { font:inherit; cursor:pointer; border:1px solid var(--line);
          background:var(--bg); color:var(--ink); border-radius:6px;
          padding:5px 11px; }
 button[aria-pressed="true"] { background:var(--ink); color:var(--bg);
                               border-color:var(--ink); }
 .head { border:1px solid var(--line); border-radius:8px; padding:12px 14px;
         margin-bottom:16px; background:var(--panel); font-size:14px; }
 .filters { display:flex; gap:8px; flex-wrap:wrap; align-items:center;
            margin-bottom:14px; font-size:13px; }
 input[type=search] { font:inherit; padding:5px 9px; border:1px solid var(--line);
                      border-radius:6px; background:var(--bg); color:var(--ink);
                      min-width:200px; }
 .q { border:1px solid var(--line); border-radius:8px; margin-bottom:8px;
      overflow:hidden; }
 .q > summary { cursor:pointer; padding:10px 14px; display:grid;
                grid-template-columns:52px 1fr auto; gap:10px; align-items:start; }
 .q > summary::-webkit-details-marker { display:none; }
 .tag { font-size:11px; font-weight:700; letter-spacing:.04em; padding-top:3px; }
 .pass { color:var(--pass); } .fail { color:var(--fail); }
 .meta { color:var(--soft); font-size:12px; white-space:nowrap; }
 .kind { color:var(--soft); font-size:12px; }
 .body { padding:0 14px 14px; border-top:1px solid var(--line); }
 .row { margin:12px 0; }
 .label { font-size:11px; text-transform:uppercase; letter-spacing:.06em;
          color:var(--soft); margin-bottom:3px; }
 pre { white-space:pre-wrap; word-break:break-word; background:var(--panel);
       border:1px solid var(--line); border-radius:6px; padding:9px 11px;
       margin:0; font:12.5px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace; }
 .step { border-left:3px solid var(--line); padding:2px 0 2px 11px; margin:9px 0; }
 .step.tool { border-left-color:#3b82f6; }
 .step.model { border-left-color:#a855f7; }
 .step.error { border-left-color:var(--fail); }
 .step.answer { border-left-color:var(--pass); }
 .step h4 { margin:0 0 4px; font-size:12.5px; }
 .empty { color:var(--soft); padding:28px 0; }
</style>
</head>
<body>
<div class="wrap">
  <h1>__TITLE__</h1>
  <p class="note">__NOTE__</p>
  <div class="runs" id="runs"></div>
  <div class="head" id="head"></div>
  <div class="filters">
    <button id="all" aria-pressed="true">all</button>
    <button id="failed" aria-pressed="false">failures only</button>
    <input type="search" id="search" placeholder="filter by text, kind or id">
    <span class="meta" id="count"></span>
  </div>
  <div id="list"></div>
</div>
<script>
const RUNS = __DATA__;
let current = 0, failedOnly = false, needle = "";

const esc = s => String(s ?? "").replace(/[&<>"]/g, c =>
  ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const pct = v => (v == null ? "n/a" : (v * 100).toFixed(1) + "%");

function drawRuns() {
  document.getElementById("runs").innerHTML = RUNS.map((r, i) =>
    `<button data-i="${i}" aria-pressed="${i === current}">${esc(r.system || r.run)}</button>`
  ).join("");
  document.querySelectorAll("#runs button").forEach(b =>
    b.onclick = () => { current = +b.dataset.i; draw(); });
}

function drawHead() {
  const r = RUNS[current];
  if (!r) { document.getElementById("head").textContent = "No runs yet."; return; }
  const a = r.accuracy || {};
  document.getElementById("head").innerHTML =
    `<strong>${esc(r.system)}</strong> on ${esc(r.eval_version)} (${esc(r.split)}) &mdash; ` +
    `${pct(a.point)} <span class="meta">(${pct(a.low)}&ndash;${pct(a.high)})</span> ` +
    `over ${r.total} questions. Ended: ${esc(JSON.stringify(r.stops || {}))}`;
}

function steps(list) {
  if (!list || !list.length) return '<p class="meta">No steps recorded.</p>';
  return list.map(s => {
    const bits = [];
    if (s.kind === "tool") {
      bits.push(`<pre>${esc(JSON.stringify(s.arguments || {}))}</pre>`);
      if (s.thought) bits.push(`<p class="meta">thought: ${esc(s.thought)}</p>`);
      bits.push(`<pre>${esc(s.result || "")}</pre>`);
    } else if (s.kind === "model") {
      bits.push(`<pre>${esc(s.reply || "")}</pre>`);
    } else {
      bits.push(`<pre>${esc(JSON.stringify(
        Object.fromEntries(Object.entries(s).filter(([k]) =>
          !["index","kind","prompt_tokens","completion_tokens","total_tokens",
            "latency_ms","cached"].includes(k))), null, 1))}</pre>`);
    }
    const head = s.kind === "tool"
      ? `${esc(s.tool)} ${s.ok === false ? '<span class="fail">failed</span>' : ""}`
      : esc(s.kind);
    const cost = s.total_tokens
      ? `<span class="meta"> ${s.total_tokens} tokens, ${Math.round(s.latency_ms)}ms` +
        `${s.cached ? ", cached" : ""}</span>` : "";
    return `<div class="step ${esc(s.kind)}"><h4>${s.index}. ${head}${cost}</h4>` +
           bits.join("") + `</div>`;
  }).join("");
}

function draw() {
  drawRuns(); drawHead();
  const r = RUNS[current];
  let rows = r ? r.questions : [];
  if (failedOnly) rows = rows.filter(q => !q.passed);
  if (needle) {
    const n = needle.toLowerCase();
    rows = rows.filter(q => (q.text + q.kind + q.id).toLowerCase().includes(n));
  }
  document.getElementById("count").textContent =
    `${rows.length} shown` + (r ? ` of ${r.questions.length}` : "");
  document.getElementById("list").innerHTML = rows.length ? rows.map(q => `
    <details class="q">
      <summary>
        <span class="tag ${q.passed ? "pass" : "fail"}">${q.passed ? "PASS" : "FAIL"}</span>
        <span>${esc(q.text)}<br><span class="kind">${esc(q.kind)}`
        + ` &middot; ${esc(q.market)}`
        + `${q.language !== "en" ? " &middot; " + esc(q.language) : ""}`
        + ` &middot; ${esc(q.id)}</span></span>
        <span class="meta">${q.tokens} tok<br>${Math.round(q.latency_ms)}ms</span>
      </summary>
      <div class="body">
        <div class="row"><div class="label">Answer given</div>
          <pre>${esc(q.answer) || "(none)"}</pre></div>
        <div class="row"><div class="label">Reference</div>
          <pre>${esc(q.expected) || "(hand-checked)"}</pre></div>
        ${q.failures && q.failures.length
          ? `<div class="row"><div class="label">Why it failed</div>`
            + `<pre>${esc(q.failures.map(f => f.grader + ": " + f.detail).join("\\n"))}</pre></div>`
          : ""}
        <div class="row"><div class="label">Steps (${q.steps.length})</div>${steps(q.steps)}</div>
      </div>
    </details>`).join("") : '<p class="empty">Nothing matches that filter.</p>';
}

document.getElementById("all").onclick = () => {
  failedOnly = false;
  document.getElementById("all").setAttribute("aria-pressed", "true");
  document.getElementById("failed").setAttribute("aria-pressed", "false");
  draw();
};
document.getElementById("failed").onclick = () => {
  failedOnly = true;
  document.getElementById("all").setAttribute("aria-pressed", "false");
  document.getElementById("failed").setAttribute("aria-pressed", "true");
  draw();
};
document.getElementById("search").oninput = e => { needle = e.target.value; draw(); };
draw();
</script>
</body>
</html>
"""

REDACTED_NOTE = (
    "Raw prices are masked as [figure]. The data behind them is licensed for "
    "internal use and may not be republished, so what is shown here is the shape "
    "of each run: the tools called, their arguments, the reasoning, and what was "
    "cited. Run the viewer locally with --no-redact against your own database to "
    "see the figures."
)

FULL_NOTE = (
    "Built locally with redaction off. Do not publish this page: it contains raw "
    "licensed market data."
)


def render(data: ViewerData, *, redact: bool = True) -> str:
    page = PAGE.replace("__TITLE__", html.escape(data.title))
    page = page.replace("__NOTE__", html.escape(REDACTED_NOTE if redact else FULL_NOTE))
    return page.replace("__DATA__", data.to_json())


def build(
    results_files: Iterable[Path],
    output: Path,
    *,
    redact: bool = True,
    max_questions: int | None = None,
) -> Path:
    data = build_data(list(results_files), redact=redact, max_questions=max_questions)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(data, redact=redact))
    return output
