/**
 * InfinityGPT — Reactive Conversational Frontend Client
 */

const API_BASE = "/api/v1";

/**
 * Shared API request helper.
 * - Parses JSON only when Content-Type matches.
 * - Surfaces detailed backend error message.
 * - Prevents raw HTML error pages from throwing SyntaxError: Unexpected token '<'.
 */
async function apiRequest(endpoint, options = {}) {
  const url = endpoint.startsWith("http")
    ? endpoint
    : `${API_BASE}${endpoint.startsWith("/") ? "" : "/"}${endpoint}`;

  const response = await fetch(url, options);
  const contentType = response.headers.get("content-type") || "";

  if (!response.ok) {
    if (contentType.includes("application/json")) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || err.error || err.message || `Request failed (${response.status})`);
    }
    const text = await response.text().catch(() => "");
    throw new Error(`HTTP ${response.status}: ${response.statusText || text.slice(0, 100) || "Server error"}`);
  }

  if (contentType.includes("application/json")) {
    return await response.json();
  }
  return await response.text();
}

// State
let activeConversationId = localStorage.getItem("infinity_conversation_id") || null;
let currentConversation = null;
let conversationsList = [];
let isGenerating = false;

// DOM Elements
const sidebar = document.getElementById("sidebar");
const sidebarToggleBtn = document.getElementById("sidebarToggleBtn");
const newChatBtn = document.getElementById("newChatBtn");
const currentChatTitle = document.getElementById("currentChatTitle");
const listToday = document.getElementById("listToday");
const listYesterday = document.getElementById("listYesterday");
const listOlder = document.getElementById("listOlder");
const contextFileCount = document.getElementById("contextFileCount");
const contextFilesList = document.getElementById("contextFilesList");

const messagesContainer = document.getElementById("messagesContainer");
const emptyState = document.getElementById("emptyState");
const messageFeed = document.getElementById("messageFeed");
const suggestionChips = document.getElementById("suggestionChips");
const clearChatBtn = document.getElementById("clearChatBtn");
const loadSampleBtn = document.getElementById("loadSampleBtn");

const composerForm = document.getElementById("composerForm");
const messageInput = document.getElementById("messageInput");
const sendBtn = document.getElementById("sendBtn");
const attachBtn = document.getElementById("attachBtn");
const fileAttachmentInput = document.getElementById("fileAttachmentInput");
const attachmentsPreviewBar = document.getElementById("attachmentsPreviewBar");

// Modals
const toolsModal = document.getElementById("toolsModal");
const openToolsBtn = document.getElementById("openToolsBtn");
const toolsCloseBtn = document.getElementById("toolsCloseBtn");
const imageModal = document.getElementById("imageModal");
const modalImg = document.getElementById("modalImg");
const imageCloseBtn = document.getElementById("imageCloseBtn");
const settingsModal = document.getElementById("settingsModal");
const openSettingsBtn = document.getElementById("openSettingsBtn");
const settingsCloseBtn = document.getElementById("settingsCloseBtn");
const settingsSessionId = document.getElementById("settingsSessionId");

// Secondary Tools Elements
const toolTabBtns = document.querySelectorAll(".tool-tab-btn");
const toolPanes = document.querySelectorAll(".tool-pane");
const directSearchQuery = document.getElementById("directSearchQuery");
const directTopK = document.getElementById("directTopK");
const executeSearchBtn = document.getElementById("executeSearchBtn");
const searchResultsContainer = document.getElementById("searchResultsContainer");
const chartTypeSelect = document.getElementById("chartTypeSelect");
const chartXSelect = document.getElementById("chartXSelect");
const chartYSelect = document.getElementById("chartYSelect");
const chartAggSelect = document.getElementById("chartAggSelect");
const renderChartBtn = document.getElementById("renderChartBtn");
const chartPreviewContainer = document.getElementById("chartPreviewContainer");
const profilerContent = document.getElementById("profilerContent");

// Initialize Application
async function init() {
  setupSidebar();
  setupComposer();
  setupModals();
  setupSecondaryTools();
  setupSampleLoader();

  await refreshConversations();

  if (activeConversationId) {
    await loadConversation(activeConversationId);
  } else if (conversationsList.length > 0) {
    await loadConversation(conversationsList[0].conversation_id);
  } else {
    await startNewChat();
  }
}

