'use strict';

// Network calls: send chat messages and check server health.
const api = {
  async createSession() {
    const res = await fetch('/chat/session/new', {
      method: 'POST',
      credentials: 'include',
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `HTTP ${res.status}`);
    }
    return res.json();
  },

  async sendMessage(content, sessionId) {
    // FR9: send the user's query to the backend route that calls LLaMA 3.
    const res = await fetch('/chat/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ content, session_id: sessionId }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `HTTP ${res.status}`);
    }
    return res.json();
  },

  async submitFeedback(payload) {
    const res = await fetch('/feedback/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(payload),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    return data;
  },

  async checkHealth() {
    const res = await fetch('/api/health', { credentials: 'include' });
    return res.json();
  },
};

// Rendering helpers: escape user text, format times, and draw chat messages.
const ui = {
  escapeHtml(value) {
    return String(value)
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  },

  formatTime(iso) {
    if (!iso) return '';
    try {
      let str = String(iso).trim();
      if (!str.endsWith('Z') && !/[+-]\d{2}(:\d{2})?$/.test(str)) {
        str += 'Z';
      }
      const d = new Date(str);
      if (isNaN(d.getTime())) return '';
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch {
      return '';
    }
  },

  appendMessage(role, content, messageId, timestamp, responseTimeMs) {
    document.getElementById('welcome-message')?.remove();

    const container = document.getElementById('messages-container');
    const message = document.createElement('div');
    message.className = `message ${role}`;
    if (messageId) message.dataset.msgId = messageId;

    const isAssistant = role === 'assistant';
    message.innerHTML = `
      <div class="msg-avatar">${isAssistant ? 'AI' : 'You'}</div>
      <div class="msg-content">
        <div class="msg-bubble">${ui.escapeHtml(content).replaceAll('\n', '<br>')}</div>
        <div class="msg-meta">
          <span>${ui.formatTime(timestamp)}</span>
          ${isAssistant && Number.isFinite(responseTimeMs) ? `<span>${responseTimeMs} ms</span>` : ''}
          ${isAssistant && messageId ? `<button class="btn-feedback-trigger" data-id="${messageId}">Feedback</button>` : ''}
        </div>
      </div>
    `;

    message.querySelector('.btn-feedback-trigger')?.addEventListener('click', event => {
      feedback.open(event.currentTarget.dataset.id);
    });

    container.appendChild(message);
    container.scrollTop = container.scrollHeight;
  },

  renderWelcome() {
    document.getElementById('messages-container').innerHTML = `
      <div class="welcome-message" id="welcome-message">
        <h2>New Chat</h2>
        <p>Ask me anything. This page keeps only the current conversation.</p>
        <div class="suggestion-chips">
          <button class="chip" onclick="app.sendSuggestion('Explain machine learning in simple terms')">Machine learning</button>
          <button class="chip" onclick="app.sendSuggestion('Write a Python hello world program')">Python code</button>
          <button class="chip" onclick="app.sendSuggestion('Give me 3 tips for better writing')">Writing tips</button>
        </div>
      </div>
    `;
  },

  // FR9: show a real-time waiting indicator while LLaMA 3 generates a response.
  showTyping() {
    const container = document.getElementById('messages-container');
    const typing = document.createElement('div');
    typing.className = 'message assistant typing-indicator';
    typing.id = 'typing-indicator';
    typing.innerHTML = `
      <div class="msg-avatar">AI</div>
      <div class="msg-content">
        <div class="msg-bubble">
          <span class="typing-dot"></span>
          <span class="typing-dot"></span>
          <span class="typing-dot"></span>
        </div>
      </div>
    `;
    container.appendChild(typing);
    container.scrollTop = container.scrollHeight;
  },

  hideTyping() {
    document.getElementById('typing-indicator')?.remove();
  },

  setConnectionStatus(online, text) {
    const dot = document.querySelector('.status-dot');
    const label = document.querySelector('.status-text');
    dot.className = `status-dot ${online ? 'online' : 'offline'}`;
    label.textContent = text;
  },
};

// Feedback action: opens the dedicated feedback page for one assistant message.
const feedback = {
  open(messageId) {
    const sessionParam = app.currentSessionId ? `&session_id=${encodeURIComponent(app.currentSessionId)}` : '';
    window.location.href = `/feedback?message_id=${encodeURIComponent(messageId)}${sessionParam}`;
  },
};

// Page controller: binds UI events and manages the active in-page conversation.
const app = {
  currentSessionId: null,
  isLoading: false,
  pendingFeedbackMessageId: null,
  selectedRating: 0,
  selectedCorrectness: null,
  selectedLength: null,

  async init() {
    app.bindEvents();
    await app.checkConnection();
    await app.startNewChat();
    app.autoResizeInput();
  },

  // Register button, keyboard, logout, and input-resize actions for the chat page.
  bindEvents() {
    document.getElementById('btn-send').addEventListener('click', app.handleSend);
    document.getElementById('btn-logout')?.addEventListener('click', app.handleLogout);
    document.getElementById('btn-chat-feedback').addEventListener('click', app.submitMandatoryFeedback);
    document.getElementById('message-input').addEventListener('keydown', event => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        app.handleSend();
      }
    });
    app.bindMandatoryFeedbackControls();
  },

  // FR12: collect the mandatory rating, correctness, and length selections.
  bindMandatoryFeedbackControls() {
    document.querySelectorAll('#chat-rating-group .star').forEach(star => {
      star.addEventListener('click', () => app.setRating(parseInt(star.dataset.value, 10)));
    });
    app.bindFeedbackOptionGroup('chat-correctness-group', 'selectedCorrectness');
    app.bindFeedbackOptionGroup('chat-length-group', 'selectedLength');
  },

  bindFeedbackOptionGroup(groupId, fieldName) {
    document.querySelectorAll(`#${groupId} .toggle-btn`).forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll(`#${groupId} .toggle-btn`).forEach(item => item.classList.remove('selected'));
        btn.classList.add('selected');
        app[fieldName] = btn.dataset.value;
      });
    });
  },

  setRating(value) {
    app.selectedRating = value;
    document.querySelectorAll('#chat-rating-group .star').forEach(star => {
      star.classList.toggle('active', parseInt(star.dataset.value, 10) <= value);
    });
  },

  autoResizeInput() {
    const input = document.getElementById('message-input');
    input.addEventListener('input', () => {
      input.style.height = 'auto';
      input.style.height = `${Math.min(input.scrollHeight, 160)}px`;
    });
  },

  // FR8: keep sending every message to the same session id until the user
  // starts a new chat, which enables continuous multi-turn conversation.
  async handleSend() {
    const input = document.getElementById('message-input');
    const content = input.value.trim();
    if (!content || app.isLoading) return;
    if (app.pendingFeedbackMessageId) {
      app.showMandatoryFeedback();
      return;
    }

    app.isLoading = true;
    input.value = '';
    input.style.height = 'auto';
    document.getElementById('btn-send').disabled = true;
    ui.appendMessage('user', content, null, new Date().toISOString());
    ui.showTyping();

    try {
      if (!app.currentSessionId) {
        const session = await api.createSession();
        app.currentSessionId = session.session_id;
      }
      const result = await api.sendMessage(content, app.currentSessionId);
      app.currentSessionId = result.session_id;
      ui.hideTyping();
      // FR9/FR10: display the generated LLaMA 3 response with its tracked response time.
      ui.appendMessage('assistant', result.response, result.message_id, result.timestamp, result.response_time_ms);
      app.requireFeedback(result.message_id);
    } catch (err) {
      ui.hideTyping();
      ui.appendMessage('assistant', `Error: ${err.message}. Please try again.`, null, new Date().toISOString());
    } finally {
      app.isLoading = false;
      app.setComposerLocked(false);
      input.focus();
    }
  },

  // FR12/FR13: track response feedback and require it before the next turn.
  requireFeedback(messageId) {
    app.pendingFeedbackMessageId = messageId;
    app.selectedRating = 0;
    app.selectedCorrectness = null;
    app.selectedLength = null;
    document.querySelectorAll('#chat-rating-group .star').forEach(star => star.classList.remove('active'));
    document.querySelectorAll('#mandatory-feedback .toggle-btn').forEach(btn => btn.classList.remove('selected'));
    document.getElementById('chat-feedback-status').textContent = '';
  },

  showMandatoryFeedback() {
    document.getElementById('mandatory-feedback').classList.remove('hidden');
    app.setComposerLocked(true);
  },

  // FR13: central input-control switch used to lock and unlock the chat.
  setComposerLocked(locked) {
    document.getElementById('message-input').disabled = locked;
    document.getElementById('btn-send').disabled = locked || app.isLoading;
  },

  // FR13: successful feedback completion unlocks chat input for the next turn.
  async submitMandatoryFeedback() {
    const statusEl = document.getElementById('chat-feedback-status');
    statusEl.textContent = '';
    statusEl.className = 'feedback-status';

    if (!app.selectedRating || !app.selectedCorrectness || !app.selectedLength) {
      statusEl.textContent = 'Select rating, correctness, and length.';
      statusEl.className = 'feedback-status error';
      return;
    }

    try {
      await api.submitFeedback({
        message_id: app.pendingFeedbackMessageId,
        session_id: app.currentSessionId,
        rating: app.selectedRating,
        correctness: app.selectedCorrectness,
        length_type: app.selectedLength,
      });
      app.pendingFeedbackMessageId = null;
      document.getElementById('mandatory-feedback').classList.add('hidden');
      app.setComposerLocked(false);
      document.getElementById('message-input').focus();
    } catch (err) {
      statusEl.textContent = err.message;
      statusEl.className = 'feedback-status error';
    }
  },

  // FR7/FR8: start a fresh independent multi-turn chat by asking the backend
  // for a unique session id.
  async startNewChat() {
    if (app.pendingFeedbackMessageId) return;
    ui.renderWelcome();
    document.getElementById('message-input').focus();
    try {
      const session = await api.createSession();
      app.currentSessionId = session.session_id;
    } catch {
      app.currentSessionId = null;
    }
  },

  sendSuggestion(text) {
    document.getElementById('message-input').value = text;
    app.handleSend();
  },

  async checkConnection() {
    try {
      const result = await api.checkHealth();
      ui.setConnectionStatus(result.status === 'ok', result.status === 'ok' ? 'Connected' : 'Limited');
    } catch {
      ui.setConnectionStatus(false, 'Offline');
    }
  },

  handleLogout(event) {
    event.preventDefault();
    window.location.href = '/auth/logout';
  },
};

window.app = app;

document.addEventListener('DOMContentLoaded', () => app.init());
