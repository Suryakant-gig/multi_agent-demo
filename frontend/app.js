/**
 * OmniData AI Frontend Reactive Application
 */

const API_BASE = window.location.origin;

// State
let sessionId = localStorage.getItem("omnidata_session_id") || "sess-" + Math.random().toString(36).substring(2, 9);
localStorage.setItem("omnidata_session_id", sessionId);

let activeDataset = null;

// DOM Elements
const displaySessionId = document.getElementById("displaySessionId");
const sessionStatus = document.getElementById("sessionStatus");
const fileInput = document.getElementById("fileInput");
const loadSampleBtn = document.getElementById("loadSampleBtn");
const newSessionBtn = document.getElementById("newSessionBtn");
const datasetInfo = document.getElementById("datasetInfo");
const rowCountBadge = document.getElementById("rowCountBadge");
const columnTags = document.getElementById("columnTags");

const chatContainer = document.getElementById("chatContainer");
const chatInput = document.getElementById("chatInput");
const sendBtn = document.getElementById("sendBtn");
const promptChips = document.getElementById("promptChips");

// Tabs
const navItems = document.querySelectorAll(".nav-item");
const tabPanes = document.querySelectorAll(".tab-pane");

// Chart Studio Elements
const chartTypeSelect = document.getElementById("chartTypeSelect");
const chartXSelect = document.getElementById("chartXSelect");
const chartYSelect = document.getElementById("chartYSelect");
const chartAggSelect = document.getElementById("chartAggSelect");
const renderChartBtn = document.getElementById("renderChartBtn");
const chartPreviewContainer = document.getElementById("chartPreviewContainer");

// Search Elements
const directSearchQuery = document.getElementById("directSearchQuery");
const directTopK = document.getElementById("directTopK");
const executeSearchBtn = document.getElementById("executeSearchBtn");
const searchResultsContainer = document.getElementById("searchResultsContainer");

// Profiler Elements
const profilerContent = document.getElementById("profilerContent");

// Modal Elements
const imageModal = document.getElementById("imageModal");
const modalImg = document.getElementById("modalImg");
const modalCloseBtn = document.getElementById("modalCloseBtn");

// Initialize
function init() {
  displaySessionId.textContent = sessionId;
  checkHealth();
  setupTabs();
  setupChat();
  setupUpload();
  setupSearch();
  setupChartStudio();
  setupModal();
}

// 1. Health Check
async function checkHealth() {
  try {
    const res = await fetch(`${API_BASE}/api/v1/health`);
    if (res.ok) {
      sessionStatus.textContent = "API Online";
    } else {
      sessionStatus.textContent = "API Error";
    }
  } catch (err) {
    sessionStatus.textContent = "Connecting...";
  }
}

// 2. Tab Navigation
function setupTabs() {
  navItems.forEach(item => {
    item.addEventListener("click", () => {
      const targetTab = item.dataset.tab;
      navItems.forEach(n => n.classList.remove("active"));
      tabPanes.forEach(p => p.classList.remove("active"));

      item.classList.add("active");
      const targetPane = document.getElementById(`pane-${targetTab}`);
      if (targetPane) targetPane.classList.add("active");
    });
  });

  newSessionBtn.addEventListener("click", () => {
    sessionId = "sess-" + Math.random().toString(36).substring(2, 9);
    localStorage.setItem("omnidata_session_id", sessionId);
    displaySessionId.textContent = sessionId;
    activeDataset = null;
    updateDatasetSidebar(null);
    chatContainer.innerHTML = `
      <div class="message-row assistant">
        <div class="avatar ai-avatar">AI</div>
        <div class="message-bubble">
          <div class="message-header"><span class="sender-name">OmniData Assistant</span></div>
          <div class="message-body"><p>Session reset. Please upload a new dataset or load the sample data.</p></div>
        </div>
      </div>
    `;
  });
}

