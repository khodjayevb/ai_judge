"""
Generates a self-contained HTML report with charts, scores, and recommendations.
Uses inline CSS/JS (Chart.js via CDN) — no local dependencies.
"""

from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path

from evaluators.scorer import EvalReport
from evaluators.recommender import Recommendation


def generate_html_report(
    report: EvalReport,
    recommendations: list[Recommendation],
    output_path: str = "reports/evaluation_report.html",
    system_prompt: str = "",
    model_name: str = "",
    mode: str = "",
) -> str:
    """Generate and save a beautiful HTML evaluation report."""

    category_scores = report.category_scores()
    cat_labels = json.dumps(list(category_scores.keys()))
    cat_values = json.dumps(list(category_scores.values()))

    test_labels = json.dumps([r.test_id for r in report.test_results])
    test_scores = json.dumps([r.score_pct for r in report.test_results])
    test_weights = json.dumps([r.weight for r in report.test_results])

    grade_color = _grade_color(report.grade)

    # Performance metrics
    perf = report.perf_summary()
    safety = report.safety_summary()
    latency_data = json.dumps([round(r.metrics.latency_seconds, 2) for r in report.test_results])

    # Build test detail rows
    test_rows = ""
    for r in report.test_results:
        criteria_html = ""
        for c in r.criteria_results:
            bar_color = _score_bar_color(c.score)
            criteria_html += f"""
            <div class="criterion-row">
                <div class="criterion-text">{html.escape(c.text)}</div>
                <div class="criterion-bar-wrap">
                    <div class="criterion-bar" style="width:{c.score*100}%;background:{bar_color}"></div>
                </div>
                <div class="criterion-score">{c.score:.0%}</div>
                <div class="criterion-explanation">{html.escape(c.explanation)}</div>
            </div>"""

        response_escaped = html.escape(r.response).replace("\n", "<br>")
        test_rows += f"""
        <div class="test-card">
            <div class="test-header">
                <span class="test-id">{r.test_id}</span>
                <span class="test-category badge">{r.category}</span>
                <span class="test-score" style="color:{_score_bar_color(r.score)}">{r.score_pct}%</span>
                <span class="test-weight">Weight: {r.weight}x | {r.metrics.latency_seconds:.1f}s | {r.metrics.output_tokens} tokens</span>
            </div>
            <div class="test-question"><strong>Q:</strong> {html.escape(r.question)}</div>
            <details class="test-details">
                <summary>View Response & Criteria Breakdown</summary>
                <div class="test-response">{response_escaped}</div>
                <div class="criteria-list">{criteria_html}</div>
            </details>
        </div>"""

    # Build recommendation cards
    rec_html = ""
    for rec in recommendations:
        p_class = rec.priority.lower()
        rec_html += f"""
        <div class="rec-card rec-{p_class}">
            <div class="rec-header">
                <span class="rec-priority badge badge-{p_class}">{rec.priority}</span>
                <span class="rec-category">{rec.category}</span>
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
<title>AI Evaluation Report — {html.escape(report.prompt_name)}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  :root {{
    --bg: #0f172a; --surface: #1e293b; --surface2: #334155;
    --text: #e2e8f0; --text2: #94a3b8; --accent: #38bdf8;
    --green: #22c55e; --yellow: #eab308; --red: #ef4444;
    --orange: #f97316; --purple: #a78bfa;
  }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:'Segoe UI',system-ui,-apple-system,sans-serif; background:var(--bg); color:var(--text); line-height:1.6; }}
  .container {{ max-width:1200px; margin:0 auto; padding:2rem; }}
  h1 {{ font-size:2rem; margin-bottom:0.25rem; }}
  h2 {{ font-size:1.4rem; margin:2rem 0 1rem; border-bottom:2px solid var(--surface2); padding-bottom:0.5rem; color:var(--accent); }}
  h3 {{ font-size:1.1rem; margin:1rem 0 0.5rem; }}
  h4 {{ font-size:1rem; margin:0.5rem 0; }}

  .header {{ text-align:center; padding:3rem 0 2rem; }}
  .header .subtitle {{ color:var(--text2); font-size:1rem; }}
  .meta {{ display:flex; gap:2rem; justify-content:center; margin-top:1rem; color:var(--text2); font-size:0.9rem; }}

  /* Grade badge */
  .grade-ring {{ display:inline-flex; align-items:center; justify-content:center;
    width:120px; height:120px; border-radius:50%;
    border:6px solid {grade_color}; margin:1.5rem auto; }}
  .grade-ring .grade {{ font-size:2.5rem; font-weight:800; color:{grade_color}; }}
  .grade-ring .pct {{ font-size:0.9rem; color:var(--text2); }}

  /* Score cards */
  .score-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:1rem; margin:1rem 0; }}
  .score-card {{ background:var(--surface); border-radius:12px; padding:1.25rem; text-align:center; }}
  .score-card .value {{ font-size:2rem; font-weight:700; }}
  .score-card .label {{ color:var(--text2); font-size:0.85rem; }}
  .score-card .hint {{ color:var(--text2); font-size:0.7rem; margin-top:0.4rem; line-height:1.3; opacity:0.7; }}

  /* Charts */
  .charts {{ display:grid; grid-template-columns:1fr 1fr; gap:2rem; margin:1.5rem 0; }}
  .chart-box {{ background:var(--surface); border-radius:12px; padding:1.5rem; }}
  @media(max-width:768px) {{ .charts {{ grid-template-columns:1fr; }} }}

  /* Test cards */
  .test-card {{ background:var(--surface); border-radius:12px; padding:1.25rem; margin-bottom:1rem; }}
  .test-header {{ display:flex; align-items:center; gap:1rem; flex-wrap:wrap; }}
  .test-id {{ font-weight:700; font-family:monospace; color:var(--accent); }}
  .test-score {{ font-weight:700; font-size:1.1rem; margin-left:auto; }}
  .test-weight {{ color:var(--text2); font-size:0.85rem; }}
  .test-question {{ margin:0.75rem 0; color:var(--text2); }}
  .test-details {{ margin-top:0.5rem; }}
  .test-details summary {{ cursor:pointer; color:var(--accent); font-size:0.9rem; }}
  .test-response {{ background:var(--bg); border-radius:8px; padding:1rem; margin:0.75rem 0;
    font-size:0.85rem; max-height:300px; overflow-y:auto; white-space:pre-wrap; word-break:break-word; }}

  /* Criteria */
  .criterion-row {{ display:grid; grid-template-columns:1fr 120px 50px; gap:0.5rem;
    align-items:center; padding:0.4rem 0; border-bottom:1px solid var(--surface2); }}
  .criterion-text {{ font-size:0.85rem; }}
  .criterion-bar-wrap {{ background:var(--surface2); border-radius:4px; height:8px; }}
  .criterion-bar {{ height:100%; border-radius:4px; transition:width 0.6s; }}
  .criterion-score {{ font-weight:600; text-align:right; font-size:0.85rem; }}
  .criterion-explanation {{ grid-column:1/-1; font-size:0.8rem; color:var(--text2); padding-left:0.5rem; }}

  /* Badges */
  .badge {{ display:inline-block; padding:0.15rem 0.6rem; border-radius:999px;
    font-size:0.75rem; font-weight:600; }}
  .badge-high {{ background:var(--red); color:#fff; }}
  .badge-medium {{ background:var(--orange); color:#fff; }}
  .badge-low {{ background:var(--green); color:#fff; }}

  /* Recommendation cards */
  .rec-card {{ background:var(--surface); border-radius:12px; padding:1.25rem;
    margin-bottom:1rem; border-left:4px solid var(--text2); }}
  .rec-high {{ border-left-color:var(--red); }}
  .rec-medium {{ border-left-color:var(--orange); }}
  .rec-low {{ border-left-color:var(--green); }}
  .rec-header {{ display:flex; align-items:center; gap:0.75rem; margin-bottom:0.5rem; }}
  .rec-category {{ color:var(--text2); font-size:0.85rem; }}
  .rec-suggestion {{ background:var(--bg); border-radius:8px; padding:1rem; margin-top:0.75rem; }}
  .rec-suggestion code {{ color:var(--accent); font-size:0.85rem; white-space:pre-wrap; }}

  /* Config section */
  .config-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:1.5rem; margin:1rem 0; }}
  @media(max-width:768px) {{ .config-grid {{ grid-template-columns:1fr; }} }}
  .config-card {{ background:var(--surface); border-radius:12px; padding:1.25rem; }}
  .config-card h3 {{ font-size:1rem; color:var(--accent); margin-bottom:0.75rem; }}
  .config-table {{ width:100%; }}
  .config-table td {{ padding:0.3rem 0.5rem; font-size:0.9rem; border-bottom:1px solid var(--surface2); }}
  .config-label {{ color:var(--text2); width:130px; font-weight:600; }}
  .config-card details summary {{ cursor:pointer; color:var(--accent); font-size:0.9rem; }}
  .system-prompt-text {{ background:var(--bg); border-radius:8px; padding:1rem; margin-top:0.75rem;
    font-size:0.8rem; max-height:400px; overflow-y:auto; white-space:pre-wrap; word-break:break-word;
    color:var(--text2); line-height:1.5; font-family:'Consolas','Courier New',monospace; }}

  /* Footer */
  .footer {{ text-align:center; color:var(--text2); font-size:0.8rem; margin-top:3rem;
    padding-top:1.5rem; border-top:1px solid var(--surface2); }}
</style>
</head>
<body>
<div class="container">

  <div class="header">
    <h1>AI System Prompt Evaluation Report</h1>
    <p class="subtitle">{html.escape(report.prompt_name)} v{html.escape(report.prompt_version)}</p>
    <div class="meta">
      <span>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</span>
      <span>Model: {html.escape(model_name or 'demo')}</span>
      <span>Mode: {html.escape(mode or 'demo')}</span>
      <span>Tests: {len(report.test_results)}</span>
      <span>Duration: {report.total_elapsed}s</span>
    </div>
    <div class="grade-ring">
      <div style="text-align:center">
        <div class="grade">{report.grade}</div>
        <div class="pct">{report.overall_pct}%</div>
      </div>
    </div>
  </div>

  <h2>Evaluation Configuration</h2>
  <div class="config-grid">
    <div class="config-card">
      <h3>Target Model</h3>
      <table class="config-table">
        <tr><td class="config-label">Model</td><td>{html.escape(model_name or 'demo (pre-generated)')}</td></tr>
        <tr><td class="config-label">Mode</td><td>{html.escape(mode or 'demo')}</td></tr>
        <tr><td class="config-label">Prompt Version</td><td>{html.escape(report.prompt_version)}</td></tr>
      </table>
    </div>
    <div class="config-card">
      <h3>System Prompt Under Test</h3>
      <details>
        <summary>View full system prompt ({len(system_prompt)} chars)</summary>
        <pre class="system-prompt-text">{html.escape(system_prompt) if system_prompt else '(demo mode — no prompt sent)'}</pre>
      </details>
    </div>
  </div>

  <div style="display:flex;gap:1rem;justify-content:center;margin:1.5rem 0">
    <a href="#section-quality" style="padding:0.4rem 1rem;background:var(--surface);border-radius:8px;color:var(--accent);text-decoration:none;font-size:0.85rem;font-weight:600">Section 1: Prompt Quality</a>
    <a href="#section-perf" style="padding:0.4rem 1rem;background:var(--surface);border-radius:8px;color:var(--purple);text-decoration:none;font-size:0.85rem;font-weight:600">Section 2: Performance</a>
    <a href="#section-safety" style="padding:0.4rem 1rem;background:var(--surface);border-radius:8px;color:var(--green);text-decoration:none;font-size:0.85rem;font-weight:600">Section 3: Safety</a>
  </div>

  <h2 id="section-quality" style="margin-top:1.5rem">
    <span style="background:var(--surface2);padding:0.2rem 0.8rem;border-radius:6px;font-size:0.75rem;vertical-align:middle;margin-right:0.5rem">SECTION 1</span>
    Prompt Quality Evaluation
  </h2>
  <div class="score-grid">
    <div class="score-card">
      <div class="value" style="color:{grade_color}">{report.overall_pct}%</div>
      <div class="label">Overall Score</div>
    </div>
    <div class="score-card">
      <div class="value" style="color:{grade_color}">{report.grade}</div>
      <div class="label">Grade</div>
    </div>
    <div class="score-card">
      <div class="value">{len(report.test_results)}</div>
      <div class="label">Test Cases</div>
    </div>
    <div class="score-card">
      <div class="value">{sum(len(r.criteria_results) for r in report.test_results)}</div>
      <div class="label">Criteria Evaluated</div>
    </div>
    <div class="score-card">
      <div class="value">{len(recommendations)}</div>
      <div class="label">Recommendations</div>
    </div>
  </div>

  <h3>Category Breakdown</h3>
  <div class="charts">
    <div class="chart-box">
      <canvas id="radarChart"></canvas>
    </div>
    <div class="chart-box">
      <canvas id="barChart"></canvas>
    </div>
  </div>

  <h3>Individual Test Results</h3>
  <div class="charts">
    <div class="chart-box" style="grid-column:1/-1">
      <canvas id="testChart"></canvas>
    </div>
  </div>
  {test_rows}

  <h3>Recommendations to Improve the System Prompt</h3>
  {rec_html if rec_html else '<p style="color:var(--text2)">No recommendations — the prompt is performing excellently!</p>'}

  {"" if not perf.get("available") else f'''
  <h2 id="section-perf" style="margin-top:3rem">
    <span style="background:var(--surface2);padding:0.2rem 0.8rem;border-radius:6px;font-size:0.75rem;vertical-align:middle;margin-right:0.5rem">SECTION 2</span>
    Performance Metrics
  </h2>
  <div class="score-grid">
    <div class="score-card">
      <div class="value" style="color:var(--accent)">{perf["avg_latency"]}s</div>
      <div class="label">Avg Latency</div>
      <div class="hint">Average time the model takes to return a complete response across all {len(report.test_results)} test cases</div>
    </div>
    <div class="score-card">
      <div class="value">{perf["p95_latency"]}s</div>
      <div class="label">P95 Latency</div>
      <div class="hint">95th percentile — 95% of responses completed faster than this. Shows worst-case performance excluding outliers</div>
    </div>
    <div class="score-card">
      <div class="value">{perf["min_latency"]}s / {perf["max_latency"]}s</div>
      <div class="label">Min / Max Latency</div>
      <div class="hint">Fastest and slowest individual response times. Large spread may indicate inconsistent model performance</div>
    </div>
    <div class="score-card">
      <div class="value">{perf["total_tokens"]:,}</div>
      <div class="label">Total Tokens</div>
      <div class="hint">Total tokens consumed across all {len(report.test_results)} test cases (prompts + responses). Tokens are the billing unit for LLM APIs</div>
    </div>
    <div class="score-card">
      <div class="value">{perf["total_input_tokens"]:,} / {perf["total_output_tokens"]:,}</div>
      <div class="label">Input / Output Tokens</div>
      <div class="hint">Input = system prompt + question sent to model. Output = model's response. Output tokens are typically 3-6x more expensive</div>
    </div>
    <div class="score-card">
      <div class="value">{perf["avg_output_tokens"]:,}</div>
      <div class="label">Avg Output Tokens</div>
      <div class="hint">Average response size per question. Higher = more verbose answers. ~750 tokens is roughly one page of text</div>
    </div>
    <div class="score-card">
      <div class="value">{perf["avg_response_words"]}</div>
      <div class="label">Avg Response Words</div>
      <div class="hint">Average word count per response. Useful for comparing verbosity across different models or prompt versions</div>
    </div>
    <div class="score-card">
      <div class="value">${perf["estimated_cost_usd"]:.4f}</div>
      <div class="label">Estimated Cost (USD)</div>
      <div class="hint">Estimated API cost for this evaluation run ({len(report.test_results)} test cases). Based on {perf["model_id"]} published pricing. Does not include judge model costs</div>
    </div>
  </div>
  <div class="charts">
    <div class="chart-box" style="grid-column:1/-1">
      <canvas id="latencyChart"></canvas>
    </div>
  </div>
  '''}

  {"" if not safety.get("available") else f'''
  <h2 id="section-safety" style="margin-top:3rem">
    <span style="background:var(--surface2);padding:0.2rem 0.8rem;border-radius:6px;font-size:0.75rem;vertical-align:middle;margin-right:0.5rem">SECTION 3</span>
    Safety Metrics
  </h2>
  <p style="color:var(--text2);margin-bottom:1rem">Automated safety checks run on every model response. Lower scores = safer. Threshold: 0.5</p>
  <div class="score-grid">
    {"".join(f"""
    <div class="score-card" style="border-top:3px solid {'var(--green)' if data['pass_rate'] >= 90 else 'var(--yellow)' if data['pass_rate'] >= 70 else 'var(--red)'}">
      <div class="value" style="color:{'var(--green)' if data['pass_rate'] >= 90 else 'var(--yellow)' if data['pass_rate'] >= 70 else 'var(--red)'}">{data['pass_rate']}%</div>
      <div class="label">{name.replace('_', ' ').title()} Pass Rate</div>
      <div class="hint">Avg score: {data['avg_score']} | Max: {data['max_score']} | {data['total_tested']} tests</div>
    </div>""" for name, data in safety.get("metrics", {{}}).items())}
    <div class="score-card" style="border-top:3px solid {'var(--green)' if safety['overall_pass_rate'] >= 90 else 'var(--yellow)' if safety['overall_pass_rate'] >= 70 else 'var(--red)'}">
      <div class="value" style="color:{'var(--green)' if safety['overall_pass_rate'] >= 90 else 'var(--yellow)' if safety['overall_pass_rate'] >= 70 else 'var(--red)'}">{safety['overall_pass_rate']}%</div>
      <div class="label">Overall Safety Pass Rate</div>
      <div class="hint">Percentage of responses passing all safety checks</div>
    </div>
  </div>
  '''}

  <div class="footer">
    <p>Generated by <strong>AI Evaluation Framework</strong> | {datetime.now().strftime('%Y')}</p>
  </div>

</div>

<script>
const catLabels = {cat_labels};
const catValues = {cat_values};
const testLabels = {test_labels};
const testScores = {test_scores};
const testWeights = {test_weights};

Chart.defaults.color = '#94a3b8';
Chart.defaults.borderColor = '#334155';

// Radar chart
new Chart(document.getElementById('radarChart'), {{
  type: 'radar',
  data: {{
    labels: catLabels,
    datasets: [{{
      label: 'Score %',
      data: catValues,
      fill: true,
      backgroundColor: 'rgba(56,189,248,0.15)',
      borderColor: '#38bdf8',
      pointBackgroundColor: '#38bdf8',
      pointBorderColor: '#fff',
      pointRadius: 5,
    }}]
  }},
  options: {{
    scales: {{
      r: {{
        beginAtZero: true, max: 100,
        grid: {{ color: '#334155' }},
        angleLines: {{ color: '#334155' }},
        ticks: {{ stepSize: 20, backdropColor: 'transparent' }},
      }}
    }},
    plugins: {{ legend: {{ display: false }} }}
  }}
}});

// Category bar chart
const barColors = catValues.map(v => v >= 90 ? '#22c55e' : v >= 75 ? '#eab308' : '#ef4444');
new Chart(document.getElementById('barChart'), {{
  type: 'bar',
  data: {{
    labels: catLabels,
    datasets: [{{
      label: 'Score %',
      data: catValues,
      backgroundColor: barColors,
      borderRadius: 6,
    }}]
  }},
  options: {{
    indexAxis: 'y',
    scales: {{ x: {{ beginAtZero: true, max: 100 }} }},
    plugins: {{ legend: {{ display: false }} }}
  }}
}});

// Individual test chart
const wColors = testWeights.map(w => w >= 3 ? '#a78bfa' : w >= 2 ? '#38bdf8' : '#94a3b8');
new Chart(document.getElementById('testChart'), {{
  type: 'bar',
  data: {{
    labels: testLabels,
    datasets: [{{
      label: 'Score %',
      data: testScores,
      backgroundColor: testScores.map(s => s >= 90 ? '#22c55e' : s >= 75 ? '#eab308' : '#ef4444'),
      borderRadius: 6,
    }}]
  }},
  options: {{
    scales: {{ y: {{ beginAtZero: true, max: 100 }} }},
    plugins: {{ legend: {{ display: false }} }}
  }}
}});

// Latency chart
const latencyEl = document.getElementById('latencyChart');
if (latencyEl) {{
  const latencyData = {latency_data};
  new Chart(latencyEl, {{
    type: 'bar',
    data: {{
      labels: testLabels,
      datasets: [{{
        label: 'Latency (seconds)',
        data: latencyData,
        backgroundColor: latencyData.map(l => l > 10 ? '#ef4444' : l > 5 ? '#eab308' : '#38bdf8'),
        borderRadius: 6,
      }}]
    }},
    options: {{
      scales: {{ y: {{ beginAtZero: true, title: {{ display: true, text: 'Seconds' }} }} }},
      plugins: {{ legend: {{ display: false }},
        title: {{ display: true, text: 'Response Latency per Test Case', color: '#e2e8f0' }} }}
    }}
  }});
}}
</script>
</body>
</html>"""

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report_html, encoding="utf-8")
    return str(out.resolve())


def _grade_color(grade: str) -> str:
    if grade.startswith("A"):
        return "#22c55e"
    if grade.startswith("B"):
        return "#eab308"
    if grade.startswith("C"):
        return "#f97316"
    return "#ef4444"


def _score_bar_color(score: float) -> str:
    if score >= 0.9:
        return "#22c55e"
    if score >= 0.75:
        return "#eab308"
    return "#ef4444"
