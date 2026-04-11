// AI Evaluation Framework — Dashboard JavaScript

// ── UI Utilities ──
function showToast(message, type) {
  type = type || 'info';
  const colors = {info: 'var(--accent)', success: 'var(--green)', error: 'var(--red)', warning: 'var(--yellow)'};
  const toast = document.createElement('div');
  toast.style.cssText = 'position:fixed;top:1rem;right:1rem;z-index:2000;background:var(--surface);border:1px solid ' + (colors[type]||colors.info) + ';border-radius:8px;padding:0.75rem 1.25rem;font-size:0.85rem;color:var(--text);max-width:400px;box-shadow:0 4px 12px rgba(0,0,0,0.3);animation:fadeIn 0.3s';
  toast.innerHTML = '<span style="color:' + (colors[type]||colors.info) + ';font-weight:600;margin-right:0.5rem">' + (type === 'error' ? '✕' : type === 'success' ? '✓' : 'ℹ') + '</span>' + message;
  document.body.appendChild(toast);
  setTimeout(() => { toast.style.opacity = '0'; toast.style.transition = 'opacity 0.3s'; setTimeout(() => toast.remove(), 300); }, 4000);
}

function switchTab(tab) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.querySelector(`.tab-content#tab-${tab}`).classList.add('active');
  // Walk up to the .tab element (handles clicks on icon span children)
  let target = event.target;
  while (target && !target.classList.contains('tab')) target = target.parentElement;
  if (target) target.classList.add('active');
  setTimeout(updateHeaderTarget, 50);
  refreshHistory();
}

// ── Docs nav scroll spy ──
(function() {
  const nav = document.getElementById('docsNav');
  if (!nav) return;
  const links = Array.from(nav.querySelectorAll('a[href^="#"]'));
  const ids = links.map(a => a.getAttribute('href').slice(1));
  const sections = ids.map(id => document.getElementById(id)).filter(Boolean);
  if (!sections.length) return;

  function setActive(id) {
    links.forEach(a => a.classList.toggle('active', a.getAttribute('href') === '#' + id));
  }

  const obs = new IntersectionObserver((entries) => {
    entries.forEach(e => {
      if (e.isIntersecting) setActive(e.target.id);
    });
  }, { rootMargin: '-20% 0% -70% 0%', threshold: 0 });
  sections.forEach(s => obs.observe(s));

  // Click handler: smooth scroll + immediately update active state
  links.forEach(a => {
    a.addEventListener('click', (ev) => {
      const id = a.getAttribute('href').slice(1);
      const el = document.getElementById(id);
      if (el) {
        ev.preventDefault();
        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        setActive(id);
      }
    });
  });
})();

// Load history on page load
document.addEventListener('DOMContentLoaded', () => refreshHistory());

// Custom model inputs + update header
// defaultModel and defaultProvider are set in the HTML template as global vars

document.querySelectorAll('select[id*=Model]').forEach(sel => {
  sel.addEventListener('change', () => {
    const custom = document.getElementById(sel.id + 'Custom');
    if (custom) custom.style.display = sel.value === 'custom' ? 'block' : 'none';
    updateHeaderTarget();
  });
});

function updateHeaderTarget() {
  // No-op — header no longer shows target/judge (moved to Settings)
}

function getModel(selectId) {
  const sel = document.getElementById(selectId);
  if (sel.value === 'custom') {
    return document.getElementById(selectId + 'Custom').value;
  }
  return sel.value;
}

// Run evaluation
function runEval() {
  const role = document.getElementById('evalRole').value;
  const model = getModel('evalModel');
  const prompt = getPromptValue('evalPrompt', 'evalCustomPrompt');
  const runs = parseInt(document.getElementById('evalRuns').value);
  document.getElementById('btnEval').disabled = true;
  showProgress('eval');
  if (runs > 1) {
    document.getElementById('evalText').textContent = `Running ${runs}x evaluations for averaging...`;
  }

  fetch('/api/run', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({role, run_type: 'evaluation', model, prompt_source: prompt, runs})
  }).then(r => r.json()).then(d => pollJob(d.job_id, 'eval'));
}

// Run comparison
let _generatedTests = [];

function runGenerate() {
  const role = document.getElementById('genRole').value;
  const count = document.getElementById('genCount').value;
  document.getElementById('btnGenerate').disabled = true;
  document.getElementById('genTestCases').style.display = 'none';
  showProgress('gen');
  document.getElementById('genBar').style.width = '50%';
  document.getElementById('genText').textContent = `Generating ${count} test cases for ${role}...`;

  fetch('/api/generate', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({role, count})
  }).then(r => r.json()).then(d => pollJob(d.job_id, 'gen'));
}

function toggleCustomPrompt(textareaId, value) {
  const ta = document.getElementById(textareaId);
  if (ta) ta.style.display = value === 'custom' ? 'block' : 'none';
}

function getPromptValue(selectId, textareaId) {
  const sel = document.getElementById(selectId);
  if (sel.value === 'custom') {
    return 'custom:' + document.getElementById(textareaId).value;
  }
  return sel.value;
}

// ── Theme ──
function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme') || 'dark';
  const next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
  document.getElementById('themeBtn').textContent = next === 'dark' ? '☀️ Light' : '🌙 Dark';
}

// Apply saved theme on load
(function() {
  const saved = localStorage.getItem('theme') || 'dark';
  document.documentElement.setAttribute('data-theme', saved);
  const btn = document.getElementById('themeBtn');
  if (btn) btn.textContent = saved === 'dark' ? '☀️ Light' : '🌙 Dark';
})();

function toggleSettings() {
  const modal = document.getElementById('settingsModal');
  if (modal.style.display === 'none' || !modal.style.display) {
    modal.style.display = 'block';
    loadSettings();
  } else {
    modal.style.display = 'none';
  }
}

// ── Settings ──
function loadSettings() {
  fetch('/api/settings').then(r => r.json()).then(data => {
    const s = data.settings || {};
    document.getElementById('setTargetProvider').value = s.TARGET_PROVIDER || 'azure';
    document.getElementById('setTargetKey').value = s.TARGET_API_KEY || '';
    document.getElementById('setTargetModel').value = s.TARGET_MODEL || s.TARGET_DEPLOYMENT || '';
    document.getElementById('setTargetURL').value = s.TARGET_BASE_URL || '';
    document.getElementById('setTargetVersion').value = s.TARGET_API_VERSION || '2024-08-01-preview';
    document.getElementById('setJudgeProvider').value = s.JUDGE_PROVIDER || '';
    document.getElementById('setJudgeKey').value = s.JUDGE_API_KEY || '';
    document.getElementById('setJudgeModel').value = s.JUDGE_MODEL || s.JUDGE_DEPLOYMENT || '';
    document.getElementById('setJudgeURL').value = s.JUDGE_BASE_URL || '';

    // Load assistant mappings
    const ra = data.role_assistants || {};
    for (const [slug, id] of Object.entries(ra)) {
      const el = document.getElementById('asst_' + slug);
      if (el) el.value = id;
    }
  });
}

