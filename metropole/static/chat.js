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
  for (const source of sources) {
    const details = document.createElement('details');
    const summary = document.createElement('summary');
    summary.textContent = `[${source.number}] ${source.tag} · ${source.source.split(/[\\/]/).pop()}`;
    const excerpt = document.createElement('p');
    excerpt.textContent = source.excerpt;
    details.append(summary, excerpt);
    article.append(details);
  }
  messages.append(article);
  article.scrollIntoView({ block: 'end', behavior: 'smooth' });
  return article;
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
  try {
    const response = await fetch('/api/chat', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, history: history.slice(-12) }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Could not obtain an answer.');
    append('assistant', result.answer, result.sources);
    history.push({ role: 'user', content: question }, { role: 'assistant', content: result.answer.slice(0, 8000) });
    history = history.slice(-12);
  } catch (err) {
    error.textContent = err.message;
    userMessage.remove();
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
