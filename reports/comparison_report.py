"""
Generates a side-by-side comparison HTML report for two evaluation runs.
Shows deltas, improvement arrows, and highlights wins/regressions.
"""

from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path

from evaluators.scorer import EvalReport
from evaluators.recommender import Recommendation


def generate_comparison_report(
    report_v1: EvalReport,
    report_v2: EvalReport,
    recommendations: list[Recommendation],
    output_path: str = "reports/comparison_report.html",
    system_prompt_v1: str = "",
    system_prompt_v2: str = "",
    model_name: str = "",
    mode: str = "",
) -> str:
    """Generate a side-by-side comparison report."""

    cat_v1 = report_v1.category_scores()
    cat_v2 = report_v2.category_scores()
    all_cats = sorted(set(list(cat_v1.keys()) + list(cat_v2.keys())))

    # Chart data
    cat_labels = json.dumps(all_cats)
    cat_v1_vals = json.dumps([cat_v1.get(c, 0) for c in all_cats])
    cat_v2_vals = json.dumps([cat_v2.get(c, 0) for c in all_cats])

    delta_overall = report_v2.overall_pct - report_v1.overall_pct
    delta_sign = "+" if delta_overall > 0 else ""
    delta_color = "#22c55e" if delta_overall > 0 else "#ef4444" if delta_overall < 0 else "#94a3b8"

    # Category comparison rows
    cat_rows = ""
    for cat in all_cats:
        s1 = cat_v1.get(cat, 0)
        s2 = cat_v2.get(cat, 0)
        d = s2 - s1
        arrow = "&#9650;" if d > 0 else "&#9660;" if d < 0 else "&#8212;"
        d_color = "#22c55e" if d > 0 else "#ef4444" if d < 0 else "#94a3b8"
        cat_rows += f"""
        <tr>
            <td>{html.escape(cat)}</td>
            <td class="num">{s1}%</td>
            <td class="num">{s2}%</td>
            <td class="num" style="color:{d_color};font-weight:700">{arrow} {d:+.1f}%</td>
        </tr>"""

    # Per-test comparison rows
    test_rows = ""
    v1_map = {r.test_id: r for r in report_v1.test_results}
    v2_map = {r.test_id: r for r in report_v2.test_results}
    all_ids = list(dict.fromkeys([r.test_id for r in report_v1.test_results] +
                                  [r.test_id for r in report_v2.test_results]))

    for tid in all_ids:
        r1 = v1_map.get(tid)
        r2 = v2_map.get(tid)
        s1 = r1.score_pct if r1 else 0
        s2 = r2.score_pct if r2 else 0
        d = s2 - s1
        arrow = "&#9650;" if d > 0 else "&#9660;" if d < 0 else "&#8212;"
        d_color = "#22c55e" if d > 0 else "#ef4444" if d < 0 else "#94a3b8"
        cat = r1.category if r1 else (r2.category if r2 else "")

        # Criteria detail
        criteria_detail = ""
        if r1 and r2:
            for c1, c2 in zip(r1.criteria_results, r2.criteria_results):
                cd = c2.score - c1.score
                c_arrow = "&#9650;" if cd > 0 else "&#9660;" if cd < 0 else "&#8212;"
                c_color = "#22c55e" if cd > 0 else "#ef4444" if cd < 0 else "#94a3b8"
                criteria_detail += f"""
                <div class="crit-compare">
                    <span class="crit-text">{html.escape(c1.text)}</span>
                    <span class="crit-s">{c1.score:.0%}</span>
                    <span class="crit-arrow" style="color:{c_color}">{c_arrow}</span>
                    <span class="crit-s">{c2.score:.0%}</span>
                </div>"""

        test_rows += f"""
        <div class="test-compare-card">
            <div class="tc-header">
                <span class="test-id">{tid}</span>
                <span class="badge">{html.escape(cat)}</span>
                <span class="tc-scores">
                    <span class="tc-v1">{s1}%</span>
                    <span class="tc-arrow" style="color:{d_color}">{arrow} {d:+.1f}%</span>
                    <span class="tc-v2">{s2}%</span>
                </span>
            </div>
            <details>
                <summary>Criteria Breakdown</summary>
                <div class="crit-grid">
                    <div class="crit-header">
                        <span>Criterion</span><span>V1</span><span></span><span>V2</span>
                    </div>
                    {criteria_detail}
                </div>
            </details>
        </div>"""

    # Recommendation cards
    rec_html = ""
    for rec in recommendations:
        p_class = rec.priority.lower()
        rec_html += f"""
        <div class="rec-card rec-{p_class}">
            <div class="rec-header">
                <span class="badge badge-{p_class}">{rec.priority}</span>
                <span class="rec-cat">{rec.category}</span>
            </div>
            <h4>{html.escape(rec.title)}</h4>
            <p>{html.escape(rec.description)}</p>
            <div class="rec-suggestion">
                <strong>Suggested prompt change:</strong><br>
                <code>{html.escape(rec.prompt_suggestion)}</code>
            </div>
        </div>"""

    report_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Prompt Evaluation Comparison — V1 vs V2</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  :root {{
    --bg: #0f172a; --surface: #1e293b; --surface2: #334155;
    --text: #e2e8f0; --text2: #94a3b8; --accent: #38bdf8;
    --green: #22c55e; --yellow: #eab308; --red: #ef4444;
    --orange: #f97316; --purple: #a78bfa;
  }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:'Segoe UI',system-ui,sans-serif; background:var(--bg); color:var(--text); line-height:1.6; }}
  .container {{ max-width:1200px; margin:0 auto; padding:2rem; }}
  h1 {{ font-size:2rem; text-align:center; }}
  h2 {{ font-size:1.3rem; margin:2.5rem 0 1rem; border-bottom:2px solid var(--surface2); padding-bottom:0.5rem; color:var(--accent); }}
  .subtitle {{ text-align:center; color:var(--text2); margin-bottom:2rem; }}

  /* Hero comparison */
  .hero {{ display:flex; justify-content:center; align-items:center; gap:3rem; margin:2rem 0; flex-wrap:wrap; }}
  .hero-card {{ background:var(--surface); border-radius:16px; padding:2rem 3rem; text-align:center; min-width:200px; }}
  .hero-card .version {{ font-size:0.9rem; color:var(--text2); margin-bottom:0.5rem; }}
  .hero-card .grade {{ font-size:3rem; font-weight:800; }}
  .hero-card .pct {{ font-size:1.1rem; color:var(--text2); }}
  .hero-arrow {{ font-size:3rem; color:{delta_color}; font-weight:700; }}
  .hero-delta {{ text-align:center; }}
  .hero-delta .delta-val {{ font-size:2rem; font-weight:800; color:{delta_color}; }}
  .hero-delta .delta-label {{ font-size:0.85rem; color:var(--text2); }}

  /* Table */
  table {{ width:100%; border-collapse:collapse; background:var(--surface); border-radius:12px; overflow:hidden; }}
  th {{ background:var(--surface2); padding:0.75rem 1rem; text-align:left; font-size:0.85rem; color:var(--text2); }}
  td {{ padding:0.75rem 1rem; border-bottom:1px solid var(--surface2); }}
  .num {{ text-align:center; font-family:monospace; font-size:0.95rem; }}

  /* Charts */
  .charts {{ display:grid; grid-template-columns:1fr 1fr; gap:2rem; margin:1.5rem 0; }}
  .chart-box {{ background:var(--surface); border-radius:12px; padding:1.5rem; }}
  @media(max-width:768px) {{ .charts {{ grid-template-columns:1fr; }} }}

  /* Test compare cards */
  .test-compare-card {{ background:var(--surface); border-radius:12px; padding:1.25rem; margin-bottom:0.75rem; }}
  .tc-header {{ display:flex; align-items:center; gap:1rem; flex-wrap:wrap; }}
  .test-id {{ font-weight:700; font-family:monospace; color:var(--accent); }}
  .tc-scores {{ margin-left:auto; display:flex; align-items:center; gap:0.5rem; font-weight:600; }}
  .tc-v1 {{ color:var(--text2); }}
  .tc-v2 {{ color:var(--accent); }}
  .tc-arrow {{ font-size:0.9rem; }}
  details summary {{ cursor:pointer; color:var(--accent); font-size:0.85rem; margin-top:0.5rem; }}

  .crit-grid {{ margin-top:0.75rem; }}
  .crit-header {{ display:grid; grid-template-columns:1fr 50px 30px 50px; gap:0.5rem; color:var(--text2); font-size:0.8rem; font-weight:600; padding-bottom:0.5rem; border-bottom:1px solid var(--surface2); }}
  .crit-compare {{ display:grid; grid-template-columns:1fr 50px 30px 50px; gap:0.5rem; padding:0.35rem 0; font-size:0.85rem; border-bottom:1px solid var(--bg); }}
  .crit-s {{ text-align:center; font-family:monospace; }}
  .crit-arrow {{ text-align:center; }}

  .badge {{ display:inline-block; padding:0.15rem 0.6rem; border-radius:999px; font-size:0.75rem; font-weight:600; background:var(--surface2); }}
  .badge-high {{ background:var(--red); color:#fff; }}
  .badge-medium {{ background:var(--orange); color:#fff; }}
  .badge-low {{ background:var(--green); color:#fff; }}

  .rec-card {{ background:var(--surface); border-radius:12px; padding:1.25rem; margin-bottom:1rem; border-left:4px solid var(--text2); }}
  .rec-high {{ border-left-color:var(--red); }}
  .rec-medium {{ border-left-color:var(--orange); }}
  .rec-low {{ border-left-color:var(--green); }}
  .rec-header {{ display:flex; align-items:center; gap:0.75rem; margin-bottom:0.5rem; }}
  .rec-cat {{ color:var(--text2); font-size:0.85rem; }}
  .rec-suggestion {{ background:var(--bg); border-radius:8px; padding:1rem; margin-top:0.75rem; }}
  .rec-suggestion code {{ color:var(--accent); font-size:0.85rem; white-space:pre-wrap; }}

  .footer {{ text-align:center; color:var(--text2); font-size:0.8rem; margin-top:3rem; padding-top:1.5rem; border-top:1px solid var(--surface2); }}
</style>
</head>
<body>
<div class="container">

  <h1>System Prompt Evaluation: V1 vs V2</h1>
  <p class="subtitle">Side-by-side comparison showing the impact of prompt improvements</p>

  <div class="hero">
    <div class="hero-card">
      <div class="version">V1 Baseline</div>
      <div class="grade" style="color:{"#eab308" if report_v1.grade.startswith("B") else "#ef4444" if report_v1.grade.startswith(("C","D")) else "#22c55e"}">{report_v1.grade}</div>
      <div class="pct">{report_v1.overall_pct}%</div>
    </div>
    <div class="hero-delta">
      <div class="hero-arrow">&#10132;</div>
      <div class="delta-val">{delta_sign}{delta_overall:.1f}%</div>
      <div class="delta-label">improvement</div>
    </div>
    <div class="hero-card">
      <div class="version">V2 Improved</div>
      <div class="grade" style="color:{"#22c55e" if report_v2.grade.startswith("A") else "#eab308"}">{report_v2.grade}</div>
      <div class="pct">{report_v2.overall_pct}%</div>
    </div>
  </div>

  <h2>Evaluation Configuration</h2>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:1.5rem;margin:1rem 0">
    <div style="background:var(--surface);border-radius:12px;padding:1.25rem">
      <h3 style="color:var(--red);font-size:1rem;margin-bottom:0.5rem">V1 Baseline Prompt</h3>
      <p style="color:var(--text2);font-size:0.85rem;margin-bottom:0.5rem">Model: {html.escape(model_name or 'demo')} | Mode: {html.escape(mode or 'demo')}</p>
      <details><summary style="cursor:pointer;color:var(--accent);font-size:0.85rem">View system prompt ({len(system_prompt_v1)} chars)</summary>
        <pre style="background:var(--bg);border-radius:8px;padding:1rem;margin-top:0.5rem;font-size:0.75rem;max-height:300px;overflow-y:auto;white-space:pre-wrap;color:var(--text2);font-family:monospace">{html.escape(system_prompt_v1) if system_prompt_v1 else '(demo mode)'}</pre>
      </details>
    </div>
    <div style="background:var(--surface);border-radius:12px;padding:1.25rem">
      <h3 style="color:var(--accent);font-size:1rem;margin-bottom:0.5rem">V2 Improved Prompt</h3>
      <p style="color:var(--text2);font-size:0.85rem;margin-bottom:0.5rem">Model: {html.escape(model_name or 'demo')} | Mode: {html.escape(mode or 'demo')}</p>
      <details><summary style="cursor:pointer;color:var(--accent);font-size:0.85rem">View system prompt ({len(system_prompt_v2)} chars)</summary>
        <pre style="background:var(--bg);border-radius:8px;padding:1rem;margin-top:0.5rem;font-size:0.75rem;max-height:300px;overflow-y:auto;white-space:pre-wrap;color:var(--text2);font-family:monospace">{html.escape(system_prompt_v2) if system_prompt_v2 else '(demo mode)'}</pre>
      </details>
    </div>
  </div>

  <h2>Category Comparison</h2>
  <div class="charts">
    <div class="chart-box">
      <canvas id="radarCompare"></canvas>
    </div>
    <div class="chart-box">
      <canvas id="barCompare"></canvas>
    </div>
  </div>

  <table>
    <thead><tr><th>Category</th><th>V1</th><th>V2</th><th>Delta</th></tr></thead>
    <tbody>{cat_rows}</tbody>
  </table>

  <h2>Per-Test Comparison</h2>
  {test_rows}

  <h2>Remaining Recommendations (V2)</h2>
  {rec_html if rec_html else '<p style="color:var(--text2)">No further recommendations. The prompt is performing excellently.</p>'}

  <div class="footer">
    <p>Generated by <strong>AI Evaluation Framework</strong> | {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
  </div>

</div>

<script>
const labels = {cat_labels};
const v1 = {cat_v1_vals};
const v2 = {cat_v2_vals};

Chart.defaults.color = '#94a3b8';
Chart.defaults.borderColor = '#334155';

new Chart(document.getElementById('radarCompare'), {{
  type: 'radar',
  data: {{
    labels,
    datasets: [
      {{ label: 'V1 Baseline', data: v1, fill: true,
        backgroundColor: 'rgba(239,68,68,0.1)', borderColor: '#ef4444',
        pointBackgroundColor: '#ef4444', pointRadius: 4 }},
      {{ label: 'V2 Improved', data: v2, fill: true,
        backgroundColor: 'rgba(56,189,248,0.15)', borderColor: '#38bdf8',
        pointBackgroundColor: '#38bdf8', pointRadius: 4 }},
    ]
  }},
  options: {{
    scales: {{ r: {{ beginAtZero: true, max: 100,
      grid: {{ color: '#334155' }}, angleLines: {{ color: '#334155' }},
      ticks: {{ stepSize: 20, backdropColor: 'transparent' }} }} }},
    plugins: {{ legend: {{ position: 'bottom' }} }}
  }}
}});

new Chart(document.getElementById('barCompare'), {{
  type: 'bar',
  data: {{
    labels,
    datasets: [
      {{ label: 'V1 Baseline', data: v1, backgroundColor: '#ef4444aa', borderRadius: 4 }},
      {{ label: 'V2 Improved', data: v2, backgroundColor: '#38bdf8', borderRadius: 4 }},
    ]
  }},
  options: {{
    indexAxis: 'y',
    scales: {{ x: {{ beginAtZero: true, max: 100 }} }},
    plugins: {{ legend: {{ position: 'bottom' }} }}
  }}
}});
</script>
</body>
</html>"""

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report_html, encoding="utf-8")
    return str(out.resolve())