// 3. File Upload & Ingestion
function setupUpload() {
  fileInput.addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    await uploadFileObject(file);
  });

  loadSampleBtn.addEventListener("click", async () => {
    loadSampleBtn.disabled = true;
    loadSampleBtn.innerHTML = `<span>⏳</span> Loading Sample...`;
    try {
      const res = await fetch(`${API_BASE}/api/v1/upload-sample?session_id=${sessionId}`, { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        handleUploadSuccess(data);
      } else {
        alert("Failed to load sample dataset from server.");
      }
    } catch (err) {
      console.error(err);
      alert("Error loading sample data.");
    } finally {
      loadSampleBtn.disabled = false;
      loadSampleBtn.innerHTML = `<span>✨</span> Load Sample Sales Dataset`;
    }
  });
}

async function uploadFileObject(file) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("session_id", sessionId);

  appendMessage("assistant", `Uploading and indexing file <strong>${file.name}</strong>...`);

  try {
    const res = await fetch(`${API_BASE}/api/v1/upload`, {
      method: "POST",
      body: formData
    });

    if (!res.ok) {
      const err = await res.json();
      appendMessage("assistant", `❌ Upload failed: ${err.error || err.detail || "Validation error"}`);
      return;
    }

    const data = await res.json();
    handleUploadSuccess(data);
  } catch (err) {
    appendMessage("assistant", `❌ Network error while uploading: ${err.message}`);
  }
}

function handleUploadSuccess(data) {
  activeDataset = data;
  updateDatasetSidebar(data);
  populateDropdowns(data.columns);
  updateProfiler(data);
  appendMessage("assistant", `✅ Successfully indexed <strong>${data.file_name}</strong> (${data.row_count} rows, ${data.column_count} columns). You can now ask questions, run Top-K rankings, or request charts!`);
}

function updateDatasetSidebar(data) {
  if (!data) {
    rowCountBadge.textContent = "No file";
    datasetInfo.innerHTML = `<p class="empty-hint">Upload a CSV or Excel file to begin analyzing.</p>`;
    columnTags.innerHTML = "";
    return;
  }

  rowCountBadge.textContent = `${data.row_count} rows`;
  datasetInfo.innerHTML = `
    <div class="dataset-name-text">${data.file_name}</div>
    <div style="font-size: 0.75rem; color: var(--text-dim);">${data.column_count} columns detected</div>
  `;

  columnTags.innerHTML = data.columns.map(c => {
    const typeClass = c.is_numeric ? "numeric" : (c.is_categorical ? "categorical" : "");
    return `<span class="col-tag ${typeClass}" title="${c.data_type}">${c.name}</span>`;
  }).join("");
}

function populateDropdowns(columns) {
  chartXSelect.innerHTML = `<option value="">Select column</option>`;
  chartYSelect.innerHTML = `<option value="">Select column (optional)</option>`;

  columns.forEach(col => {
    chartXSelect.innerHTML += `<option value="${col.name}">${col.name} (${col.data_type})</option>`;
    chartYSelect.innerHTML += `<option value="${col.name}">${col.name} (${col.data_type})</option>`;
  });
}

// 4. Chat Workspace
function setupChat() {
  sendBtn.addEventListener("click", () => handleSendMessage());
  chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  });

  // Prompt chips
  promptChips.addEventListener("click", (e) => {
    if (e.target.classList.contains("chip")) {
      const prompt = e.target.dataset.prompt;
      chatInput.value = prompt;
      handleSendMessage();
    }
  });
}