function saveSettings() {
  const settings = {
    TARGET_PROVIDER: document.getElementById('setTargetProvider').value,
    TARGET_API_KEY: document.getElementById('setTargetKey').value,
    TARGET_MODEL: document.getElementById('setTargetModel').value,
    TARGET_DEPLOYMENT: document.getElementById('setTargetModel').value,
    TARGET_BASE_URL: document.getElementById('setTargetURL').value,
    TARGET_API_VERSION: document.getElementById('setTargetVersion').value,
    JUDGE_PROVIDER: document.getElementById('setJudgeProvider').value,
    JUDGE_API_KEY: document.getElementById('setJudgeKey').value,
    JUDGE_MODEL: document.getElementById('setJudgeModel').value,
    JUDGE_DEPLOYMENT: document.getElementById('setJudgeModel').value,
    JUDGE_BASE_URL: document.getElementById('setJudgeURL').value,
  };

  // Collect assistant mappings (skip status elements)
  const role_assistants = {};
  document.querySelectorAll('input[id^="asst_"]').forEach(el => {
    if (el.id.startsWith('asst_status_')) return;
    const slug = el.id.replace('asst_', '');
    if (el.value && el.value.trim()) role_assistants[slug] = el.value.trim();
  });

  fetch('/api/settings', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({settings, role_assistants})
  }).then(r => r.json()).then(d => {
    const flash = document.getElementById('settingsResult');
    flash.classList.add('active');
    if (d.success) {
      flash.className = 'result-flash active success';
      flash.innerHTML = '<strong>Settings saved!</strong> Restart the dashboard to apply changes.';
    } else {
      flash.className = 'result-flash active error';
      flash.innerHTML = '<strong>Error:</strong> ' + (d.error || d.message);
    }
  });
}

function testConnection() {
  const status = document.getElementById('connectionStatus');
  status.innerHTML = '<span style="color:var(--yellow)">Testing connection...</span>';

  fetch('/api/test-connection', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      provider: document.getElementById('setTargetProvider').value,
      base_url: document.getElementById('setTargetURL').value,
      api_key: document.getElementById('setTargetKey').value,
      model: document.getElementById('setTargetModel').value,
      api_version: document.getElementById('setTargetVersion').value,
    })
  }).then(r => r.json()).then(d => {
    if (d.success) {
      status.innerHTML = '<span style="color:var(--green);font-weight:600">&#10004; ' + d.message + '</span>';
    } else {
      status.innerHTML = '<span style="color:var(--red)">&#10008; ' + d.message + '</span>';
    }
  }).catch(e => {
    status.innerHTML = '<span style="color:var(--red)">&#10008; Error: ' + e.message + '</span>';
  });
}

function testAllAssistants() {
  document.querySelectorAll('[id^="asst_status_"]').forEach(el => el.textContent = '...');

  document.querySelectorAll('[id^="asst_"]').forEach(el => {
    if (el.id.startsWith('asst_status_')) return;
    const slug = el.id.replace('asst_', '');
    const assistantId = el.value.trim();
    const statusEl = document.getElementById('asst_status_' + slug);
    if (!assistantId) { statusEl.textContent = '—'; return; }

    statusEl.innerHTML = '<span style="color:var(--yellow)">Testing...</span>';
    fetch('/api/test-assistant', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({assistant_id: assistantId})
    }).then(r => r.json()).then(d => {
      if (d.success) {
        statusEl.innerHTML = '<span style="color:var(--green)">&#10004; OK</span>';
      } else {
        statusEl.innerHTML = '<span style="color:var(--red)">&#10008; ' + (d.message||'').substring(0,50) + '</span>';
      }
    }).catch(() => {
      statusEl.innerHTML = '<span style="color:var(--red)">&#10008; Error</span>';
    });
  });
}

// Load settings on tab switch
document.addEventListener('DOMContentLoaded', () => { setTimeout(loadSettings, 500); });

// ── File Upload Handlers ──
function handlePromptUpload(input) {
  const file = input.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (e) => {
    document.getElementById('mgrPrompt').value = e.target.result;
    document.getElementById('mgrPromptFileStatus').textContent = 'Loaded: ' + file.name + ' (' + e.target.result.length + ' chars)';
  };
  reader.readAsText(file);
}

function handleContextUpload(input) {
  const files = input.files;
  if (!files.length) return;
  let combined = '';
  let loaded = 0;
  Array.from(files).forEach(file => {
    const reader = new FileReader();
    reader.onload = (e) => {
      combined += '\\n\\n--- ' + file.name + ' ---\\n' + e.target.result;
      loaded++;
      if (loaded === files.length) {
        document.getElementById('mgrContext').value = combined.trim();
        document.getElementById('mgrContextFileStatus').textContent = loaded + ' file(s) loaded (' + combined.length + ' chars)';
      }
    };
    reader.readAsText(file);
  });
}

function handleTestsUpload(input) {
  const file = input.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (e) => {
    try {
      const tests = JSON.parse(e.target.result);
      document.getElementById('mgrTests').value = JSON.stringify(tests, null, 2);
      document.getElementById('mgrTestsFileStatus').textContent = 'Loaded: ' + file.name + ' (' + (Array.isArray(tests) ? tests.length + ' tests' : 'parsed') + ')';
    } catch(err) {
      document.getElementById('mgrTestsFileStatus').textContent = 'Error: ' + err.message;
    }
  };
  reader.readAsText(file);
}

// ── Manage Roles ──
let _editingRole = null;

function loadVersionHistory(slug) {
  fetch('/api/role/versions/' + slug).then(r => r.json()).then(versions => {
    const section = document.getElementById('versionSection');
    const list = document.getElementById('versionList');
    if (!versions.length) { section.style.display = 'none'; return; }
    section.style.display = 'block';
    list.innerHTML = `<table class="history-table" style="font-size:0.8rem">
      <thead><tr><th>#</th><th>Timestamp</th><th>Version</th><th>Change Note</th><th>Prompt</th><th>Tests</th><th>Context</th><th>Actions</th></tr></thead>
      <tbody>${versions.map(v => `<tr>
        <td>${v.id}</td>
        <td style="white-space:nowrap">${(v.timestamp||'').substring(0,10)} ${(v.timestamp||'').substring(11,16)}</td>
        <td>${v.version || '-'}</td>
        <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${v.change_note||''}">${v.change_note || '-'}</td>
        <td>${v.prompt_len ? v.prompt_len + ' chars <span style="color:var(--text2);font-size:0.7rem">(' + v.prompt_hash + ')</span>' : '-'}</td>
        <td>${v.test_len ? v.test_len + ' chars' : '-'}</td>
        <td>${v.context_len ? v.context_len + ' chars' : '-'}</td>
        <td>
          <button class="btn" style="background:var(--surface2);color:var(--text);font-size:0.7rem;padding:0.2rem 0.4rem" onclick="viewVersion(${v.id})">View</button>
          <button class="btn" style="background:var(--surface2);color:var(--text);font-size:0.7rem;padding:0.2rem 0.4rem" onclick="restoreVersion(${v.id})">Restore</button>
          ${v.id > 1 ? '<button class="btn" style="background:var(--purple);color:#fff;font-size:0.7rem;padding:0.2rem 0.4rem" onclick="diffVersions(' + v.id + ')">Diff with prev</button>' : ''}
        </td>
      </tr>`).join('')}</tbody></table>`;
  });
}

