from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import tempfile
import textwrap
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "Trading-Desk-v3-Visual-Guide.pdf"
CHROME = os.environ.get("CHROME_PATH", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

STYLE = """
@page { size: A3 landscape; margin: 0; }
* { box-sizing: border-box; }
body { margin: 0; color: #182b42; font-family: Arial, sans-serif; background: #fff; }
.sheet { width: 420mm; height: 297mm; padding: 17mm 21mm 12mm; display: flex;
  flex-direction: column; break-after: page; overflow: hidden; }
.sheet:last-child { break-after: auto; }
.eyebrow { color: #197e87; font-size: 12pt; font-weight: 700; letter-spacing: 2px; }
h1 { margin: 10px 0 12px; font-size: 31pt; font-weight: 700; letter-spacing: -1px; }
.subtitle { font-size: 15pt; line-height: 1.45; color: #526478; margin-bottom: 12px; }
.content { flex: 1; min-height: 0; display: flex; align-items: center; justify-content: center; }
.diagram { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; }
.diagram svg { width: 100% !important; height: 100% !important; max-width: none !important; }
.note { margin-top: 13px; padding: 13px 17px; border-left: 4px solid #dfaa43;
  background: #fff8e8; font-size: 12pt; line-height: 1.5; }
.footer { border-top: 1px solid #d6e1ec; margin-top: 13px; padding-top: 11px;
  font-size: 10pt; color: #62748a; display: flex; justify-content: space-between; }
.cover { background: linear-gradient(125deg, #f3f8fc, #ffffff 70%); }
.cover h1 { font-size: 44pt; line-height: 1.13; margin-top: 20px; }
.cover .subtitle { font-size: 17pt; max-width: 950px; }
.cover .content { align-items: stretch; flex-direction: column; justify-content: center; gap: 20px; }
.toc { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 35px; font-size: 13pt; }
.toc div { border-bottom: 1px solid #d6e1ec; padding: 8px 0; }
.toc b { display: inline-block; width: 40px; color: #197e87; }
.banner { background: #182f49; color: #fff; padding: 24px 28px; border-radius: 9px;
 font-size: 17pt; line-height: 1.5; }
table { border-collapse: collapse; width: 100%; table-layout: fixed; font-size: 13pt; line-height: 1.45; }
th { background: #182f49; color: white; text-align: left; padding: 16px; }
td { padding: 17px 16px; vertical-align: top; border-bottom: 1px solid #d6e1ec; }
tr:nth-child(even) td { background: #f1f7fb; }
th:first-child { width: 18%; }
th:nth-child(2) { width: 35%; }
"""

NODE_RENDER = r"""
const fs = require('node:fs');
const path = require('node:path');
const runtime = process.argv[2];
const puppeteer = require(path.join(runtime, 'node_modules/puppeteer-core'));
(async () => {
  const input = JSON.parse(fs.readFileSync(path.join(runtime, 'input.json'), 'utf8'));
  const browser = await puppeteer.launch({executablePath: input.chrome, headless: true});
  try {
    const page = await browser.newPage();
    await page.setViewport({width: 1588, height: 1123, deviceScaleFactor: 1});
    await page.setRequestInterception(true);
    page.on('request', request => {
      if (/^https?:/.test(request.url())) request.abort();
      else request.continue();
    });
    await page.setContent(input.html, {waitUntil: 'load'});
    await page.addScriptTag({path: path.join(runtime, 'node_modules/mermaid/dist/mermaid.min.js')});
    const sizes = await page.evaluate(async (diagrams) => {
      mermaid.initialize({startOnLoad: false, securityLevel: 'strict', theme: 'base',
        themeVariables: {fontFamily: 'Arial, sans-serif', fontSize: '24px',
          primaryColor: '#eaf3fa', primaryTextColor: '#182b42', primaryBorderColor: '#5a819e',
          lineColor: '#55748c', secondaryColor: '#e4f2ee', tertiaryColor: '#fff2d6',
          edgeLabelBackground: '#ffffff'},
        flowchart: {htmlLabels: false, useMaxWidth: false, curve: 'basis', nodeSpacing: 26, rankSpacing: 35}});
      const stats = [];
      for (let i = 0; i < diagrams.length; i++) {
        const target = document.getElementById('chart-' + i);
        const result = await mermaid.render('mermaid-' + i, diagrams[i]);
        target.innerHTML = result.svg;
        const svg = target.querySelector('svg');
        svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
        const view = svg.viewBox.baseVal;
        const rect = target.getBoundingClientRect();
        const scale = Math.min(rect.width / view.width, rect.height / view.height);
        stats.push({diagram: i + 1, width: view.width, height: view.height, effectiveFontPx: 24 * scale});
      }
      await document.fonts.ready;
      const overflow = [];
      for (const sheet of document.querySelectorAll('.sheet')) {
        if (sheet.scrollHeight > sheet.clientHeight + 2) overflow.push('Page content overflow: ' + sheet.querySelector('h1').textContent);
        const body = sheet.querySelector('.body');
        if (body && body.scrollHeight > body.clientHeight + 2) {
          overflow.push('Body overlaps footer: ' + sheet.querySelector('h1').textContent +
            ' (' + body.scrollHeight + 'px content / ' + body.clientHeight + 'px available)');
        }
      }
      if (overflow.length) throw new Error(overflow.join('; '));
      return stats;
    }, input.diagrams);
    await page.pdf({path: input.output, preferCSSPageSize: true, printBackground: true,
                    tagged: true, outline: true});
    fs.writeFileSync(path.join(runtime, 'render-stats.json'), JSON.stringify(sizes, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
"""


def wrap_diagram(source: str) -> str:
    def quoted(match):
        return '"' + '<br/>'.join(textwrap.wrap(match.group(1), width=29, break_long_words=False, break_on_hyphens=False)) + '"'

    return re.sub(r'"([^"\n]+)"', quoted, source)


def sheet(title: str, subtitle: str, content: str, note: str, source: str, page: int, cover=False) -> str:
    return (
        f'<section class="sheet{" cover" if cover else ""}"><div class="eyebrow">TRADING DESK / V3</div>'
        f'<h1>{html.escape(title)}</h1><div class="subtitle">{html.escape(subtitle)}</div>'
        f'<div class="content">{content}</div><div class="note">{html.escape(note)}</div>'
        f'<div class="footer"><span>{html.escape(source)}</span><span>Visual guide / {page:02d}</span></div></section>'
    )


def build_document() -> tuple[str, list[str], list[str]]:
    visual = (ROOT / "architecture-visual.md").read_text()
    originals = dict(re.findall(r"^## \d+\. ([^\n]+)\n.*?```mermaid\n(.*?)```", visual, re.MULTILINE | re.DOTALL))
    expected = {"Domains and cross-cutting controls", "Target authority and economic-effect boundary",
                "Implemented portfolio and simulator paths", "Evidence-gated phases", "State ownership", "Test pyramid"}
    if set(originals) != expected:
        raise ValueError("Architecture diagram sections changed; review the named export mappings")
    for name in ("langgraph-integration.md", "requirements-and-contracts.md", "roadmap.md"):
        if not (ROOT / name).is_file():
            raise FileNotFoundError(name)
    authority_lines = originals["Target authority and economic-effect boundary"].strip().splitlines()
    authority_first = '\n'.join(authority_lines[:5])
    authority_second = 'flowchart LR\n  H["Human approval bound to intent hash"]\n' + '\n'.join(authority_lines[5:])
    phase_lines = originals["Evidence-gated phases"].strip().splitlines()
    phases_first = 'flowchart LR\n' + '\n'.join(phase_lines[1:4])
    phases_second = 'flowchart TB\n  P3["Phase 3 evidence gate"]\n  P1["Return to Phase 1 research validation"]\n' + '\n'.join(phase_lines[4:])
    graph = '''flowchart TB
  START([START]) --> S["snapshot"] --> P["pick_next"]
  P -->|Cards remain| R["retrieve"] --> D["debate_pm"] --> G["risk_gate"]
  P -->|No cards| END([END])
  G -->|Rejected| L["log_episode"]
  G -->|Allowed| H["human_approve: checkpoint and interrupt"]
  H -->|Reject| L
  H -->|Approve or configured auto| F["paper_fill: expiry and risk recheck"]
  F --> L
  L --> P
'''
    orders = '''flowchart LR
  P["PROPOSED"] --> R["REJECTED"]
  P --> A["AUTHORIZED"]
  A --> E["EXPIRED / REVOKED"]
  A --> V["RESERVED"] --> D["DISPATCH_PENDING"] --> ACK["ACKNOWLEDGED"]
  D --> U["UNKNOWN"]
  U --> EXIST["Reconciled existing order"]
  U --> NO["Proven not accepted"]
  ACK --> PART["PARTIALLY_FILLED"] --> F["FILLED"]
  ACK --> CANCEL["CANCEL_PENDING"] --> C["CANCELED"]
  PART --> CANCEL
  ACK --> REJ["REJECTED_BY_VENUE"]
'''
    agents = '''flowchart TB
  S["Current model card and score"] --> B["Bull Analyst: positive evidence"]
  S --> C["Bear Analyst: adverse evidence"]
  S --> AL["Shared allocator and PortfolioTarget"]
  B --> PM["Portfolio Manager: numeric rules and structured proposal"]
  C --> PM
  AL --> PM
  M["Decision-time eligible lessons"] --> B
  M --> C
  PM --> R["Auditor and deterministic risk"]
  R --> H["Orchestration approval and internal paper path"]
  S --> MS["Model Signal: card summary"]
  MS --> REC["Decision record"]
  PM --> REC
'''
    artifacts = '''flowchart LR
  D["Dated data and membership"] --> S["Content-addressed snapshots"]
  S --> T["Training with mature labels"]
  T --> F["Frozen estimator and transforms"]
  F --> A["Explicit local model review"]
  A --> I["Approved current inference: no silent fallback"]
  I --> E["Versioned research evidence and read-only HTML"]
'''
    specs = [
        ("Domains and shared controls", "TARGET ARCHITECTURE / Six domains, one modular deployment", originals["Domains and cross-cutting controls"],
         "Control and evidence apply across every domain. LLM access is an optional adapter, not an authority layer. One Python package and one writer are the laptop baseline.", "architecture-visual.md / Domains and cross-cutting controls"),
        ("From evidence to approval", "TARGET AUTHORITY FLOW / Part 1 of 2", authority_first,
         "Agents produce typed proposals, never broker orders. Approval is bound to an immutable intent; deterministic risk owns hard limits and projected reservations.", "architecture-visual.md / Target authority and economic-effect boundary"),
        ("From approval to economic effect", "TARGET AUTHORITY FLOW / Part 2 of 2", authority_second,
         "Recheck expiry, current risk and HALT before dispatch. An ambiguous broker outcome becomes UNKNOWN and requires reconciliation, not a blind retry. These broker capabilities are not implemented in the starter.", "architecture-visual.md / Target authority and economic-effect boundary"),
        ("Implemented portfolio and simulator", "IMPLEMENTED FOUNDATIONS / Shared decisions, separate execution paths", originals["Implemented portfolio and simulator paths"],
         "PortfolioTarget preserves explicit cash and lineage. The durable paper CLI supports partial buys/sells, fees, marked sessions, reservations and transactional events. Legacy cycle/graph fills remain separate immediate-close demonstrations; neither is broker certification.", "README.md / Portfolio-first implementation; architecture-visual.md"),
        ("Four deterministic agent roles", "IMPLEMENTED DECISION SUPPORT / Not four autonomous LLM agents", agents,
         "Bull/Bear briefs do not control numeric decisions. Shared allocation supplies desired deltas; risk and trust can reduce them. Model Signal summarizes a card. Optional LLM refinement changes thesis/invalidation prose only and is disabled by default.", "README.md / Agents; trading-agents-architecture.md / Decision and execution flow"),
        ("Frozen models and research evidence", "IMPLEMENTED FOUNDATIONS / Provenance before admission", artifacts,
         "Explicit rules and approved-model inference are distinct modes. Reports include benchmark costs, exposure/cash, matched-exposure baselines, fold dispersion and doubled-cost sensitivity. FinRL-X informed interfaces only: no dependency or copied execution code. Full PIT and promotion evidence remain gates.", "README.md / Portfolio-first implementation; roadmap.md"),
        ("Phases 0–3: establish evidence", "PROJECT ROADMAP / Foundations, research, paper lifecycle and measured memory", phases_first,
         "Phase 2 requires at least 20 prospective equity sessions after accounting and replay gates pass. A no-candidate research result permits simulator engineering, not live admission. Continue to Phase 4 only after the dependent evidence gates pass.", "architecture-visual.md / Evidence-gated phases; roadmap.md"),
        ("Phases 4–5: certify and operate", "PROJECT ROADMAP / Broker paper, optional canary and governed operations", phases_second,
         "Observation windows are operating-policy floors, not proof of alpha or completion estimates. Phase 5 requires 30 calendar days of operational evidence and restore/rollback drills. P0 on the live branch means priority-zero blockers, not Phase 0.", "architecture-visual.md / Evidence-gated phases; roadmap.md"),
        ("State ownership and memory", "TARGET DATA RESPONSIBILITIES / Checkpoints are not portfolio truth", originals["State ownership"],
         "A restored checkpoint does not authorize a new economic effect. Preserve entry situations; retrieve only outcomes available before the decision. Indexes are rebuildable; the economic ledger is not a disposable cache.", "architecture-visual.md / State ownership"),
        ("Verification and acceptance", "TARGET TEST PYRAMID / Evidence before external execution", originals["Test pyramid"],
         "Offline suites cover portfolio targets, frozen artifacts, marked ledger/reservations, decision parity, paper CLI, escaped reports and disabled shadow sentiment. They do not certify broker races, authentic PIT inputs, authorization, alpha or operational readiness.", "architecture-visual.md / Test pyramid; testing-and-acceptance.md"),
        ("LangGraph workflow", "IMPLEMENTED LEGACY PATH / Shared decisions, toy fills", graph,
         "Graph and cycle share allocation, target construction and decision-time lesson filtering. Graph approval defaults to a 300-second snapshot expiry and rechecks risk/HALT. Its paper_fill is still a legacy toy fill, not the separate durable paper engine or a broker adapter.", "langgraph-integration.md / Shipped topology"),
        ("Order lifecycle and uncertainty", "TARGET EXECUTION CONTRACT / Not a shipped broker adapter", orders,
         "UNKNOWN is not rejected. Resolve acceptance through broker history and stable order IDs. A fill can race cancellation; reconcile filled quantity before releasing remaining reservations. A checkpoint is not an exactly-once transaction.", "requirements-and-contracts.md / Target order state machine"),
    ]
    toc = '<div class="toc">' + ''.join(
        f'<div><b>{i + 2:02d}</b>{html.escape(item[0])}</div>' for i, item in enumerate(specs)
    ) + f'<div><b>{len(specs) + 2:02d}</b>Phase outputs and admission gates</div></div>'
    cover = '<div class="banner">Research first. Deterministic risk. Human authority.<br>Paper-only remains a valid outcome through Phase 5.</div>' + toc
    pages = [sheet("Architecture & delivery\nvisual guide", "Trading Desk v3 / Architecture, workflows, state ownership and phase gates", cover,
                   "Readiness: research and internal-paper prototype. Target diagrams describe the intended design, not implemented guarantees. No live broker adapter is provided.",
                   "Sources: architecture-visual.md, langgraph-integration.md, requirements-and-contracts.md, roadmap.md", 1, cover=True)]
    titles = ["Architecture & delivery"]
    diagrams = []
    for index, (title, subtitle, diagram, note, source) in enumerate(specs):
        diagrams.append(wrap_diagram(diagram))
        pages.append(sheet(title, subtitle, f'<div class="diagram" id="chart-{index}"></div>', note, source, index + 2))
        titles.append(title)
    roadmap = (ROOT / "roadmap.md").read_text()
    rows = []
    for line in roadmap.splitlines():
        if re.match(r"\| [0-5] ", line):
            cells = [cell.strip() for cell in line.strip('|').split('|')]
            rows.append('<tr>' + ''.join(f'<td>{html.escape(cells[i])}</td>' for i in (0, 2, 3)) + '</tr>')
    if len(rows) != 6:
        raise ValueError("Expected six phase rows")
    table = '<table><thead><tr><th>Phase</th><th>Ordered work packages</th><th>Output / admission gate</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table>'
    pages.append(sheet("Phase outputs and admission gates", "DELIVERY CONTRACT / Read each phase as an evidence gate, not a deadline", table,
                       "Engineering completion and model admission are different. A no-candidate result allows simulator development, not live trading. Any unresolved priority-zero blocker prevents the dependent external-execution capability.",
                       "roadmap.md / Phase contracts", len(specs) + 2))
    titles.append("Phase outputs and admission gates")
    document = '<!doctype html><html><head><meta charset="utf-8"><title>Trading Desk v3 - Visual Guide</title><style>' + STYLE + '</style></head><body>' + ''.join(pages) + '</body></html>'
    return document, diagrams, titles


def build_overview() -> tuple[str, list[str], list[str]]:
    style = """
    @page { size: A4 portrait; margin: 0; }
    * { box-sizing: border-box; }
    body { margin: 0; color: #182b42; font: 10.5pt/1.5 Arial, sans-serif; }
    .sheet { width: 210mm; height: 297mm; padding: 15mm 17mm 12mm;
      display: flex; flex-direction: column; break-after: page; }
    .sheet:last-child { break-after: auto; }
    .eyebrow { color: #197e87; font-size: 9pt; font-weight: 700; letter-spacing: 1.5px; }
    h1 { font-size: 27pt; line-height: 1.13; margin: 12px 0 9px; letter-spacing: -.6px; }
    .subtitle { color: #617387; font-size: 12pt; margin-bottom: 19px; }
    .body { flex: 1; min-height: 0; }
    h2 { font-size: 13pt; margin: 12px 0 7px; }
    p { margin: 0 0 8px; }
    .lead { background: #182f49; color: white; padding: 18px 21px; border-radius: 7px;
      font-size: 13pt; line-height: 1.48; margin-bottom: 19px; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .card { background: #f0f6fa; border: 1px solid #d9e5ee; border-radius: 5px; padding: 10px 14px; }
    .card b { display: block; font-size: 11pt; margin-bottom: 5px; }
    .card p { margin: 0; font-size: 10pt; }
    .domain { display: flex; gap: 11px; }
    .number { color: #197e87; font-weight: 700; font-size: 13pt; min-width: 26px; }
    .plane { padding: 9px 14px; background: #eaf3f0; margin-top: 10px; border-radius: 5px; }
    .plane b { color: #19675e; }
    ul { padding-left: 18px; margin: 7px 0 12px; }
    li { margin-bottom: 7px; }
    .flow { display: flex; align-items: center; gap: 6px; margin: 10px 0 8px; }
    .flow span { flex: 1; text-align: center; background: #eaf3fa; padding: 10px 5px;
      border-bottom: 3px solid #7197ae; font-size: 9pt; font-weight: 700; }
    .flow i { font-style: normal; color: #197e87; }
    .small { font-size: 9.5pt; color: #526478; }
    .note { background: #fff7e7; border-left: 3px solid #dfaa43; padding: 10px 13px;
      font-size: 9.3pt; line-height: 1.45; margin-top: 13px; }
    .footer { border-top: 1px solid #d6e1ec; padding-top: 9px; margin-top: 14px;
      display: flex; justify-content: space-between; color: #62748a; font-size: 8pt; }
    .phase { display: grid; grid-template-columns: 28px 155px 1fr; gap: 10px;
      align-items: start; border-bottom: 1px solid #d9e5ee; padding: 10px 0; }
    .phase strong { color: #197e87; font-size: 12pt; }
    .phase b { font-size: 10pt; }
    .phase span { font-size: 9.5pt; }
    .status { margin-top: 17px; }
    .status ul { font-size: 9.5pt; margin-bottom: 0; }
    .status li { margin-bottom: 5px; }
    """
    first = """
    <div class="lead">Build a small, auditable research desk that tests whether models,
    memory and carefully bounded AI assistance improve trading decisions after costs.</div>
    <h2>The idea</h2>
    <p>Start by collecting market data, training and comparing algorithms, and testing them
    honestly on later, unseen periods. Then use a small decision-support team to explain
    model signals, challenge proposals and recall relevant past outcomes. A deterministic
    risk gate—not an AI prompt—controls what may proceed.</p>
    <h2>Why build it?</h2>
    <ul>
      <li><b>Separate evidence from a good story.</b> Compare strategies with simple baselines,
      transaction costs and realistic timing before trusting them.</li>
      <li><b>Keep continuity.</b> Connect a decision to its evidence, outcome and lesson so
      later decisions can use history without seeing the future.</li>
      <li><b>Make decisions inspectable.</b> Preserve the reasoning, limits and approvals
      needed to understand why an action was allowed or rejected.</li>
    </ul>
    <h2>The intended loop</h2>
    <div class="flow"><span>Market data</span><i>→</i><span>Models</span><i>→</i>
    <span>Proposal</span><i>→</i><span>Risk + human</span><i>→</i><span>Paper test</span><i>→</i><span>Review</span></div>
    <p class="small">Reviewed outcomes feed future research and eligible memory. Improvements
    are evaluated against a fixed baseline; they are not automatically adopted.</p>
    <h2>What “learning” means here</h2>
    <div class="grid">
      <div class="card"><b>Numerical learning</b><p>Retrain models on dated evidence and
      compare new candidates with the existing strategy.</p></div>
      <div class="card"><b>Structured memory</b><p>Retrieve past lessons and propose policy
      improvements, with testing and human review before adoption.</p></div>
    </div>
    <div class="note"><b>Scope:</b> daily, long/flat equities first; spot-crypto research stays
    separate. This is not an unrestricted AI trading bot, high-frequency platform or promise
    of returns. Real-money trading is optional and is not implemented in the starter.</div>
    """
    domains = [
        ("D1", "Data and features", "Collect, date and validate market observations; turn them into consistent numerical inputs."),
        ("D2", "Research and model lifecycle", "Train and compare algorithms, test costs and holdouts, and preserve evidence for candidate models."),
        ("D3", "Decision support", "Combine model signals and eligible lessons into explainable proposals. AI may assist with language, not execution authority."),
        ("D4", "Portfolio and risk", "Value the book and check projected exposure, loss limits, available cash and approval validity."),
        ("D5", "Execution and accounting", "Manage authorized orders, fills, fees and cash; reconcile the ledger with the broker. Broker integration is future work."),
        ("D6", "Memory and evaluation", "Connect decisions to matured outcomes, retrieve relevant lessons and measure whether adaptation actually helps."),
    ]
    cards = ''.join(
        f'<div class="card domain"><span class="number">{number}</span><div><b>{html.escape(title)}</b><p>{html.escape(description)}</p></div></div>'
        for number, title, description in domains
    )
    second = """
    <p>The architecture has <b>six responsibility layers (domains)</b> and two shared
    operating functions. These are clear boundaries inside a modular application—not a
    requirement to build six separate services.</p>
    <div class="grid">""" + cards + """</div>
    <h2>Two functions span every layer</h2>
    <div class="plane"><b>Control plane:</b> human approvals, scheduling, environment
    selection, HALT, secrets, releases and recovery.</div>
    <div class="plane"><b>Evidence plane:</b> decision history, data/model lineage,
    tests, metrics, alerts, audit export and backups.</div>
    <h2>The most important boundary</h2>
    <p><b>Models compute. Agents help explain. Risk enforces limits. Humans retain authority.</b>
    Agents cannot bypass the risk gate, approve their own actions or receive direct broker
    submission privileges. Unknown state should stop new risk, not invite a guess.</p>
    <h2>Simple deployment first</h2>
    <p>One Python package and one writer on a laptop. Parquet stores research data;
    SQLite holds prototype state. LangGraph is optional for checkpoints and human pauses.
    Add databases, servers or cloud services only when measured needs justify them.</p>
    <div class="note"><b>Target versus current:</b> shared targets, frozen artifacts and
    marked internal-paper accounting exist. Independent parity, authenticated approval,
    broker execution and operational certification remain gates.</div>
    """
    phases = [
        ("0", "Reproducible laptop", "Install the locked environment and prove that offline tests and the CLI work."),
        ("1", "Credible research", "Validate data and model experiments; admit a candidate only with evidence—or promote nothing."),
        ("2", "Correct paper lifecycle", "Build marked accounting, realistic paper execution, risk controls and replay-safe approvals."),
        ("3", "Measured memory", "Test retrieval, policy and bounded adaptation against a fixed numerical baseline."),
        ("4", "Broker-paper certification", "Prove reconciliation and failure handling; consider a supervised tiny-live trial only after separate approval."),
        ("5", "Reliable operations", "Monitor, back up, restore and manage releases; expand only through reviewed changes."),
    ]
    timeline = ''.join(
        f'<div class="phase"><strong>{number}</strong><b>{html.escape(title)}</b><span>{html.escape(description)}</span></div>'
        for number, title, description in phases
    )
    third = """
    <p>Progress is controlled by <b>evidence gates, not calendar deadlines</b>. Research can
    produce a useful negative result; a model is not entitled to promotion because the tools work.</p>
    """ + timeline + """
    <p class="small" style="margin-top:10px">Observation floors: 20 internal-paper equity
    sessions in Phase 2; 20 broker-paper sessions in Phase 4; 30 calendar days of operational
    evidence in Phase 5. These are not proof of profit or completion estimates.</p>
    <div class="grid status">
      <div class="card"><b>Available in the starter</b><ul>
        <li>Frozen artifacts, current approved inference and research evidence.</li>
        <li>Shared targets and a durable marked internal-paper simulator.</li>
        <li>Optional graph approvals, filtered lessons and read-only reports.</li>
      </ul></div>
      <div class="card"><b>Still required for operation</b><ul>
        <li>Independent accounting parity and realistic venue fill semantics.</li>
        <li>Authentic PIT inputs, promotion policy and immutable outcomes.</li>
        <li>Broker reconciliation, authenticated approvals, remote audit and recovery.</li>
      </ul></div>
    </div>
    <h2>What success looks like</h2>
    <p>Reproducible evidence, understandable decisions, enforced limits and dependable
    operations. If memory or AI does not improve the baseline, keep the simpler system.
    Staying paper-only—or retiring a weak strategy—is a valid outcome.</p>
    <div class="note"><b>Current status:</b> research and internal-paper prototype.
    No live broker adapter is provided. Tests and design documents do not establish
    profitable performance or production readiness.</div>
    """
    portfolio = """
    <div class="lead">Versioned evidence → scores → shared allocation → PortfolioTarget
    → fresh-mark plan → explicit approval and reservation → internal fills and events.</div>
    <div class="grid">
      <div class="card"><b>Allocation and explicit cash</b><p>Equal-weight and inverse-volatility
      allocation with optional reduce-only regime scaling. Immutable targets retain cash,
      decision/execution times and data/model/config lineage. Cash is not normalized into assets.</p></div>
      <div class="card"><b>Rebalancing and exits</b><p>Plan over all holdings and targets using
      complete fresh marks. Include sells and exits before buys; do not spend proceeds from
      unfilled sales. Desired allocation is not execution authority.</p></div>
      <div class="card"><b>Snapshots and frozen models</b><p>Content-addressed raw/feature snapshots,
      frozen estimators/transforms, digest/schema/code checks and explicit local model review.
      Approved inference has no silent fallback; stateless rules and replay are distinct modes.</p></div>
      <div class="card"><b>Research evidence</b><p>Versioned runs, exposure/cash histories,
      benchmark costs, matched-exposure and cash baselines, fold dispersion and doubled-cost
      sensitivity. Supplied sessions and known-at membership do not make Yahoo a PIT feed.</p></div>
      <div class="card"><b>Durable internal simulator</b><p>Marked equity, session/cashflow P&amp;L,
      partial fills, buys/sells, fees, cash/share reservations, cancellation and UNKNOWN blocking.
      Duplicate/conflicting fills are checked; fill and event writes are transactional.</p></div>
      <div class="card"><b>Read-only reporting</b><p>Escaped static HTML research reports and
      paper-order statistics. There are no dashboard trading controls or synthetic results
      represented as real observations.</p></div>
    </div>
    <h2>What was adopted—and what was not</h2>
    <p>FinRL-X informed weight-centric interfaces only. No package dependency or execution code
    was imported. Fabricated-price fallback and cash renormalization were not adopted.</p>
    <div class="note"><b>Boundary:</b> this is an internal simulator, not an exchange or broker.
    Supplied marks/fills are not a venue feed; a local reviewer string is not authentication.
    Shared allocation does not prove research/execution equivalence.</div>
    """
    agent_roles = """
    <div class="lead">Four deterministic Python roles—not four autonomous LLM agents.
    Numeric rules and shared allocation remain separate from explanatory prose.</div>
    <div class="grid">
      <div class="card"><b>Model Signal</b><p>Formats the model card's score, price,
      features and provenance for the decision record. It does not train the model or compute
      a new score.</p></div>
      <div class="card"><b>Bull Analyst</b><p>Builds favorable evidence from moving averages,
      momentum and RSI, with eligible historical lessons. It does not authorize execution.</p></div>
      <div class="card"><b>Bear Analyst</b><p>Highlights adverse momentum, volatility,
      RSI, score, costs and fill risks, with eligible lessons. Its prose does not set size.</p></div>
      <div class="card"><b>Portfolio Manager</b><p>Produces a structured proposal and evidence.
      Shared target allocation supplies desired deltas; risk/trust may reduce them.
      The standalone helper retains its compatibility sizing rule.</p></div>
    </div>
    <h2>Optional language assistance stays bounded</h2>
    <p>PM refinement is disabled by default. When explicitly enabled, it rewrites only
    thesis and invalidation text—not score, direction, position size or risk limits.
    Provider/key binding, injection tests and measured usefulness remain admission work.</p>
    <p>The separate sentiment boundary is disabled and shadow-only. It validates publication/
    availability times, typed responses and request/cost metadata. No news provider is connected;
    its results never enter allocation or execution.</p>
    <h2>Orchestration is not authority</h2>
    <p>Direct cycle and LangGraph share decision, target and projected-risk helpers plus
    decision-time lesson filtering. Their legacy immediate-close fills remain different from
    the durable paper CLI. A checkpoint is not portfolio truth or a new authorization.</p>
    <div class="note">Bull/Bear arguments do not independently decide direction or size.
    Agents cannot approve themselves. Graph approval expires from the snapshot (300 seconds
    by default), with risk and HALT rechecked before the toy fill.</div>
    """
    verification = """
    <h2>Expanded offline regression coverage</h2>
    <ul>
      <li><b>Portfolio:</b> explicit cash, deterministic targets, invalid weights, reduce-only
      scaling, exits and missing/stale/future marks.</li>
      <li><b>Artifacts:</b> immutable snapshots, model approval, digest/schema rejection,
      mature labels, supplied sessions, known-at membership and current inference.</li>
      <li><b>Ledger:</b> partial fills, fees, session P&amp;L, duplicate/conflicting IDs,
      cross-connection reservations, expiry/HALT checks, UNKNOWN blocking and audit rollback.</li>
      <li><b>Decisions and paper CLI:</b> direct/graph helper parity, structured evidence,
      future/open-lesson exclusion, explicit review and no side effects from a plan.</li>
      <li><b>Reports and shadow sentiment:</b> escaped read-only HTML, disabled integration,
      availability validation and bounded requests.</li>
    </ul>
    <h2>What the tests do not certify</h2>
    <p>Independent full-ledger/corporate-action parity, real liquidity and cancel/fill races,
    authentic PIT data, statistical alpha, authenticated/revocable approvals, broker
    reconciliation, remote audit and operational restore/observation remain gates.
    Test totals must come from a current run, not a historical count.</p>
    <h2>Reproducible development and operation</h2>
    <p>Use Python 3.12 and the existing lockfile with dev/graph extras. Run pytest, Ruff and
    CLI help offline before networked research. New interfaces added no application dependency.
    Coding-agent tooling is optional and separate from application authority.</p>
    <p>Use dedicated data/config profiles. The durable simulator follows session → plan →
    approve → fill → book. HALT blocks new risk; it is not a broker flatten command.
    Do not delete a database to resolve uncertain state or treat restore as permission to resume.</p>
    <div class="note"><b>Release boundary:</b> No live broker adapter is provided.
    Local hashes detect corruption, not replacement by someone controlling the artifact store.
    Load trusted local artifacts only; keep observation, independent review and recovery evidence
    separate from implementation completion.</div>
    """
    titles = ["Trading Desk v3", "The architecture, simplified", "Portfolio-first foundations",
              "Agents and bounded AI", "From idea to reliable operation", "Verification and release boundaries"]
    subtitles = ["Project overview · refreshed September 24, 2026",
                 "Six domains, shared controls and a small starting stack",
                 "Implemented interfaces, evidence and durable internal paper",
                 "Four roles, shared numeric decisions and disabled optional integrations",
                 "The phased roadmap and an honest view of readiness",
                 "Current automated coverage versus remaining admission obligations"]
    sources = ["README.md · trading-agents-architecture.md",
               "trading-agents-architecture.md · architecture-visual.md",
               "README.md · roadmap.md · operations-runbook.md",
               "README.md · langgraph-integration.md",
               "roadmap.md · phase-5-operations.md",
               "testing-and-acceptance.md · operations-runbook.md"]
    pages = []
    for index, (title, subtitle, content, source) in enumerate(zip(titles, subtitles, (first, second, portfolio, agent_roles, third, verification), sources, strict=True), 1):
        pages.append(
            '<section class="sheet"><div class="eyebrow">TRADING DESK / PROJECT OVERVIEW</div>'
            f'<h1>{html.escape(title)}</h1><div class="subtitle">{html.escape(subtitle)}</div>'
            f'<div class="body">{content}</div><div class="footer"><span>{html.escape(source)}</span>'
            f'<span>Overview / {index:02d}</span></div></section>'
        )
    document = '<!doctype html><html><head><meta charset="utf-8"><title>Trading Desk v3 - Project Overview</title><style>' + style + '</style></head><body>' + ''.join(pages) + '</body></html>'
    return document, [], titles


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the visual guide or concise project overview")
    parser.add_argument("--overview", action="store_true")
    args = parser.parse_args()
    if not Path(CHROME).is_file():
        raise FileNotFoundError("Set CHROME_PATH to an installed Chrome/Chromium executable")
    document, diagrams, titles = build_overview() if args.overview else build_document()
    output = ROOT / "Trading-Desk-v3-Project-Overview.pdf" if args.overview else OUTPUT
    with tempfile.TemporaryDirectory(prefix="trading-desk-pdf-build-") as directory:
        runtime = Path(directory)
        subprocess.run(["npm", "install", "--prefix", str(runtime), "--ignore-scripts", "--no-audit", "--no-fund", "--save-exact",
                        "mermaid@11.4.1", "puppeteer-core@24.16.0"], check=True)
        (runtime / "input.json").write_text(json.dumps({"html": document, "diagrams": diagrams, "chrome": CHROME, "output": str(output)}))
        (runtime / "render.cjs").write_text(NODE_RENDER)
        subprocess.run(["node", str(runtime / "render.cjs"), str(runtime)], check=True)
        stats = json.loads((runtime / "render-stats.json").read_text())
        for stat in stats:
            print(f"Diagram {stat['diagram']}: effective font {stat['effectiveFontPx']:.1f}px")
        small = [stat["diagram"] for stat in stats if stat["effectiveFontPx"] < 12]
        if small:
            raise ValueError(f"Diagrams {small} need a more readable layout")
    previews = Path(tempfile.mkdtemp(prefix="trading-desk-pdf-preview-"))
    with pymupdf.open(output) as pdf:
        if len(pdf) != len(titles):
            raise ValueError(f"Expected {len(titles)} pages, found {len(pdf)}")
        for number, (page, title) in enumerate(zip(pdf, titles, strict=True)):
            text = " ".join(page.get_text().split())
            if title not in text:
                raise ValueError(f"Page {number + 1} is missing its title")
            for word in page.get_text("words"):
                if word[0] < 0 or word[1] < 0 or word[2] > page.rect.width + 1 or word[3] > page.rect.height + 1:
                    raise ValueError(f"Text outside page {number + 1}: {word[4]}")
            page.get_pixmap(matrix=pymupdf.Matrix(1, 1), alpha=False).save(previews / f"page-{number + 1:02d}.png")
        print(f"PDF verified: {len(pdf)} pages, searchable text; {len(diagrams)} Mermaid diagrams")
    print(f"PDF: {output}")
    print(f"Preview images: {previews}")


if __name__ == "__main__":
    main()