// ---------------------------------------------------------------------------
// 1. Conversation Management & History
// ---------------------------------------------------------------------------

async function refreshConversations() {
  try {
    conversationsList = await apiRequest("/conversations");
    renderConversationsList();
  } catch (err) {
    console.error("Failed to load conversations:", err);
  }
}

function renderConversationsList() {
  listToday.innerHTML = "";
  listYesterday.innerHTML = "";
  listOlder.innerHTML = "";

  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const yesterdayStart = todayStart - 86400000;

  let hasToday = false;
  let hasYesterday = false;
  let hasOlder = false;

  conversationsList.forEach((conv) => {
    const updatedAt = new Date(conv.updated_at).getTime();
    const item = createConversationItem(conv);

    if (updatedAt >= todayStart) {
      listToday.appendChild(item);
      hasToday = true;
    } else if (updatedAt >= yesterdayStart) {
      listYesterday.appendChild(item);
      hasYesterday = true;
    } else {
      listOlder.appendChild(item);
      hasOlder = true;
    }
  });

  document.getElementById("sectionToday").style.display = hasToday ? "block" : "none";
  document.getElementById("sectionYesterday").style.display = hasYesterday ? "block" : "none";
  document.getElementById("sectionOlder").style.display = hasOlder ? "block" : "none";
}

function createConversationItem(conv) {
  const el = document.createElement("div");
  el.className = `conv-item ${conv.conversation_id === activeConversationId ? "active" : ""}`;
  el.dataset.id = conv.conversation_id;

  const titleSpan = document.createElement("span");
  titleSpan.className = "conv-title";
  titleSpan.textContent = conv.title || "New Chat";
  titleSpan.title = conv.title || "New Chat";

  const actions = document.createElement("div");
  actions.className = "conv-actions";

  // Rename Button
  const renameBtn = document.createElement("button");
  renameBtn.className = "conv-action-icon";
  renameBtn.title = "Rename conversation";
  renameBtn.innerHTML = `
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <path d="M12 20h9"></path>
      <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path>
    </svg>
  `;
  renameBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    promptRenameConversation(conv.conversation_id, conv.title);
  });

  // Delete Button
  const deleteBtn = document.createElement("button");
  deleteBtn.className = "conv-action-icon delete";
  deleteBtn.title = "Delete conversation";
  deleteBtn.innerHTML = `
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <polyline points="3 6 5 6 21 6"></polyline>
      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"></path>
    </svg>
  `;
  deleteBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    deleteConversation(conv.conversation_id);
  });

  actions.appendChild(renameBtn);
  actions.appendChild(deleteBtn);

  el.appendChild(titleSpan);
  el.appendChild(actions);

  el.addEventListener("click", () => {
    if (conv.conversation_id !== activeConversationId) {
      loadConversation(conv.conversation_id);
    }
  });

  return el;
}

async function startNewChat() {
  try {
    const conv = await apiRequest("/conversations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "New Chat" })
    });
    activeConversationId = conv.conversation_id;
    localStorage.setItem("infinity_conversation_id", activeConversationId);
    currentConversation = conv;
    renderCurrentConversation();
    await refreshConversations();
    messageInput.focus();
  } catch (err) {
    console.error("Failed to create new chat:", err);
  }
}

async function loadConversation(id) {
  try {
    currentConversation = await apiRequest(`/conversations/${id}`);
    activeConversationId = id;
    localStorage.setItem("infinity_conversation_id", id);
    renderCurrentConversation();
    renderConversationsList();
  } catch (err) {
    console.error("Failed to load conversation:", err);
    if (err.message && (err.message.includes("404") || err.message.includes("not found"))) {
      await startNewChat();
    }
  }
}