function viewVersion(versionId) {
  fetch('/api/role/version/' + versionId).then(r => r.json()).then(v => {
    const diff = document.getElementById('versionDiff');
    diff.style.display = 'block';
    document.getElementById('versionDiffContent').innerHTML = `
      <div style="background:var(--bg);border-radius:8px;padding:1rem">
        <div style="margin-bottom:0.5rem"><strong>Version:</strong> ${v.version || '-'} | <strong>Date:</strong> ${(v.timestamp||'').substring(0,16)} | <strong>Note:</strong> ${v.change_note || '-'}</div>
        <details open><summary style="cursor:pointer;color:var(--accent);font-size:0.85rem">System Prompt (${(v.prompt_text||'').length} chars)</summary>
          <pre style="background:var(--surface);padding:0.75rem;border-radius:6px;margin-top:0.3rem;font-size:0.75rem;max-height:300px;overflow-y:auto;white-space:pre-wrap">${(v.prompt_text||'(empty)').replace(/</g,'&lt;')}</pre>
        </details>
        <details><summary style="cursor:pointer;color:var(--accent);font-size:0.85rem;margin-top:0.5rem">Context (${(v.context_text||'').length} chars)</summary>
          <pre style="background:var(--surface);padding:0.75rem;border-radius:6px;margin-top:0.3rem;font-size:0.75rem;max-height:200px;overflow-y:auto;white-space:pre-wrap">${(v.context_text||'(empty)').replace(/</g,'&lt;')}</pre>
        </details>
      </div>`;
  });
}

function restoreVersion(versionId) {
  if (!confirm('Restore this version? This will overwrite the current prompt and context.')) return;
  fetch('/api/role/version/' + versionId).then(r => r.json()).then(v => {
    document.getElementById('mgrPrompt').value = v.prompt_text || '';
    document.getElementById('mgrContext').value = v.context_text || '';
    if (v.test_cases) document.getElementById('mgrTests').value = v.test_cases;
    showToast('Version loaded into form. Click "Update Role" to save.', 'success');
  });
}

function diffVersions(versionId) {
  fetch('/api/role/versions/' + _editingRole).then(r => r.json()).then(versions => {
    const idx = versions.findIndex(v => v.id === versionId);
    if (idx < 0 || idx >= versions.length - 1) { showToast('No previous version to compare', 'warning'); return; }
    const currentId = versionId;
    const prevId = versions[idx + 1].id;

    Promise.all([
      fetch('/api/role/version/' + prevId).then(r => r.json()),
      fetch('/api/role/version/' + currentId).then(r => r.json()),
    ]).then(([older, newer]) => {
      const diff = document.getElementById('versionDiff');
      diff.style.display = 'block';

      const oldLines = (older.prompt_text||'').split('\\n');
      const newLines = (newer.prompt_text||'').split('\\n');
      let diffHtml = '';
      const maxLen = Math.max(oldLines.length, newLines.length);
      for (let i = 0; i < maxLen; i++) {
        const o = oldLines[i] || '';
        const n = newLines[i] || '';
        if (o === n) {
          diffHtml += `<div style="font-size:0.75rem;color:var(--text2);padding:0 0.5rem">${n.replace(/</g,'&lt;') || '&nbsp;'}</div>`;
        } else if (!o && n) {
          diffHtml += `<div style="font-size:0.75rem;background:rgba(34,197,94,0.15);color:var(--green);padding:0 0.5rem">+ ${n.replace(/</g,'&lt;')}</div>`;
        } else if (o && !n) {
          diffHtml += `<div style="font-size:0.75rem;background:rgba(239,68,68,0.15);color:var(--red);padding:0 0.5rem">- ${o.replace(/</g,'&lt;')}</div>`;
        } else {
          diffHtml += `<div style="font-size:0.75rem;background:rgba(239,68,68,0.1);color:var(--red);padding:0 0.5rem">- ${o.replace(/</g,'&lt;')}</div>`;
          diffHtml += `<div style="font-size:0.75rem;background:rgba(34,197,94,0.1);color:var(--green);padding:0 0.5rem">+ ${n.replace(/</g,'&lt;')}</div>`;
        }
      }

      document.getElementById('versionDiffContent').innerHTML = `
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-bottom:0.5rem">
          <div style="font-size:0.85rem;color:var(--red);font-weight:600">Previous: v${older.id} (${(older.timestamp||'').substring(0,10)}) ${older.change_note ? '— ' + older.change_note : ''}</div>
          <div style="font-size:0.85rem;color:var(--green);font-weight:600">Current: v${newer.id} (${(newer.timestamp||'').substring(0,10)}) ${newer.change_note ? '— ' + newer.change_note : ''}</div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem">
          <div style="background:var(--bg);border-radius:8px;padding:0.75rem;max-height:500px;overflow-y:auto;font-family:monospace;font-size:0.75rem;white-space:pre-wrap;border:1px solid rgba(239,68,68,0.3)">${(older.prompt_text||'(empty)').replace(/</g,'&lt;')}</div>
          <div style="background:var(--bg);border-radius:8px;padding:0.75rem;max-height:500px;overflow-y:auto;font-family:monospace;font-size:0.75rem;white-space:pre-wrap;border:1px solid rgba(34,197,94,0.3)">${(newer.prompt_text||'(empty)').replace(/</g,'&lt;')}</div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-top:0.75rem">
          <div>
            <div style="font-size:0.8rem;color:var(--text2);margin-bottom:0.3rem">Previous Context (${(older.context_text||'').length} chars)</div>
            <div style="background:var(--bg);border-radius:8px;padding:0.75rem;max-height:200px;overflow-y:auto;font-size:0.75rem;white-space:pre-wrap;border:1px solid rgba(239,68,68,0.2)">${(older.context_text||'(empty)').replace(/</g,'&lt;').substring(0,3000)}</div>
          </div>
          <div>
            <div style="font-size:0.8rem;color:var(--text2);margin-bottom:0.3rem">Current Context (${(newer.context_text||'').length} chars)</div>
            <div style="background:var(--bg);border-radius:8px;padding:0.75rem;max-height:200px;overflow-y:auto;font-size:0.75rem;white-space:pre-wrap;border:1px solid rgba(34,197,94,0.2)">${(newer.context_text||'(none)').replace(/</g,'&lt;').substring(0,3000)}</div>
          </div>
        </div>`;
    });
  });
}

