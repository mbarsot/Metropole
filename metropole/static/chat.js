const form = document.querySelector('#chat-form');
const input = document.querySelector('#question');
const send = document.querySelector('#send');
const messages = document.querySelector('#messages');
const error = document.querySelector('#error');
let history = [];
let busy = false;

function append(role, text, sources = []) {
  const article = document.createElement('article');
  article.className = `message ${role}`;
  const label = document.createElement('h2');
  label.textContent = role === 'user' ? 'You' : 'Metropole';
  const content = document.createElement('p');
  content.textContent = text;
  article.append(label, content);
  addSources(article, sources);
  messages.append(article);
  article.scrollIntoView({ block: 'end', behavior: 'smooth' });
  return article;
}

function addSources(article, sources) {
  for (const source of sources) {
    const details = document.createElement('details');
    const summary = document.createElement('summary');
    summary.textContent = `[${source.number}] ${source.tag} · ${source.source.split(/[\\/]/).pop()}`;
    const excerpt = document.createElement('p');
    excerpt.textContent = source.excerpt;
    details.append(summary, excerpt);
    article.append(details);
  }
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (busy || !input.value.trim()) return;
  const question = input.value.trim();
  busy = true;
  send.disabled = true;
  document.querySelector('#reset').disabled = true;
  send.textContent = 'Thinking…';
  error.textContent = '';
  document.querySelector('#welcome')?.remove();
  const userMessage = append('user', question);
  input.value = '';
  let assistantMessage = null;
  let answer = '';
  let sources = [];
  let receivedToken = false;
  let completed = false;
  try {
    const response = await fetch('/api/chat', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, history: history.slice(-12), stream: true }),
    });
    if (!response.ok) {
      const result = await response.json();
      throw new Error(result.error || 'Could not obtain an answer.');
    }
    if (!response.body) throw new Error('Your browser does not support streamed responses.');
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let pending = '';
    function eventLine(line) {
      if (!line.trim()) return;
      if (completed) throw new Error('Unexpected data after answer completion.');
      const event = JSON.parse(line);
      if (event.type === 'error') throw new Error(event.error);
      if (event.type === 'metadata') {
        sources = event.sources;
        answer = event.prefix;
        assistantMessage = append('assistant', answer || 'Waiting for Ollama…');
      } else if (event.type === 'token') {
        if (!assistantMessage) throw new Error('Missing response metadata.');
        answer += event.text;
        receivedToken = true;
        assistantMessage.querySelector('p').textContent = answer;
        send.textContent = 'Receiving…';
        assistantMessage.scrollIntoView({ block: 'end', behavior: 'auto' });
      } else if (event.type === 'done') {
        completed = true;
      } else {
        throw new Error('Unexpected stream event.');
      }
    }
    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        pending += decoder.decode(value, { stream: true });
        const lines = pending.split('\n');
        pending = lines.pop();
        lines.forEach(eventLine);
      }
      pending += decoder.decode();
      if (pending.trim()) eventLine(pending);
      if (!completed || !receivedToken) throw new Error('The answer stream ended before completion. Please retry.');
    } finally {
      if (!completed) {
        try { await reader.cancel(); } catch (_) { /* Preserve the original error. */ }
      }
      reader.releaseLock();
    }
    addSources(assistantMessage, sources);
    history.push({ role: 'user', content: question }, { role: 'assistant', content: answer.slice(0, 8000) });
    history = history.slice(-12);
  } catch (err) {
    error.textContent = err.message;
    if (receivedToken) {
      const note = document.createElement('p');
      note.textContent = 'Incomplete answer — please retry.';
      assistantMessage.append(note);
    } else {
      assistantMessage?.remove();
      userMessage.remove();
    }
    input.value = question;
  } finally {
    busy = false;
    send.disabled = false;
    document.querySelector('#reset').disabled = false;
    send.textContent = 'Send ↑';
    input.focus();
  }
});

input.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); form.requestSubmit(); }
});
document.querySelector('#reset').addEventListener('click', () => {
  if (busy) return;
  history = [];
  messages.replaceChildren();
  error.textContent = '';
  input.value = '';
  input.focus();
});
document.querySelectorAll('[data-question]').forEach(button => {
  button.addEventListener('click', () => { input.value = button.dataset.question; input.focus(); });
});
document.querySelector('#check').addEventListener('click', async () => {
  const status = document.querySelector('#connection-status');
  const button = document.querySelector('#check');
  status.textContent = 'Checking…';
  button.disabled = true;
  try {
    const response = await fetch('/api/status');
    const result = await response.json();
    status.textContent = response.ok ? `Connected · ${result.model}` : result.error;
  } catch (err) { status.textContent = err.message; }
  finally { button.disabled = false; }
});