async function promptRenameConversation(id, currentTitle) {
  const newTitle = prompt("Enter a new title for this conversation:", currentTitle);
  if (newTitle && newTitle.trim() && newTitle.trim() !== currentTitle) {
    try {
      await apiRequest(`/conversations/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: newTitle.trim() })
      });
      if (currentConversation && currentConversation.conversation_id === id) {
        currentConversation.title = newTitle.trim();
        currentChatTitle.textContent = newTitle.trim();
      }
      await refreshConversations();
    } catch (err) {
      console.error("Failed to rename conversation:", err);
    }
  }
}

async function deleteConversation(id) {
  if (!confirm("Are you sure you want to delete this conversation?")) return;
  try {
    await apiRequest(`/conversations/${id}`, { method: "DELETE" });
    conversationsList = conversationsList.filter(c => c.conversation_id !== id);
    if (activeConversationId === id) {
      if (conversationsList.length > 0) {
        await loadConversation(conversationsList[0].conversation_id);
      } else {
        await startNewChat();
      }
    } else {
      renderConversationsList();
    }
  } catch (err) {
    console.error("Failed to delete conversation:", err);
  }
}

function renderCurrentConversation() {
  if (!currentConversation) return;

  currentChatTitle.textContent = currentConversation.title || "New Chat";
  settingsSessionId.textContent = currentConversation.session_id || currentConversation.conversation_id;

  updateContextCard(currentConversation.uploaded_files || []);

  const messages = currentConversation.messages || [];
  if (messages.length === 0) {
    emptyState.style.display = "flex";
    messageFeed.style.display = "none";
    messageFeed.innerHTML = "";
  } else {
    emptyState.style.display = "none";
    messageFeed.style.display = "flex";
    messageFeed.innerHTML = "";
    messages.forEach(msg => appendMessageElement(msg.role, msg));
    scrollToBottom();
  }
}

function updateContextCard(files) {
  contextFileCount.textContent = `${files.length} attached`;
  if (files.length === 0) {
    contextFilesList.innerHTML = `<p class="no-files-hint">No files attached yet. Upload CSV, Excel, or PDF.</p>`;
    return;
  }

  contextFilesList.innerHTML = files.map(f => {
    const icon = f.file_type === "pdf" ? "📄" : "📊";
    const sub = f.file_type === "pdf" ? `${f.page_count}p` : `${f.row_count} rows`;
    return `
      <div class="file-pill" title="${f.file_name} (${sub})">
        <span class="file-icon">${icon}</span>
        <span class="file-name">${escapeHtml(f.file_name)}</span>
      </div>
    `;
  }).join("");

  // Populate profiler dropdowns if tabular dataset is present
  if (currentConversation.active_dataset && currentConversation.active_dataset.columns) {
    populateToolDropdowns(currentConversation.active_dataset.columns);
    updateProfiler(currentConversation.active_dataset);
  }
}

// ---------------------------------------------------------------------------
// 2. Composer & Message Sending
// ---------------------------------------------------------------------------

function setupComposer() {
  // Auto-growing textarea
  messageInput.addEventListener("input", () => {
    messageInput.style.height = "auto";
    messageInput.style.height = Math.min(messageInput.scrollHeight, 180) + "px";
    sendBtn.disabled = !messageInput.value.trim() || isGenerating;
  });

  messageInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!sendBtn.disabled && !isGenerating) {
        handleSendMessage();
      }
    }
  });

  composerForm.addEventListener("submit", (e) => {
    e.preventDefault();
    if (!sendBtn.disabled && !isGenerating) {
      handleSendMessage();
    }
  });

  // Suggestion chips
  suggestionChips.addEventListener("click", (e) => {
    const btn = e.target.closest(".prompt-chip");
    if (btn) {
      const promptText = btn.dataset.prompt;
      messageInput.value = promptText;
      messageInput.dispatchEvent(new Event("input"));
      handleSendMessage();
    }
  });

  // Attachment button & drag and drop
  attachBtn.addEventListener("click", () => fileAttachmentInput.click());
  fileAttachmentInput.addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (file) {
      await uploadFile(file);
      fileAttachmentInput.value = "";
    }
  });

  setupDragAndDrop();
}

function setupDragAndDrop() {
  const dropZone = document.querySelector(".infinity-main");

  ["dragenter", "dragover"].forEach(eventName => {
    dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      dropZone.classList.add("drag-over");
    }, false);
  });

  ["dragleave", "drop"].forEach(eventName => {
    dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      dropZone.classList.remove("drag-over");
    }, false);
  });

  dropZone.addEventListener("drop", async (e) => {
    const dt = e.dataTransfer;
    const files = dt.files;
    if (files.length > 0) {
      await uploadFile(files[0]);
    }
  });
}

async function uploadFile(file) {
  if (!activeConversationId) await startNewChat();

  const formData = new FormData();
  formData.append("file", file);
  formData.append("conversation_id", activeConversationId);
  formData.append("session_id", activeConversationId);

  emptyState.style.display = "none";
  messageFeed.style.display = "flex";

  const uploadingNotice = appendSystemNotice(`Uploading and indexing <strong>${escapeHtml(file.name)}</strong>...`);
  scrollToBottom();

  try {
    const data = await apiRequest("/upload", {
      method: "POST",
      body: formData
    });

    uploadingNotice.remove();
    appendSystemNotice(`✅ <strong>${escapeHtml(data.file_name)}</strong> uploaded successfully. ${data.message}`);

    await loadConversation(activeConversationId);
    await refreshConversations();
  } catch (err) {
    uploadingNotice.remove();
    appendSystemNotice(`❌ Upload error: ${err.message}`);
  }
}

async function handleSendMessage() {
  const query = messageInput.value.trim();
  if (!query || isGenerating) return;

  if (!activeConversationId) await startNewChat();

  messageInput.value = "";
  messageInput.style.height = "auto";
  sendBtn.disabled = true;
  isGenerating = true;

  emptyState.style.display = "none";
  messageFeed.style.display = "flex";

  // Append user message immediately
  appendMessageElement("user", { content: query });
  scrollToBottom();

  const thinkingId = appendThinkingIndicator();
  scrollToBottom();

  try {
    const data = await apiRequest("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: query,
        conversation_id: activeConversationId,
        session_id: activeConversationId
      })
    });

    removeThinkingIndicator(thinkingId);
    appendMessageElement("assistant", data);
    scrollToBottom();

    // Reload conversation state to sync title and context
    await loadConversation(activeConversationId);
    await refreshConversations();
  } catch (err) {
    removeThinkingIndicator(thinkingId);
    appendMessageElement("assistant", { content: `❌ **Error:** ${err.message}` });
  } finally {
    isGenerating = false;
    sendBtn.disabled = !messageInput.value.trim();
  }
}

// ---------------------------------------------------------------------------
// 3. Message Rendering & ChatGPT-like Structure
// ---------------------------------------------------------------------------

function appendMessageElement(role, data) {
  const row = document.createElement("div");
  row.className = `message-row ${role}`;

  const avatar = document.createElement("div");
  avatar.className = `message-avatar ${role === "user" ? "user-avatar" : "ai"}`;
  avatar.innerHTML = role === "user" ? "U" : `
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
      <path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm0 18a8 8 0 1 1 8-8 8 8 0 0 1-8 8z"/>
      <path d="M8 12a4 4 0 1 0 4-4 4 4 0 0 0-4 4zm8 0a4 4 0 1 0-4 4 4 4 0 0 0 4-4z"/>
    </svg>
  `;

  const wrapper = document.createElement("div");
  wrapper.className = "message-content-wrapper";

  const bubble = document.createElement("div");
  bubble.className = "message-bubble";

  if (role === "user") {
    bubble.textContent = data.content;
    wrapper.appendChild(bubble);
  } else {
    // 1. Tool execution indicators (collapsible accordion)
    if (data.tool_calls && data.tool_calls.length > 0) {
      const toolCard = createToolActivityCard(data.tool_calls);
      bubble.appendChild(toolCard);
    }

    // 2. Main Markdown Text Content
    const textDiv = document.createElement("div");
    textDiv.className = "markdown-body";
    textDiv.innerHTML = formatMarkdown(data.answer || data.content || "");
    bubble.appendChild(textDiv);

    // 3. Render Chart if present
    if (data.chart && data.chart.image_base64) {
      const chartBox = createChartCard(data.chart);
      bubble.appendChild(chartBox);
    }

    // 4. Research Sources Section
    if (data.sources && data.sources.length > 0) {
      const sourcesBox = createSourcesCard(data.sources);
      bubble.appendChild(sourcesBox);
    }

    // 5. Verifiable Citations (Dataset and PDF)
    const nonWebCitations = (data.citations || []).filter(c => c.citation_type !== "web");
    if (nonWebCitations.length > 0) {
      const citsBox = createCitationsBox(nonWebCitations);
      bubble.appendChild(citsBox);
    }

    wrapper.appendChild(bubble);
  }

  row.appendChild(avatar);
  row.appendChild(wrapper);
  messageFeed.appendChild(row);
  return row;
}

function createToolActivityCard(toolCalls) {
  const card = document.createElement("div");
  card.className = "tool-activity-card";

  const firstTool = toolCalls[0];
  const header = document.createElement("div");
  header.className = "tool-activity-header";
  header.innerHTML = `
    <div class="tool-activity-title">
      <span>⚡ Completed ${toolCalls.length} tool action(s) (${firstTool.tool_name})</span>
    </div>
    <span style="font-size: 0.75rem;">${firstTool.execution_time_ms}ms &#9662;</span>
  `;

  const body = document.createElement("div");
  body.className = "tool-details-body";
  body.style.display = "none";
  body.innerHTML = toolCalls.map(tc => `
    <div><strong>Tool:</strong> <code>${tc.tool_name}</code></div>
    <div><strong>Params:</strong> ${escapeHtml(JSON.stringify(tc.parameters))}</div>
    <div style="margin-top: 4px; color: ${tc.success ? '#10b981' : '#f43f5e'};">
      Status: ${tc.success ? "Success" : "Failed: " + tc.error_message}
    </div>
  `).join("<hr style='border-color: #334155; margin: 6px 0;'>");

  header.addEventListener("click", () => {
    body.style.display = body.style.display === "none" ? "block" : "none";
  });

  card.appendChild(header);
  card.appendChild(body);
  return card;
}

function createSourcesCard(sources) {
  const card = document.createElement("div");
  card.className = "sources-card";

  const title = document.createElement("div");
  title.className = "sources-card-title";
  title.innerHTML = `
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path>
      <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path>
    </svg>
    Research Sources (${sources.length})
  `;

  const list = document.createElement("div");
  list.className = "sources-list";

  sources.forEach((s, idx) => {
    const item = document.createElement("div");
    item.className = "source-item";
    const cleanUrl = sanitizeUrl(s.url);
    item.innerHTML = `
      <div class="source-num">[${idx + 1}]</div>
      <div class="source-body">
        <a href="${cleanUrl}" target="_blank" rel="noopener noreferrer" class="source-link">${escapeHtml(s.title || cleanUrl)}</a>
        <div class="source-meta">${escapeHtml(s.domain || "")} ${s.published_at ? `&bull; ${s.published_at}` : ""} &bull; <span style="text-transform: uppercase;">${s.source_type}</span></div>
      </div>
    `;
    list.appendChild(item);
  });

  card.appendChild(title);
  card.appendChild(list);
  return card;
}

function createCitationsBox(citations) {
  const box = document.createElement("div");
  box.className = "citations-box";

  citations.forEach(c => {
    const chip = document.createElement("div");
    chip.className = `citation-chip ${c.citation_type === 'pdf' ? 'pdf' : ''}`;
    const icon = c.citation_type === "pdf" ? "📄" : "📌";
    const label = c.citation_type === "pdf"
      ? `Source: <strong>${escapeHtml(c.file_name)}</strong> (Page ${c.page_number || '?'})`
      : `Source: <strong>${escapeHtml(c.file_name)}</strong> ${c.row_index !== null && c.row_index !== undefined ? `(Row ${c.row_index})` : '(Summary)'}`;

    chip.innerHTML = `
      <span>${icon}</span>
      <span>${label}: ${escapeHtml(c.snippet || c.source_description || '')}</span>
    `;
    box.appendChild(chip);
  });

  return box;
}

function createChartCard(chart) {
  const card = document.createElement("div");
  card.className = "chart-card";

  const img = document.createElement("img");
  img.src = chart.image_base64;
  img.alt = chart.title || "Chart";
  img.addEventListener("click", () => openImageZoom(chart.image_base64));

  const hint = document.createElement("div");
  hint.className = "chart-hint";
  hint.textContent = "Click chart to expand view";

  card.appendChild(img);
  card.appendChild(hint);
  return card;
}

function appendThinkingIndicator() {
  const id = "thinking-" + Date.now();
  const row = document.createElement("div");
  row.className = "message-row assistant";
  row.id = id;

  row.innerHTML = `
    <div class="message-avatar ai">
      <div class="tool-spinner" style="width: 14px; height: 14px; border-width: 2px;"></div>
    </div>
    <div class="message-content-wrapper">
      <div class="message-bubble" style="color: var(--text-muted); font-size: 0.88rem;">
        InfinityGPT is reasoning and executing tools...
      </div>
    </div>
  `;

  messageFeed.appendChild(row);
  return id;
}

function removeThinkingIndicator(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

function appendSystemNotice(htmlText) {
  const row = document.createElement("div");
  row.className = "message-row assistant";
  row.innerHTML = `
    <div class="message-avatar ai" style="background: #334155;">ℹ️</div>
    <div class="message-content-wrapper">
      <div class="message-bubble" style="font-size: 0.88rem; color: var(--text-muted);">
        ${htmlText}
      </div>
    </div>
  `;
  messageFeed.appendChild(row);
  return row;
}

function scrollToBottom() {
  messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

// ---------------------------------------------------------------------------
// 4. Markdown Formatter & Security Sanitization
// ---------------------------------------------------------------------------

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function sanitizeUrl(url) {
  if (!url) return "#";
  const trimmed = url.trim();
  if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) {
    return trimmed;
  }
  return "#";
}

function formatMarkdown(text) {
  if (!text) return "";

  // 1. Extract and preserve code blocks
  const codeBlocks = [];
  let processed = text.replace(/```([a-zA-Z0-9_\-]*)?\n([\s\S]*?)```/g, (match, lang, code) => {
    const id = `__CODE_BLOCK_${codeBlocks.length}__`;
    codeBlocks.push({ lang: lang || "text", code });
    return id;
  });

  // 2. Headings
  processed = processed.replace(/^### (.*$)/gim, '<h3>$1</h3>');
  processed = processed.replace(/^## (.*$)/gim, '<h2>$1</h2>');
  processed = processed.replace(/^# (.*$)/gim, '<h1>$1</h1>');

  // 3. Bold & Italic
  processed = processed.replace(/\*\*\*(.*?)\*\*\*/g, '<strong><em>$1</em></strong>');
  processed = processed.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  processed = processed.replace(/\*(.*?)\*/g, '<em>$1</em>');

  // 4. Inline Code
  processed = processed.replace(/`([^`]+)`/g, (m, c) => `<code>${escapeHtml(c)}</code>`);

  // 5. Links [text](url)
  processed = processed.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (match, text, url) => {
    const safeUrl = sanitizeUrl(url);
    return `<a href="${safeUrl}" target="_blank" rel="noopener noreferrer">${text}</a>`;
  });

  // 6. Tables
  processed = formatMarkdownTables(processed);

  // 7. Unordered Lists
  processed = processed.replace(/^\s*[-*]\s+(.*)$/gim, '<li>$1</li>');
  processed = processed.replace(/(<li>[\s\S]*?<\/li>)/g, '<ul>$1</ul>');
  processed = processed.replace(/<\/ul>\s*<ul>/g, '');

  // 8. Blockquotes
  processed = processed.replace(/^\>\s+(.*)$/gim, '<blockquote style="border-left: 3px solid var(--accent-primary); padding-left: 12px; margin: 8px 0; color: var(--text-muted);">$1</blockquote>');

  // 9. Paragraphs (lines separated by double newlines)
  const paragraphs = processed.split(/\n{2,}/);
  processed = paragraphs.map(p => {
    p = p.trim();
    if (!p) return "";
    if (p.startsWith("<h") || p.startsWith("<ul") || p.startsWith("<table") || p.startsWith("<blockquote") || p.startsWith("__CODE_BLOCK")) {
      return p;
    }
    return `<p>${p.replace(/\n/g, '<br>')}</p>`;
  }).join("\n");

  // 10. Restore code blocks safely
  codeBlocks.forEach((cb, idx) => {
    const id = `__CODE_BLOCK_${idx}__`;
    const escapedCode = escapeHtml(cb.code.trim());
    const blockHtml = `
      <div class="code-block">
        <div class="code-block-header">
          <span>${cb.lang}</span>
          <button class="copy-btn" onclick="navigator.clipboard.writeText(this.closest('.code-block').querySelector('pre').innerText); this.textContent='Copied!'; setTimeout(()=>this.textContent='Copy', 1500);">Copy</button>
        </div>
        <pre><code>${escapedCode}</code></pre>
      </div>
    `;
    processed = processed.replace(id, blockHtml);
  });

  return processed;
}

function formatMarkdownTables(text) {
  const lines = text.split("\n");
  let inTable = false;
  let tableRows = [];
  let outLines = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (line.startsWith("|") && line.endsWith("|")) {
      inTable = true;
      tableRows.push(line);
    } else {
      if (inTable) {
        outLines.push(renderHtmlTable(tableRows));
        tableRows = [];
        inTable = false;
      }
      outLines.push(lines[i]);
    }
  }

  if (inTable && tableRows.length > 0) {
    outLines.push(renderHtmlTable(tableRows));
  }

  return outLines.join("\n");
}

function renderHtmlTable(rows) {
  if (rows.length < 2) return rows.join("\n");

  const parseCells = (row) => row.split("|").slice(1, -1).map(c => c.trim());
  const headerCells = parseCells(rows[0]);

  let html = `<table class="markdown-table"><thead><tr>`;
  headerCells.forEach(h => html += `<th>${h}</th>`);
  html += `</tr></thead><tbody>`;

  for (let r = 2; r < rows.length; r++) {
    const cells = parseCells(rows[r]);
    html += `<tr>`;
    cells.forEach(c => html += `<td>${c}</td>`);
    html += `</tr>`;
  }

  html += `</tbody></table>`;
  return html;
}

// ---------------------------------------------------------------------------
// 5. Sidebar & UI Toggles
// ---------------------------------------------------------------------------

function setupSidebar() {
  newChatBtn.addEventListener("click", () => startNewChat());

  sidebarToggleBtn.addEventListener("click", () => {
    sidebar.classList.toggle("collapsed");
  });

  clearChatBtn.addEventListener("click", () => {
    if (confirm("Clear messages in this conversation?")) {
      if (currentConversation) {
        currentConversation.messages = [];
        renderCurrentConversation();
      }
    }
  });
}

function setupSampleLoader() {
  loadSampleBtn.addEventListener("click", async () => {
    if (!activeConversationId) await startNewChat();

    loadSampleBtn.disabled = true;
    loadSampleBtn.innerHTML = `<span>⏳ Loading...</span>`;

    try {
      const data = await apiRequest(`/upload-sample?session_id=${activeConversationId}`, { method: "POST" });
      appendSystemNotice(`✅ Loaded sample dataset <strong>sample_sales.csv</strong> (${data.row_count} rows, ${data.column_count} columns). You can now ask questions or request charts!`);
      await loadConversation(activeConversationId);
      await refreshConversations();
    } catch (err) {
      console.error(err);
      appendSystemNotice(`❌ Could not load sample dataset: ${err.message}`);
    } finally {
      loadSampleBtn.disabled = false;
      loadSampleBtn.innerHTML = `
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon>
        </svg>
        <span>Sample Sales Data</span>
      `;
    }
  });
}

// ---------------------------------------------------------------------------
// 6. Secondary Tools & Modals
// ---------------------------------------------------------------------------

function setupModals() {
  openToolsBtn.addEventListener("click", () => toolsModal.style.display = "flex");
  toolsCloseBtn.addEventListener("click", () => toolsModal.style.display = "none");
  toolsModal.addEventListener("click", (e) => {
    if (e.target === toolsModal) toolsModal.style.display = "none";
  });

  openSettingsBtn.addEventListener("click", () => settingsModal.style.display = "flex");
  settingsCloseBtn.addEventListener("click", () => settingsModal.style.display = "none");
  settingsModal.addEventListener("click", (e) => {
    if (e.target === settingsModal) settingsModal.style.display = "none";
  });

  imageCloseBtn.addEventListener("click", () => imageModal.style.display = "none");
  imageModal.addEventListener("click", (e) => {
    if (e.target === imageModal) imageModal.style.display = "none";
  });
}

function openImageZoom(src) {
  modalImg.src = src;
  imageModal.style.display = "flex";
}

function setupSecondaryTools() {
  toolTabBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      const tool = btn.dataset.tool;
      toolTabBtns.forEach(b => b.classList.remove("active"));
      toolPanes.forEach(p => p.classList.remove("active"));

      btn.classList.add("active");
      if (tool === "search") document.getElementById("paneToolSearch").classList.add("active");
      if (tool === "charts") document.getElementById("paneToolCharts").classList.add("active");
      if (tool === "profiler") document.getElementById("paneToolProfiler").classList.add("active");
    });
  });

  // Direct search action
  executeSearchBtn.addEventListener("click", async () => {
    const q = directSearchQuery.value.trim();
    if (!q) return;

    searchResultsContainer.innerHTML = `<p class="empty-hint">Searching records...</p>`;
    try {
      const data = await apiRequest("/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: activeConversationId,
          query: q,
          top_k: parseInt(directTopK.value, 10)
        })
      });

      if (!data.results || data.results.length === 0) {
        searchResultsContainer.innerHTML = `<p class="empty-hint">No matching rows found.</p>`;
        return;
      }

      searchResultsContainer.innerHTML = data.results.map((r, i) => `
        <div style="padding: 10px; border-bottom: 1px solid var(--border-subtle);">
          <div style="font-weight: 600; font-size: 0.85rem;">Result #${i + 1} (Row ${r.row_index}) - Score: ${r.score}</div>
          <div style="font-size: 0.78rem; color: var(--text-muted); margin-top: 4px;">
            ${Object.entries(r.data).map(([k, v]) => `<strong>${k}:</strong> ${v}`).join(" | ")}
          </div>
        </div>
      `).join("");
    } catch (err) {
      searchResultsContainer.innerHTML = `<p class="empty-hint">Error: ${err.message}</p>`;
    }
  });

  // Chart Studio action
  renderChartBtn.addEventListener("click", async () => {
    const chartType = chartTypeSelect.value;
    const xCol = chartXSelect.value;
    const yCol = chartYSelect.value || null;
    const agg = chartAggSelect.value;

    if (!xCol) {
      alert("Please select an X column.");
      return;
    }

    chartPreviewContainer.innerHTML = `<p class="empty-hint">Generating visualization...</p>`;
    try {
      const data = await apiRequest("/chart", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: activeConversationId,
          chart_type: chartType,
          x_column: xCol,
          y_column: yCol,
          aggregation: agg,
          title: `${chartType.toUpperCase()} of ${yCol || xCol} by ${xCol}`
        })
      });

      chartPreviewContainer.innerHTML = `
        <div style="text-align: center;">
          <img src="${data.image_base64}" style="max-width: 100%; border-radius: var(--radius-sm); cursor: pointer;" onclick="openImageZoom('${data.image_base64}')">
          <div style="margin-top: 8px;">
            <a href="${data.image_base64}" download="chart.png" class="btn-primary" style="font-size: 0.78rem; text-decoration: none;">Download PNG</a>
          </div>
        </div>
      `;
    } catch (err) {
      chartPreviewContainer.innerHTML = `<p class="empty-hint">Error: ${err.message}</p>`;
    }
  });
}