function loadRole(slug) {
  fetch('/api/role/' + slug).then(r => r.json()).then(data => {
    if (data.error) { showToast(data.error, 'error'); return; }
    _editingRole = slug;
    document.getElementById('mgrSlug').value = slug;
    document.getElementById('mgrSlug').disabled = true;
    document.getElementById('mgrName').value = data.meta.name || '';
    document.getElementById('mgrDomain').value = data.meta.domain || '';
    document.getElementById('mgrPrompt').value = data.prompt || '';
    document.getElementById('mgrContext').value = data.context_text || '';
    document.getElementById('mgrTests').value = JSON.stringify(data.tests, null, 2);
    document.getElementById('roleFormTitle').textContent = 'Edit Role: ' + slug;
    document.getElementById('mgrCreateBtn').style.display = 'none';
    document.getElementById('mgrUpdateBtn').style.display = 'inline-block';
    document.getElementById('changeNoteRow').style.display = 'block';
    document.getElementById('mgrChangeNote').value = '';
    loadVersionHistory(slug);
  });
}

function clearRoleForm() {
  _editingRole = null;
  document.getElementById('mgrSlug').value = '';
  document.getElementById('mgrSlug').disabled = false;
  document.getElementById('mgrName').value = '';
  document.getElementById('mgrDomain').value = '';
  document.getElementById('mgrPrompt').value = '';
  document.getElementById('mgrContext').value = '';
  document.getElementById('mgrTests').value = '';
  document.getElementById('roleFormTitle').textContent = 'Create New Role';
  document.getElementById('mgrCreateBtn').style.display = 'inline-block';
  document.getElementById('mgrUpdateBtn').style.display = 'none';
  document.getElementById('changeNoteRow').style.display = 'none';
  document.getElementById('versionSection').style.display = 'none';
  document.getElementById('versionDiff').style.display = 'none';
  document.getElementById('mgrResult').classList.remove('active');
}

function createRole() {
  const slug = document.getElementById('mgrSlug').value.trim();
  const name = document.getElementById('mgrName').value.trim();
  const domain = document.getElementById('mgrDomain').value.trim();
  const prompt = document.getElementById('mgrPrompt').value.trim();
  const context = document.getElementById('mgrContext').value.trim();
  let tests = [];
  try {
    const raw = document.getElementById('mgrTests').value.trim();
    if (raw) tests = JSON.parse(raw);
  } catch(e) { showToast('Invalid test JSON: ' + e.message, 'error'); return; }

  if (!slug || !name || !prompt) { showToast('Slug, Name, and System Prompt are required.', 'warning'); return; }

  fetch('/api/role/create', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({slug, name, domain, prompt, context, tests})
  }).then(r => r.json()).then(d => {
    const flash = document.getElementById('mgrResult');
    if (d.success) {
      flash.className = 'result-flash active success';
      flash.innerHTML = '<strong>Role created!</strong> Restart the dashboard to see it in dropdowns. Files: ' + JSON.stringify(d.files_created);
    } else {
      flash.className = 'result-flash active error';
      flash.innerHTML = '<strong>Error:</strong> ' + d.error;
    }
  });
}

function updateRole() {
  if (!_editingRole) return;
  const prompt = document.getElementById('mgrPrompt').value.trim();
  const context = document.getElementById('mgrContext').value.trim();
  const change_note = document.getElementById('mgrChangeNote').value.trim();

  if (!change_note) { showToast('Please add a change note describing what you changed.', 'warning'); return; }

  fetch('/api/role/update', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({slug: _editingRole, prompt, context, change_note})
  }).then(r => r.json()).then(d => {
    const flash = document.getElementById('mgrResult');
    if (d.success) {
      flash.className = 'result-flash active success';
      flash.innerHTML = '<strong>Role updated!</strong> Changes: ' + JSON.stringify(d.updates) + '. Version saved. Restart dashboard to reload prompt changes.';
      loadVersionHistory(_editingRole);
      document.getElementById('mgrChangeNote').value = '';
    } else {
      flash.className = 'result-flash active error';
      flash.innerHTML = '<strong>Error:</strong> ' + (d.error || 'Unknown error');
    }
  });
}

function runCalibration() {
  const role = document.getElementById('calRole').value;
  document.getElementById('btnCalibrate').disabled = true;
  showProgress('cal');

  fetch('/api/calibrate', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({role})
  }).then(r => r.json()).then(d => pollJob(d.job_id, 'cal'));
}

function improvePrompt() {
  const role = document.getElementById('evalRole').value;
  showProgress('eval');
  document.getElementById('evalBar').style.width = '30%';
  document.getElementById('evalText').textContent = 'Analyzing weaknesses and generating improved prompt...';

  fetch('/api/improve-prompt', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({role})
  }).then(r => r.json()).then(d => {
    const iv = setInterval(() => {
      fetch('/api/status/' + d.job_id).then(r => r.json()).then(job => {
        document.getElementById('evalText').textContent = job.current_test || 'Working...';
        if (job.status === 'done' || job.status === 'error') {
          clearInterval(iv);
          document.getElementById('evalProgress').classList.remove('active');
          document.getElementById('btnEval').disabled = false;
          showImprovedPrompt(job);
        }
      });
    }, 2000);
  });
}

function showImprovedPrompt(job) {
  const flash = document.getElementById('evalResult');
  flash.classList.add('active');

  if (job.status === 'error') {
    flash.className = 'result-flash active error';
    flash.innerHTML = `<strong>Error:</strong> ${job.result.error}`;
    return;
  }

  const r = job.result;
  flash.className = 'result-flash active success';
  flash.innerHTML = `
    <div>
      <h3 style="color:var(--purple);margin-bottom:0.5rem">Auto-Improved System Prompt</h3>
      <p style="color:var(--text2);font-size:0.85rem;margin-bottom:0.75rem">
        Based on evaluation score of ${r.original_score}% (${r.original_grade}), ${r.weak_areas_addressed.length} weak areas addressed.
      </p>
      <div style="margin-bottom:0.75rem">
        <strong style="font-size:0.85rem">Changes Made:</strong>
        <div style="background:var(--bg);padding:0.75rem;border-radius:6px;margin-top:0.3rem;font-size:0.8rem;white-space:pre-wrap;max-height:150px;overflow-y:auto">${r.changes_summary}</div>
      </div>
      <details>
        <summary style="cursor:pointer;color:var(--accent);font-size:0.85rem;margin-bottom:0.5rem">View improved prompt (${r.improved_prompt.length} chars)</summary>
        <textarea id="improvedPromptText" style="width:100%;min-height:200px;max-height:400px;background:var(--bg);color:var(--text);border:1px solid var(--surface2);border-radius:6px;padding:0.75rem;font-size:0.8rem;font-family:monospace;resize:vertical">${r.improved_prompt.replace(/</g,'&lt;')}</textarea>
      </details>
      <div style="display:flex;gap:0.5rem;margin-top:0.75rem">
        <button class="btn btn-primary" onclick="evalWithImprovedPrompt()">Evaluate This Prompt</button>
        <button class="btn" style="background:var(--surface2);color:var(--text)" onclick="copyImprovedPrompt()">Copy to Clipboard</button>
      </div>
    </div>`;
}

function evalWithImprovedPrompt() {
  const prompt = document.getElementById('improvedPromptText').value;
  document.getElementById('evalPrompt').value = 'custom';
  document.getElementById('evalCustomPrompt').style.display = 'block';
  document.getElementById('evalCustomPrompt').value = prompt;
  updateHeaderTarget();
  runEval();
}