async function handleSendMessage() {
  const query = chatInput.value.trim();
  if (!query) return;

  chatInput.value = "";
  appendMessage("user", query);

  const typingId = showTypingIndicator();

  try {
    const res = await fetch(`${API_BASE}/api/v1/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, session_id: sessionId })
    });

    removeTypingIndicator(typingId);

    if (!res.ok) {
      const err = await res.json();
      appendMessage("assistant", `❌ Error: ${err.error || err.detail || "Agent execution failed."}`);
      return;
    }

    const data = await res.json();
    renderAgentResponse(data);
  } catch (err) {
    removeTypingIndicator(typingId);
    appendMessage("assistant", `❌ Network error: ${err.message}`);
  }
}

function appendMessage(role, text) {
  const row = document.createElement("div");
  row.className = `message-row ${role}`;
  row.innerHTML = `
    <div class="avatar ${role === 'user' ? 'user-avatar' : 'ai-avatar'}">${role === 'user' ? 'U' : 'AI'}</div>
    <div class="message-bubble">
      <div class="message-header">
        <span class="sender-name">${role === 'user' ? 'You' : 'OmniData Assistant'}</span>
        <span class="timestamp">${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
      </div>
      <div class="message-body">${formatMarkdown(text)}</div>
    </div>
  `;
  chatContainer.appendChild(row);
  chatContainer.scrollTop = chatContainer.scrollHeight;
}

function renderAgentResponse(data) {
  const row = document.createElement("div");
  row.className = "message-row assistant";

  let toolPillHtml = "";
  if (data.tool_calls && data.tool_calls.length > 0) {
    const tc = data.tool_calls[0];
    toolPillHtml = `
      <div class="tool-pill">
        <div class="tool-pill-header">
          <span>🔧 Tool: <code>${tc.tool_name}</code></span>
          <span>${tc.execution_time_ms}ms</span>
        </div>
        <div style="font-family: monospace; font-size: 0.72rem; color: #94a3b8;">
          params: ${JSON.stringify(tc.parameters)}
        </div>
      </div>
    `;
  }

  let citationsHtml = "";
  if (data.citations && data.citations.length > 0) {
    citationsHtml = `
      <div class="citations-wrapper">
        <span style="font-size: 0.75rem; font-weight: 700; color: var(--text-dim);">VERIFIABLE CITATIONS:</span>
        ${data.citations.map(c => `
          <div class="citation-chip">
            <span>📌</span>
            <span><strong>${c.file_name}</strong> ${c.row_index !== null ? `(Row ${c.row_index})` : '(Summary)'}: ${c.snippet || c.source_description}</span>
          </div>
        `).join("")}
      </div>
    `;
  }

  let chartHtml = "";
  if (data.chart && data.chart.image_base64) {
    chartHtml = `
      <div class="chart-render-box">
        <img src="${data.chart.image_base64}" alt="${data.chart.title}" onclick="openModal('${data.chart.image_base64}')">
        <div style="margin-top: 6px; font-size: 0.78rem; color: var(--text-dim);">
          Click chart image to view full resolution
        </div>
      </div>
    `;
  }

  row.innerHTML = `
    <div class="avatar ai-avatar">AI</div>
    <div class="message-bubble">
      <div class="message-header">
        <span class="sender-name">OmniData Assistant</span>
        <span class="telemetry-tag">${data.intent}</span>
        <span class="timestamp">${data.duration_ms}ms</span>
      </div>
      <div class="message-body">
        ${formatMarkdown(data.answer)}
        ${toolPillHtml}
        ${chartHtml}
        ${citationsHtml}
      </div>
    </div>
  `;

  chatContainer.appendChild(row);
  chatContainer.scrollTop = chatContainer.scrollHeight;
}

function showTypingIndicator() {
  const id = "typing-" + Date.now();
  const row = document.createElement("div");
  row.className = "message-row assistant";
  row.id = id;
  row.innerHTML = `
    <div class="avatar ai-avatar">AI</div>
    <div class="message-bubble" style="padding: 12px 18px;">
      <span class="pulse-dot" style="display: inline-block;"></span>
      <span style="font-size: 0.85rem; color: var(--text-dim); margin-left: 8px;">Agent thinking & querying tools...</span>
    </div>
  `;
  chatContainer.appendChild(row);
  chatContainer.scrollTop = chatContainer.scrollHeight;
  return id;
}

function removeTypingIndicator(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

// 5. Direct Search
function setupSearch() {
  executeSearchBtn.addEventListener("click", async () => {
    const query = directSearchQuery.value.trim();
    if (!query) {
      alert("Please enter a search query.");
      return;
    }

    searchResultsContainer.innerHTML = `<p class="empty-hint">Searching...</p>`;
    try {
      const res = await fetch(`${API_BASE}/api/v1/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          query: query,
          top_k: parseInt(directTopK.value, 10)
        })
      });

      if (!res.ok) {
        const err = await res.json();
        searchResultsContainer.innerHTML = `<p class="empty-hint">❌ ${err.error || err.detail}</p>`;
        return;
      }

      const data = await res.json();
      if (!data.results || data.results.length === 0) {
        searchResultsContainer.innerHTML = `<p class="empty-hint">No matching records found.</p>`;
        return;
      }

      searchResultsContainer.innerHTML = data.results.map((r, i) => `
        <div class="result-card">
          <div class="result-header">
            <span style="font-weight: 700;">Result #${i + 1} (Row ${r.row_index})</span>
            <span class="result-score">Relevance: ${r.score}</span>
          </div>
          <div class="result-data-grid">
            ${Object.entries(r.data).map(([k, v]) => `
              <div class="result-data-item">
                <span class="key">${k}:</span> <span class="val">${v}</span>
              </div>
            `).join("")}
          </div>
          ${r.citation ? `
            <div style="margin-top: 8px; font-size: 0.75rem; color: #38bdf8;">
              📌 ${r.citation.source_description}
            </div>
          ` : ""}
        </div>
      `).join("");
    } catch (err) {
      searchResultsContainer.innerHTML = `<p class="empty-hint">Error: ${err.message}</p>`;
    }
  });
}