function populateToolDropdowns(columns) {
  chartXSelect.innerHTML = `<option value="">Select column</option>`;
  chartYSelect.innerHTML = `<option value="">Select column (optional)</option>`;

  columns.forEach(col => {
    chartXSelect.innerHTML += `<option value="${col.name}">${col.name} (${col.data_type})</option>`;
    chartYSelect.innerHTML += `<option value="${col.name}">${col.name} (${col.data_type})</option>`;
  });
}

function updateProfiler(dataset) {
  profilerContent.innerHTML = `
    <div style="margin-bottom: 12px;">
      <h4 style="margin: 0 0 4px;">${escapeHtml(dataset.file_name)}</h4>
      <div style="font-size: 0.8rem; color: var(--text-dim);">${dataset.row_count} rows &bull; ${dataset.column_count} columns</div>
    </div>
    <table class="markdown-table" style="font-size: 0.8rem;">
      <thead>
        <tr>
          <th>Column</th>
          <th>Type</th>
          <th>Missing</th>
          <th>Unique</th>
          <th>Sample Values</th>
        </tr>
      </thead>
      <tbody>
        ${dataset.columns.map(c => `
          <tr>
            <td><strong>${escapeHtml(c.name)}</strong></td>
            <td><code>${c.data_type}</code></td>
            <td>${c.null_count}</td>
            <td>${c.unique_count}</td>
            <td>${escapeHtml((c.sample_values || []).join(", "))}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

// Start Application
document.addEventListener("DOMContentLoaded", init);