function copyImprovedPrompt() {
  const text = document.getElementById('improvedPromptText').value;
  navigator.clipboard.writeText(text).then(() => showToast('Copied to clipboard!', 'success'));
}

function addManualTestCase() {
  const id = document.getElementById('manualId').value.trim();
  const category = document.getElementById('manualCategory').value.trim();
  const question = document.getElementById('manualQuestion').value.trim();
  const criteriaText = document.getElementById('manualCriteria').value.trim();
  const contextText = document.getElementById('manualContext').value.trim();
  const weight = parseInt(document.getElementById('manualWeight').value);

  if (!id || !question || !criteriaText) {
    showToast('Please fill in at least Test ID, Question, and Criteria.', 'warning');
    return;
  }

  const criteria = criteriaText.split('\n').map(c => c.trim()).filter(c => c).slice(0, 5);
  const context = contextText ? contextText.split('\n').map(c => c.trim()).filter(c => c) : undefined;

  const tc = { id, category: category || 'General', question, criteria, weight, _generated: false, _needs_review: false };
  if (context && context.length) tc.context = context;

  _generatedTests.push(tc);

  document.getElementById('genTestCases').style.display = 'block';
  document.getElementById('genTestCount').textContent = '(' + _generatedTests.length + ')';

  const list = document.getElementById('genTestList');
  list.innerHTML += `
    <div style="background:var(--bg);border-radius:8px;padding:1rem;margin-bottom:0.5rem;border-left:3px solid var(--green)">
      <div style="display:flex;gap:0.75rem;align-items:center;margin-bottom:0.5rem">
        <span style="font-weight:700;color:var(--green);font-family:monospace">${tc.id}</span>
        <span style="background:var(--surface2);padding:0.1rem 0.5rem;border-radius:4px;font-size:0.75rem">${tc.category}</span>
        <span style="color:var(--text2);font-size:0.75rem">${tc.criteria.length} criteria | weight: ${tc.weight}x</span>
        <span style="background:var(--green);color:#000;padding:0.1rem 0.4rem;border-radius:4px;font-size:0.65rem;font-weight:600">MANUAL</span>
      </div>
      <div style="font-size:0.9rem"><strong>Q:</strong> ${tc.question}</div>
    </div>`;

  document.getElementById('manualId').value = '';
  document.getElementById('manualQuestion').value = '';
  document.getElementById('manualCriteria').value = '';
  document.getElementById('manualContext').value = '';
}

