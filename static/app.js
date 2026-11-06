// Switch Sentry Frontend Controller with Ziki-Inspired Multi-Stage Pipeline

let currentIncidentId = null;
let incidents = [];

document.addEventListener("DOMContentLoaded", () => {
  initUI();
  fetchSwitchStatus();
  fetchPresets();
  loadIncidents();
  loadMistakes();

  // Poll for live changes every 2.5s
  setInterval(() => {
    if (currentIncidentId) {
      loadIncidentDetail(currentIncidentId, false);
    }
  }, 2500);
});

function initUI() {
  // Tab switching
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-pane").forEach((p) => p.classList.remove("active"));

      btn.classList.add("active");
      const target = document.getElementById(btn.dataset.tab);
      if (target) target.classList.add("active");

      if (btn.dataset.tab === "tab-mistakes") {
        loadMistakes();
      }
    });
  });

  // Modal toggle
  const modal = document.getElementById("trigger-modal");
  document.getElementById("btn-open-trigger-modal").addEventListener("click", () => {
    modal.classList.add("open");
  });
  document.getElementById("btn-close-modal").addEventListener("click", () => {
    modal.classList.remove("open");
  });
}

async function fetchSwitchStatus() {
  try {
    const res = await fetch("/api/switch/status");
    const data = await res.json();
    const modeEl = document.getElementById("bridge-mode-text");
    if (data.live_connected) {
      modeEl.innerHTML = `Switch Core: <b>Live (Port 8000)</b> • <a href="http://localhost:8065" target="_blank" style="color:var(--accent-cyan); text-decoration:none;">Open Mattermost</a>`;
    } else {
      modeEl.textContent = `Switch Bridge: ${data.switch_bridge_mode}`;
    }
  } catch (e) {
    console.error("Failed to fetch switch status", e);
  }
}

async function fetchPresets() {
  try {
    const res = await fetch("/api/presets");
    const presets = await res.json();
    const list = document.getElementById("presets-list");
    list.innerHTML = "";

    presets.forEach((p) => {
      const item = document.createElement("div");
      item.className = "preset-item";
      item.innerHTML = `
        <div class="preset-top">
          <span class="severity-pill ${getSeverityClass(p.severity)}">${p.severity.split(" ")[0]}</span>
          <span class="preset-title">${escapeHtml(p.title)}</span>
        </div>
        <div class="preset-err">${escapeHtml(p.error_name)}</div>
      `;
      item.addEventListener("click", () => triggerPreset(p.id));
      list.appendChild(item);
    });
  } catch (e) {
    console.error("Failed to load presets", e);
  }
}

async function triggerPreset(presetId) {
  document.getElementById("trigger-modal").classList.remove("open");

  try {
    const res = await fetch("/api/incidents/trigger", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ preset_id: presetId }),
    });
    const incident = await res.json();
    await loadIncidents();
    loadIncidentDetail(incident.id, true);
  } catch (e) {
    alert("Error triggering incident: " + e.message);
  }
}

async function loadIncidents() {
  try {
    const res = await fetch("/api/incidents");
    incidents = await res.json();
    document.getElementById("incident-count").textContent = incidents.length;

    const list = document.getElementById("incident-list");
    list.innerHTML = "";

    if (incidents.length === 0) {
      list.innerHTML = `<div style="padding: 12px; color: var(--text-dim); font-size: 12px;">No active incidents. Click '+ Simulate Incident' to test.</div>`;
      return;
    }

    incidents.forEach((inc) => {
      const card = document.createElement("div");
      card.className = `incident-card ${inc.id === currentIncidentId ? "active" : ""}`;
      card.innerHTML = `
        <div class="incident-card-top">
          <span class="severity-pill ${getSeverityClass(inc.alert.severity)}">${inc.alert.severity.split(" ")[0]}</span>
          <span class="incident-card-meta">${escapeHtml(inc.stage.split(".")[1] || inc.stage)}</span>
        </div>
        <h4>${escapeHtml(inc.alert.title)}</h4>
        <div class="incident-card-meta">${escapeHtml(inc.alert.service)}</div>
      `;
      card.addEventListener("click", () => {
        document.querySelectorAll(".incident-card").forEach((c) => c.classList.remove("active"));
        card.classList.add("active");
        loadIncidentDetail(inc.id, true);
      });
      list.appendChild(card);
    });

    if (!currentIncidentId && incidents.length > 0) {
      loadIncidentDetail(incidents[0].id, true);
    }
  } catch (e) {
    console.error("Failed to load incidents", e);
  }
}