// 6. Chart Studio
function setupChartStudio() {
  renderChartBtn.addEventListener("click", async () => {
    const chartType = chartTypeSelect.value;
    const xCol = chartXSelect.value;
    const yCol = chartYSelect.value || null;
    const agg = chartAggSelect.value;

    if (!xCol) {
      alert("Please select an X Column.");
      return;
    }

    chartPreviewContainer.innerHTML = `<p class="empty-hint">Generating visualization...</p>`;
    try {
      const res = await fetch(`${API_BASE}/api/v1/chart`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          chart_type: chartType,
          x_column: xCol,
          y_column: yCol,
          aggregation: agg,
          title: `${chartType.toUpperCase()} of ${yCol || xCol} by ${xCol}`
        })
      });

      if (!res.ok) {
        const err = await res.json();
        chartPreviewContainer.innerHTML = `<p class="empty-hint">❌ ${err.error || err.detail}</p>`;
        return;
      }

      const data = await res.json();
      chartPreviewContainer.innerHTML = `
        <div class="chart-render-box" style="margin-top: 0;">
          <img src="${data.image_base64}" alt="${data.title}" onclick="openModal('${data.image_base64}')">
          <div style="margin-top: 12px; display: flex; justify-content: center; gap: 12px;">
            <a href="${data.image_base64}" download="chart.png" class="btn-secondary" style="font-size: 0.8rem;">📥 Download PNG</a>
          </div>
        </div>
      `;
    } catch (err) {
      chartPreviewContainer.innerHTML = `<p class="empty-hint">Error: ${err.message}</p>`;
    }
  });
}

// 7. Data Profiler
function updateProfiler(data) {
  profilerContent.innerHTML = `
    <div style="margin-bottom: 16px;">
      <h3 style="font-family: var(--font-heading); margin-bottom: 6px;">${data.file_name}</h3>
      <p style="font-size: 0.85rem; color: var(--text-muted);">${data.row_count} total records &bull; ${data.column_count} columns &bull; Size: ${(data.file_size_bytes / 1024).toFixed(1)} KB</p>
    </div>
    <div class="table-wrapper">
      <table class="data-table">
        <thead>
          <tr>
            <th>Column Name</th>
            <th>Type</th>
            <th>Missing Values</th>
            <th>Distinct Values</th>
            <th>Sample Values</th>
          </tr>
        </thead>
        <tbody>
          ${data.columns.map(c => `
            <tr>
              <td style="font-weight: 600;">${c.name}</td>
              <td><span class="badge">${c.data_type}</span></td>
              <td>${c.null_count}</td>
              <td>${c.unique_count}</td>
              <td style="color: var(--text-muted);">${c.sample_values.join(", ")}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

// 8. Modal & Helpers
function setupModal() {
  window.openModal = function(src) {
    modalImg.src = src;
    imageModal.style.display = "flex";
  };
  modalCloseBtn.addEventListener("click", () => {
    imageModal.style.display = "none";
  });
  imageModal.addEventListener("click", (e) => {
    if (e.target === imageModal) imageModal.style.display = "none";
  });
}

function formatMarkdown(text) {
  if (!text) return "";
  let html = text
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.*?)\*/g, "<em>$1</em>")
    .replace(/`(.*?)`/g, "<code>$1</code>");
  return html;
}

// Start
document.addEventListener("DOMContentLoaded", init);