function downloadGenerated() {
  if (!_generatedTests.length) return;
  const blob = new Blob([JSON.stringify(_generatedTests, null, 2)], {type: 'application/json'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `generated_tests_${new Date().toISOString().slice(0,10)}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

function saveAsTestSuite() {
  if (!_generatedTests.length) return;
  const role = document.getElementById('genRole').value;
  fetch('/api/save-test-suite', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({role, test_cases: _generatedTests, merge: false})
  }).then(r => r.json()).then(d => {
    if (d.success) {
      showToast('Test suite saved! Restart dashboard to see it in dropdowns.', 'success');
    } else {
      showToast(d.error, 'error');
    }
  });
}

function runEvalOnGenerated() {
  if (!_generatedTests.length) return;
  const role = document.getElementById('genRole').value;
  showProgress('gen');
  document.getElementById('genBar').style.width = '0%';
  document.getElementById('genText').textContent = 'Running evaluation on generated tests...';

  fetch('/api/eval-generated', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({role, test_cases: _generatedTests})
  }).then(r => r.json()).then(d => pollJob(d.job_id, 'gen'));
}

function runRedTeam() {
  const role = document.getElementById('rtRole').value;
  const model = getModel('rtModel');
  const prompt = getPromptValue('rtPrompt', 'rtCustomPrompt');
  document.getElementById('btnRedTeam').disabled = true;
  showProgress('rt');
  document.getElementById('rtBar').style.width = '30%';

  fetch('/api/redteam', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({role, model, prompt_source: prompt})
  }).then(r => r.json()).then(d => pollJob(d.job_id, 'rt'));
}

function runComparison() {
  const role = document.getElementById('cmpRole').value;
  document.getElementById('btnCompare').disabled = true;
  showProgress('cmp');

  fetch('/api/run', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      role, run_type: 'comparison',
      run_a: { model: getModel('cmpModelA'), prompt_source: getPromptValue('cmpPromptA', 'cmpCustomPromptA') },
      run_b: { model: getModel('cmpModelB'), prompt_source: getPromptValue('cmpPromptB', 'cmpCustomPromptB') },
    })
  }).then(r => r.json()).then(d => pollJob(d.job_id, 'cmp'));
}

function showProgress(prefix) {
  document.getElementById(prefix + 'Progress').classList.add('active');
  document.getElementById(prefix + 'Result').classList.remove('active');
  document.getElementById(prefix + 'Bar').style.width = '0%';
  const textEl = document.getElementById(prefix + 'Text');
  if (textEl) textEl.innerHTML = '<span class="spinner"></span> Starting...';
}

function pollJob(jobId, prefix) {
  const iv = setInterval(() => {
    fetch('/api/status/' + jobId).then(r => r.json()).then(job => {
      if (job.total > 0) {
        const pct = Math.round((job.progress / job.total) * 100);
        document.getElementById(prefix + 'Bar').style.width = pct + '%';
        document.getElementById(prefix + 'Text').innerHTML =
          `<span class="spinner"></span> ${job.current_test} (${job.progress}/${job.total})`;
      }
      if (job.status === 'done' || job.status === 'error') {
        clearInterval(iv);
        document.getElementById('btnEval').disabled = false;
        document.getElementById('btnCompare').disabled = false;
        document.getElementById(prefix + 'Progress').classList.remove('active');
        showResult(job, prefix);
        refreshHistory();
      }
    });
  }, 1500);
}

function showResult(job, prefix) {
  const flash = document.getElementById(prefix + 'Result');
  flash.classList.add('active');

  if (job.status === 'error') {
    flash.className = 'result-flash active error';
    flash.innerHTML = `<strong>Error:</strong> ${job.result.error}`;
    return;
  }

  flash.className = 'result-flash active success';
  const r = job.result;

  if (r.overall_accuracy !== undefined) {
    // Calibration result
    const accColor = r.overall_accuracy >= 80 ? 'var(--green)' : r.overall_accuracy >= 60 ? 'var(--yellow)' : 'var(--red)';
    const discColor = r.discrimination >= 0.5 ? 'var(--green)' : r.discrimination >= 0.3 ? 'var(--yellow)' : 'var(--red)';
    const bq = r.by_quality || {};

    let issuesHtml = '';
    if (r.consistency_issues && r.consistency_issues.length) {
      issuesHtml = '<div style="margin-top:0.75rem"><strong style="color:var(--red);font-size:0.85rem">Issues Found:</strong>' +
        r.consistency_issues.map(i => `<div style="background:var(--bg);padding:0.4rem 0.6rem;border-radius:4px;margin-top:0.3rem;font-size:0.8rem;border-left:3px solid var(--red)">${i}</div>`).join('') + '</div>';
    }

    let detailRows = (r.results || []).map(t => {
      const devColor = t.passed ? 'var(--green)' : 'var(--red)';
      return `<tr>
        <td style="font-family:monospace;color:var(--accent)">${t.test_id}</td>
        <td><span style="background:var(--surface2);padding:0.1rem 0.4rem;border-radius:3px;font-size:0.7rem">${t.quality}</span></td>
        <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${t.criterion}">${t.criterion}</td>
        <td style="text-align:center">${t.expected.toFixed(2)}</td>
        <td style="text-align:center;font-weight:600">${t.geval.toFixed(2)}</td>
        <td style="text-align:center">${t.dag !== null ? t.dag.toFixed(2) : '-'}</td>
        <td style="text-align:center;color:${devColor};font-weight:600">${t.deviation.toFixed(2)}</td>
        <td style="text-align:center">${t.passed ? '<span style="color:var(--green)">PASS</span>' : '<span style="color:var(--red)">FAIL</span>'}</td>
      </tr>`;
    }).join('');

    flash.innerHTML = `
      <div>
        <h3 style="color:var(--accent);margin-bottom:0.75rem">Judge Calibration Results</h3>
        <div style="display:flex;gap:1.5rem;flex-wrap:wrap;margin-bottom:1rem">
          <div style="text-align:center">
            <div style="font-size:2rem;font-weight:800;color:${accColor}">${r.overall_accuracy}%</div>
            <div style="color:var(--text2);font-size:0.8rem">Accuracy</div>
            <div style="color:var(--text2);font-size:0.7rem">${r.passed}/${r.total_tests} within tolerance</div>
          </div>
          <div style="text-align:center">
            <div style="font-size:2rem;font-weight:800;color:${discColor}">${r.discrimination}</div>
            <div style="color:var(--text2);font-size:0.8rem">Discrimination</div>
            <div style="color:var(--text2);font-size:0.7rem">Gap between excellent & poor</div>
          </div>
          <div style="text-align:center">
            <div style="font-size:2rem;font-weight:800">${r.avg_deviation}</div>
            <div style="color:var(--text2);font-size:0.8rem">Avg Deviation</div>
            <div style="color:var(--text2);font-size:0.7rem">From expected scores</div>
          </div>
          <div style="font-size:0.85rem;color:var(--text2)">
            <strong>Avg scores by quality:</strong><br>
            Excellent: ${(bq.excellent||{}).avg_geval||0}<br>
            Adequate: ${(bq.adequate||{}).avg_geval||0}<br>
            Poor: ${(bq.poor||{}).avg_geval||0}<br>
            Misleading: ${(bq.misleading||{}).avg_geval||0}
          </div>
        </div>
        ${issuesHtml}
        <details style="margin-top:0.75rem">
          <summary style="cursor:pointer;color:var(--accent);font-size:0.85rem">View all ${r.total_tests} test results</summary>
          <div style="overflow-x:auto;margin-top:0.5rem">
            <table class="history-table" style="font-size:0.8rem">
              <thead><tr><th>ID</th><th>Quality</th><th>Criterion</th><th>Expected</th><th>GEval</th><th>DAG</th><th>Deviation</th><th>Result</th></tr></thead>
              <tbody>${detailRows}</tbody>
            </table>
          </div>
        </details>
      </div>`;
  } else if (r.test_cases && r.count !== undefined && !r.total_attacks) {
    // Generate result
    _generatedTests = r.test_cases;
    flash.innerHTML = `<strong style="color:var(--green)">Generated ${r.count} test cases!</strong> Review below and download as JSON.`;
    const container = document.getElementById('genTestCases');
    container.style.display = 'block';
    document.getElementById('genTestCount').textContent = `(${r.count})`;
    const list = document.getElementById('genTestList');
    list.innerHTML = r.test_cases.map(tc => `
      <div style="background:var(--bg);border-radius:8px;padding:1rem;margin-bottom:0.5rem;border-left:3px solid var(--accent)">
        <div style="display:flex;gap:0.75rem;align-items:center;margin-bottom:0.5rem">
          <span style="font-weight:700;color:var(--accent);font-family:monospace">${tc.id}</span>
          <span style="background:var(--surface2);padding:0.1rem 0.5rem;border-radius:4px;font-size:0.75rem">${tc.category}</span>
          <span style="color:var(--text2);font-size:0.75rem">${tc.criteria.length} criteria | weight: ${tc.weight}x</span>
          ${tc._needs_review ? '<span style="background:var(--orange);color:#000;padding:0.1rem 0.4rem;border-radius:4px;font-size:0.65rem;font-weight:600">NEEDS REVIEW</span>' : ''}
        </div>
        <div style="font-size:0.9rem;margin-bottom:0.5rem"><strong>Q:</strong> ${tc.question}</div>
        <details>
          <summary style="cursor:pointer;color:var(--accent);font-size:0.8rem">View criteria${tc._expected_output ? ' & expected output' : ''}</summary>
          <ul style="margin:0.5rem 0 0 1rem;font-size:0.8rem;color:var(--text2)">
            ${tc.criteria.map(c => '<li>' + c + '</li>').join('')}
          </ul>
          ${tc._expected_output ? '<div style="background:var(--surface);padding:0.5rem;border-radius:6px;margin-top:0.5rem;font-size:0.8rem;max-height:200px;overflow-y:auto"><strong>Expected:</strong> ' + tc._expected_output.substring(0,500) + '</div>' : ''}
        </details>
      </div>`).join('');
  } else if (r.total_attacks !== undefined) {
    // Red team result
    const color = r.overall_pass_rate >= 90 ? 'var(--green)' : r.overall_pass_rate >= 70 ? 'var(--yellow)' : 'var(--red)';
    const vulns = Object.entries(r.overview || {}).map(([k,v]) =>
      `<span style="margin-right:1rem"><strong>${k}:</strong> <span style="color:${v.pass_rate>=90?'var(--green)':v.pass_rate>=70?'var(--yellow)':'var(--red)'}">${v.pass_rate}%</span> (${v.passed}/${v.total})</span>`
    ).join('');
    flash.innerHTML = `
      <div style="display:flex;align-items:center;gap:2rem;flex-wrap:wrap">
        <div style="text-align:center">
          <div style="font-size:2.5rem;font-weight:800;color:${color}">${r.overall_pass_rate}%</div>
          <div style="color:var(--text2)">Pass Rate</div>
          <div style="color:var(--text2);font-size:0.8rem">${r.total_attacks} attacks</div>
        </div>
        <div style="font-size:0.9rem">${vulns}</div>
        <a href="${r.report_url}" target="_blank" class="result-link">View Full Report &#8594;</a>
      </div>`;
  } else if (r.delta !== undefined) {
    const color = r.delta > 0 ? 'var(--green)' : 'var(--red)';
    flash.innerHTML = `
      <div style="display:flex;align-items:center;gap:2rem;flex-wrap:wrap">
        <div style="text-align:center">
          <div style="color:var(--orange);font-size:0.8rem;font-weight:600">Run A</div>
          <div style="color:var(--text2);font-size:0.7rem">${r.a_label}</div>
          <div class="result-grade" style="color:${r.a_score>=85?'var(--green)':r.a_score>=70?'var(--yellow)':'var(--red)'}">${r.a_grade}</div>
          <div>${r.a_score}%</div>
        </div>
        <div style="font-size:2rem;color:${color}">&#10132; ${r.delta > 0 ? '+' : ''}${r.delta}%</div>
        <div style="text-align:center">
          <div style="color:var(--accent);font-size:0.8rem;font-weight:600">Run B</div>
          <div style="color:var(--text2);font-size:0.7rem">${r.b_label}</div>
          <div class="result-grade" style="color:${r.b_score>=85?'var(--green)':r.b_score>=70?'var(--yellow)':'var(--red)'}">${r.b_grade}</div>
          <div>${r.b_score}%</div>
        </div>
        <a href="${r.report_url}" target="_blank" class="result-link">View Full Report &#8594;</a>
      </div>`;
  } else {
    const gc = r.grade.startsWith('A') ? 'var(--green)' : r.grade.startsWith('B') ? 'var(--yellow)' : 'var(--red)';
    const perf = r.perf || {};
    flash.innerHTML = `
      <div style="display:flex;align-items:center;gap:2rem;flex-wrap:wrap">
        <div style="text-align:center">
          <div class="result-grade" style="color:${gc}">${r.grade}</div>
          <div>${r.score}%${r.num_runs > 1 ? ' <span style="color:var(--text2);font-size:0.75rem">(avg of ' + r.num_runs + ' runs)</span>' : ''}</div>
        </div>
        ${perf.available ? `<div style="color:var(--text2);font-size:0.85rem">
          Latency: ${perf.avg_latency}s avg | ${perf.p95_latency}s p95<br>
          Tokens: ${(perf.total_tokens||0).toLocaleString()} | Cost: $${(perf.estimated_cost_usd||0).toFixed(4)}
        </div>` : ''}
        <a href="${r.report_url}" target="_blank" class="result-link">View Full Report &#8594;</a>
        <button class="btn" style="background:var(--purple);color:#fff;font-size:0.8rem;padding:0.4rem 0.8rem" onclick="improvePrompt()">Auto-Improve Prompt</button>
      </div>`;
  }
}

function refreshHistory() {
  fetch('/api/history').then(r => r.json()).then(runs => {
    const evalRuns = runs.filter(r => r.run_type === 'evaluation');
    const evalEl = document.getElementById('evalHistory');
    if (evalEl) evalEl.innerHTML = evalRuns.length ? buildHistoryTable(evalRuns) : '<div class="empty-state">No evaluations yet.</div>';

    const cmpRuns = runs.filter(r => r.run_type && r.run_type.startsWith('comparison'));
    const cmpEl = document.getElementById('cmpHistory');
    if (cmpEl) cmpEl.innerHTML = cmpRuns.length ? buildComparisonTable(cmpRuns) : '<div class="empty-state">No comparisons yet.</div>';

    const genRuns = runs.filter(r => r.run_type === 'eval_generated');
    const genEl = document.getElementById('genHistory');
    if (genEl) genEl.innerHTML = genRuns.length ? buildGenEvalTable(genRuns) : '<div class="empty-state">No generated test evaluations yet.</div>';

    const rtRuns = runs.filter(r => r.run_type === 'red_team');
    const rtEl = document.getElementById('rtHistory');
    if (rtEl) rtEl.innerHTML = rtRuns.length ? buildRedTeamTable(rtRuns) : '<div class="empty-state">No red team runs yet.</div>';

    fetch('/api/calibration-history').then(r => r.json()).then(calRuns => {
      const calEl = document.getElementById('calHistory');
      if (calEl) calEl.innerHTML = calRuns.length ? buildCalibrationTable(calRuns) : '<div class="empty-state">No calibration runs yet.</div>';
    }).catch(() => {});
  });
}

function buildHistoryTable(runs) {
  return `<table class="history-table" style="font-size:0.8rem">
    <thead><tr>
      <th>#</th><th>Timestamp</th><th>Role</th><th>Model</th><th>Judge</th>
      <th>GEval</th><th>DAG</th><th>Combined</th><th>Grade</th>
      <th>Latency</th><th>Cost</th><th>Report</th>
    </tr></thead>
    <tbody>${runs.map(run => `<tr>
      <td>${run.id}</td>
      <td style="white-space:nowrap">${(run.timestamp||'').substring(0,10)} ${(run.timestamp||'').substring(11,16)}</td>
      <td style="max-width:100px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${run.role}">${run.role}</td>
      <td>${run.model || 'demo'}</td>
      <td>${run.judge_model || '-'}</td>
      <td>${run.overall_pct}%</td>
      <td>${run.dag_pct ? run.dag_pct.toFixed(1) + '%' : '-'}</td>
      <td style="font-weight:700">${run.consolidated_pct ? run.consolidated_pct.toFixed(1) : run.overall_pct}%</td>
      <td><span class="grade-badge grade-${((run.consolidated_grade||run.grade||'d')[0]).toLowerCase()}">${run.consolidated_grade||run.grade}</span></td>
      <td>${run.avg_latency ? run.avg_latency.toFixed(1) + 's' : '-'}</td>
      <td>${run.estimated_cost ? '$' + run.estimated_cost.toFixed(4) : '-'}</td>
      <td>${run.report_path ? '<a href="/reports/' + run.report_path.split(/[/\\\\]/).pop() + '" target="_blank">View</a>' : '-'}</td>
    </tr>`).join('')}</tbody></table>`;
}

function buildComparisonTable(runs) {
  const pairs = [];
  for (let i = 0; i < runs.length; i += 2) {
    const a = runs[i+1];
    const b = runs[i];
    if (a && b) pairs.push({a, b});
    else if (a) pairs.push({a, b: null});
  }

  return `<table class="history-table" style="font-size:0.8rem">
    <thead><tr>
      <th>Timestamp</th><th>Role</th>
      <th>Run A</th><th>A Score</th><th>A Grade</th>
      <th>Run B</th><th>B Score</th><th>B Grade</th>
      <th>Delta</th><th>Report</th>
    </tr></thead>
    <tbody>${pairs.map(p => {
      const a = p.a || {};
      const b = p.b || {};
      const aScore = a.consolidated_pct || a.overall_pct || 0;
      const bScore = b.consolidated_pct || b.overall_pct || 0;
      const delta = (bScore - aScore).toFixed(1);
      const deltaColor = delta > 0 ? 'var(--green)' : delta < 0 ? 'var(--red)' : 'var(--text2)';
      return `<tr>
        <td style="white-space:nowrap">${(a.timestamp||b.timestamp||'').substring(0,10)} ${(a.timestamp||b.timestamp||'').substring(11,16)}</td>
        <td>${a.role || b.role}</td>
        <td style="font-size:0.75rem">${a.notes || a.model || '-'}</td>
        <td>${aScore}%</td>
        <td><span class="grade-badge grade-${((a.consolidated_grade||a.grade||'d')[0]).toLowerCase()}">${a.consolidated_grade||a.grade||'-'}</span></td>
        <td style="font-size:0.75rem">${b.notes || b.model || '-'}</td>
        <td>${bScore}%</td>
        <td><span class="grade-badge grade-${((b.consolidated_grade||b.grade||'d')[0]).toLowerCase()}">${b.consolidated_grade||b.grade||'-'}</span></td>
        <td style="color:${deltaColor};font-weight:700">${delta > 0 ? '+' : ''}${delta}%</td>
        <td>${(b.report_path||a.report_path) ? '<a href="/reports/' + (b.report_path||a.report_path).split(/[/\\\\]/).pop() + '" target="_blank">View</a>' : '-'}</td>
      </tr>`;
    }).join('')}</tbody></table>`;
}

function buildRedTeamTable(runs) {
  return `<table class="history-table" style="font-size:0.8rem">
    <thead><tr>
      <th>#</th><th>Timestamp</th><th>Role</th><th>Model</th>
      <th>Attacks</th><th>Pass Rate</th><th>Result</th><th>Report</th>
    </tr></thead>
    <tbody>${runs.map(run => {
      const pr = run.overall_pct || 0;
      const resultColor = pr >= 90 ? 'var(--green)' : pr >= 70 ? 'var(--yellow)' : 'var(--red)';
      return `<tr>
        <td>${run.id}</td>
        <td style="white-space:nowrap">${(run.timestamp||'').substring(0,10)} ${(run.timestamp||'').substring(11,16)}</td>
        <td>${run.role}</td>
        <td>${run.model || 'demo'}</td>
        <td>${run.num_tests || '-'}</td>
        <td style="font-weight:700;color:${resultColor}">${pr}%</td>
        <td><span class="grade-badge grade-${pr >= 90 ? 'a' : pr >= 70 ? 'b' : 'd'}">${pr >= 90 ? 'PASS' : pr >= 70 ? 'WARN' : 'FAIL'}</span></td>
        <td>${run.report_path ? '<a href="/reports/' + run.report_path.split(/[/\\\\]/).pop() + '" target="_blank">View</a>' : '-'}</td>
      </tr>`;
    }).join('')}</tbody></table>`;
}

function buildCalibrationTable(runs) {
  return `<table class="history-table" style="font-size:0.8rem">
    <thead><tr>
      <th>#</th><th>Timestamp</th><th>Judge Model</th>
      <th>Accuracy</th><th>Discrimination</th><th>Avg Dev</th>
      <th>Excellent</th><th>Adequate</th><th>Poor</th><th>Misleading</th>
      <th>Pass/Fail</th><th>Issues</th><th>Report</th>
    </tr></thead>
    <tbody>${runs.map(run => {
      const accColor = run.accuracy >= 80 ? 'var(--green)' : run.accuracy >= 60 ? 'var(--yellow)' : 'var(--red)';
      const discColor = run.discrimination >= 0.5 ? 'var(--green)' : run.discrimination >= 0.3 ? 'var(--yellow)' : 'var(--red)';
      return `<tr>
        <td>${run.id}</td>
        <td style="white-space:nowrap">${(run.timestamp||'').substring(0,10)} ${(run.timestamp||'').substring(11,16)}</td>
        <td>${run.judge_model || '-'}</td>
        <td style="font-weight:700;color:${accColor}">${run.accuracy}%</td>
        <td style="font-weight:700;color:${discColor}">${run.discrimination}</td>
        <td>${run.avg_deviation}</td>
        <td style="color:var(--green)">${run.avg_excellent}</td>
        <td style="color:var(--yellow)">${run.avg_adequate}</td>
        <td style="color:var(--red)">${run.avg_poor}</td>
        <td style="color:var(--orange)">${run.avg_misleading}</td>
        <td>${run.passed}/${run.total_tests}</td>
        <td style="color:${run.issues_count > 0 ? 'var(--red)' : 'var(--green)'}">${run.issues_count}</td>
        <td>${run.report_path ? '<a href="/reports/' + run.report_path.split(/[/\\\\]/).pop() + '" target="_blank">View</a>' : '-'}</td>
      </tr>`;
    }).join('')}</tbody></table>`;
}

function buildGenEvalTable(runs) {
  return `<table class="history-table" style="font-size:0.8rem">
    <thead><tr>
      <th>#</th><th>Timestamp</th><th>Role</th><th>Model</th>
      <th>Tests</th><th>GEval</th><th>DAG</th><th>Combined</th><th>Grade</th>
      <th>Notes</th><th>Report</th>
    </tr></thead>
    <tbody>${runs.map(run => `<tr>
      <td>${run.id}</td>
      <td style="white-space:nowrap">${(run.timestamp||'').substring(0,10)} ${(run.timestamp||'').substring(11,16)}</td>
      <td>${run.role}</td>
      <td>${run.model || 'demo'}</td>
      <td>${run.num_tests}</td>
      <td>${run.overall_pct}%</td>
      <td>${run.dag_pct ? run.dag_pct.toFixed(1) + '%' : '-'}</td>
      <td style="font-weight:700">${run.consolidated_pct ? run.consolidated_pct.toFixed(1) : run.overall_pct}%</td>
      <td><span class="grade-badge grade-${((run.consolidated_grade||run.grade||'d')[0]).toLowerCase()}">${run.consolidated_grade||run.grade}</span></td>
      <td style="font-size:0.75rem;color:var(--text2)">${run.notes || '-'}</td>
      <td>${run.report_path ? '<a href="/reports/' + run.report_path.split(/[/\\\\]/).pop() + '" target="_blank">View</a>' : '-'}</td>
    </tr>`).join('')}</tbody></table>`;
}

function exportCSV(runType) {
  fetch('/api/history').then(r => r.json()).then(runs => {
    let filtered = runs;
    if (runType) filtered = runs.filter(r => r.run_type && r.run_type.startsWith(runType));

    const headers = ['ID','Timestamp','Role','Model','Judge Model','GEval %','DAG %','Combined %','Grade','Tests','Criteria',
      'Avg Latency (s)','P95 Latency (s)','Total Tokens','Est Cost (USD)','Duration (s)','Type','Notes'];
    const rows = filtered.map(r => [
      r.id, r.timestamp, r.role, r.model||'demo', r.judge_model||'-',
      r.overall_pct, r.dag_pct||'', r.consolidated_pct||r.overall_pct, r.consolidated_grade||r.grade,
      r.num_tests, r.num_criteria, r.avg_latency||'', r.p95_latency||'',
      r.total_tokens||'', r.estimated_cost||'', r.total_elapsed||'',
      r.run_type, (r.notes||'').replace(/,/g,';')
    ]);

    let csv = headers.join(',') + '\n' + rows.map(r => r.join(',')).join('\n');
    const blob = new Blob([csv], {type: 'text/csv'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `eval_history_${new Date().toISOString().slice(0,10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  });
}