async function loadIncidentDetail(id, autoScroll = false) {
  try {
    const res = await fetch(`/api/incidents/${id}`);
    if (!res.json) return;
    const inc = await res.json();
    currentIncidentId = inc.id;

    // Header info
    document.getElementById("view-title").textContent = inc.alert.title;
    const sevEl = document.getElementById("view-severity");
    sevEl.textContent = inc.alert.severity.split(" ")[0];
    sevEl.className = `severity-pill ${getSeverityClass(inc.alert.severity)}`;

    const statEl = document.getElementById("view-status");
    statEl.textContent = inc.stage;
    statEl.className = `status-pill ${inc.stage.includes("6") ? "status-resolved" : ""}`;

    document.getElementById("meta-service").textContent = inc.alert.service;
    document.getElementById("meta-file").textContent = `${inc.alert.affected_file}:${inc.alert.line_number}`;
    document.getElementById("meta-commit").textContent = inc.alert.commit_hash;
    document.getElementById("room-channel-name").textContent = inc.switch_room_id;

    // Update Stepper
    updatePipelineStepper(inc.stage);

    // Telemetry HUD
    if (inc.telemetry) {
      document.getElementById("tel-trust").textContent = `${inc.telemetry.trust_score}%`;
      document.getElementById("tel-tokens").textContent = inc.telemetry.total_tokens.toLocaleString();
      document.getElementById("tel-latency").textContent = `${inc.telemetry.latency_ms}ms`;
      document.getElementById("tel-cost").textContent = `$${inc.telemetry.estimated_cost_usd.toFixed(4)}`;

      const auditList = document.getElementById("tel-audit-list");
      auditList.innerHTML = "";
      inc.telemetry.audit_logs.forEach((log) => {
        const li = document.createElement("li");
        li.textContent = log;
        auditList.appendChild(li);
      });
    }

    // Chat Timeline
    renderTimeline(inc.messages, autoScroll);

    // Code Diff & Test
    const diffEl = document.getElementById("diff-content");
    const testEl = document.getElementById("test-content");
    if (inc.patch) {
      diffEl.innerHTML = formatDiff(inc.patch.unified_diff);
      let testOutput = inc.patch.test_code + "\n\n" + inc.patch.test_output;
      if (inc.verdict) {
        testOutput += "\n\n" + inc.verdict.verdict_summary;
      }
      testEl.textContent = testOutput;
    } else {
      diffEl.textContent = "// No patch generated yet.";
      testEl.textContent = "// No tests executed yet.";
    }

    // RCA Doc
    const rcaEl = document.getElementById("rca-markdown");
    if (inc.rca_document) {
      rcaEl.innerHTML = formatMarkdown(inc.rca_document);
    } else {
      rcaEl.innerHTML = `<p class="placeholder-text">The RCA document is automatically generated when human engineer approves the fix.</p>`;
    }
  } catch (e) {
    console.error("Error loading incident detail", e);
  }
}

function updatePipelineStepper(stageStr) {
  let currentStageNum = 1;
  if (stageStr.includes("1")) currentStageNum = 1;
  else if (stageStr.includes("2")) currentStageNum = 2;
  else if (stageStr.includes("3")) currentStageNum = 3;
  else if (stageStr.includes("4")) currentStageNum = 4;
  else if (stageStr.includes("5")) currentStageNum = 5;
  else if (stageStr.includes("6")) currentStageNum = 6;

  document.querySelectorAll(".step-node").forEach((node) => {
    const s = parseInt(node.dataset.stage, 10);
    node.classList.remove("active", "completed");
    if (s < currentStageNum || currentStageNum === 6) {
      node.classList.add("completed");
    } else if (s === currentStageNum) {
      node.classList.add("active");
    }
  });
}

function renderTimeline(messages, autoScroll) {
  const container = document.getElementById("chat-timeline");
  container.innerHTML = "";

  messages.forEach((msg) => {
    const el = document.createElement("div");
    el.className = "chat-message";

    let icon = "🤖";
    let roleClass = "avatar-commander";
    let badgeText = "AI Squad";

    if (msg.sender_role === "remediator") {
      icon = "🛠️";
      roleClass = "avatar-remediator";
      badgeText = "Code Remediator";
    } else if (msg.sender_role === "verifier") {
      icon = "🔍";
      roleClass = "avatar-verifier";
      badgeText = "Independent QA Verifier";
    } else if (msg.sender_role === "human") {
      icon = "👤";
      roleClass = "avatar-human";
      badgeText = "Lead Engineer";
    } else if (msg.sender_role === "commander") {
      icon = "🚨";
      roleClass = "avatar-commander";
      badgeText = "Incident Commander";
    }

    let codeHtml = "";
    if (msg.code_snippet) {
      codeHtml = `<pre class="diff-viewer" style="margin-top: 10px;">${formatDiff(msg.code_snippet)}</pre>`;
    }

    let actionsHtml = "";
    if (msg.actions && msg.actions.length > 0) {
      actionsHtml = `<div class="chat-actions">`;
      msg.actions.forEach((act) => {
        actionsHtml += `<button class="btn btn-${act.style}" onclick="triggerAction('${act.action_id}')">${escapeHtml(act.label)}</button>`;
      });
      actionsHtml += `</div>`;
    }

    el.innerHTML = `
      <div class="chat-avatar ${roleClass}">${icon}</div>
      <div class="chat-body">
        <div class="chat-author-row">
          <span class="chat-author-name">${escapeHtml(msg.sender_name)}</span>
          <span class="chat-author-badge">${badgeText}</span>
          <span class="chat-time">${new Date(msg.timestamp * 1000).toLocaleTimeString()}</span>
        </div>
        <div class="chat-text">${formatMarkdown(msg.content)}</div>
        ${codeHtml}
        ${actionsHtml}
      </div>
    `;

    container.appendChild(el);
  });

  if (autoScroll) {
    container.scrollTop = container.scrollHeight;
  }
}

async function loadMistakes() {
  try {
    const res = await fetch("/api/mistakes");
    const mistakes = await res.json();
    const tbody = document.getElementById("mistakes-tbody");
    tbody.innerHTML = "";

    mistakes.forEach((m) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td class="mistakes-id">${escapeHtml(m.id)}</td>
        <td><b>${escapeHtml(m.title)}</b></td>
        <td><code>${escapeHtml(m.anti_pattern)}</code></td>
        <td>${escapeHtml(m.prevention_rule)}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (e) {
    console.error("Failed to load mistakes", e);
  }
}

async function triggerAction(actionId) {
  if (!currentIncidentId) return;

  try {
    const res = await fetch(`/api/incidents/${currentIncidentId}/action`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: actionId, user_name: "Lead Engineer (You)" }),
    });
    const updated = await res.json();
    loadIncidentDetail(updated.id, true);
    loadIncidents();
    loadMistakes();
  } catch (e) {
    alert("Action failed: " + e.message);
  }
}

function getSeverityClass(sev) {
  if (sev.includes("P0")) return "severity-p0";
  if (sev.includes("P1")) return "severity-p1";
  return "severity-p2";
}

function formatDiff(diffText) {
  if (!diffText) return "";
  return diffText
    .split("\n")
    .map((line) => {
      const escaped = escapeHtml(line);
      if (line.startsWith("+") && !line.startsWith("+++")) {
        return `<span class="diff-add">${escaped}</span>`;
      }
      if (line.startsWith("-") && !line.startsWith("---")) {
        return `<span class="diff-sub">${escaped}</span>`;
      }
      return escaped;
    })
    .join("\n");
}

function formatMarkdown(md) {
  if (!md) return "";
  let html = escapeHtml(md);
  html = html.replace(/\*\*(.*?)\*\*/g, "<b>$1</b>");
  html = html.replace(/\*(.*?)\*/g, "<i>$1</i>");
  html = html.replace(/`(.*?)`/g, "<code>$1</code>");
  html = html.replace(/\n\n/g, "<br><br>");
  html = html.replace(/^# (.*$)/gim, "<h2>$1</h2>");
  html = html.replace(/^## (.*$)/gim, "<h3>$1</h3>");
  return html;
}

function escapeHtml(str) {
  if (!str) return "";
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
