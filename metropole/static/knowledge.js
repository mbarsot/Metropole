const knowledgeDialog = document.querySelector('#knowledge-dialog');
const knowledgeList = document.querySelector('#knowledge-list');
const knowledgeStatus = document.querySelector('#knowledge-status');
const uploadForm = document.querySelector('#upload-form');
const uploadSubmit = document.querySelector('#upload-submit');
const uploadStatus = document.querySelector('#upload-status');
const uploadResults = document.querySelector('#upload-results');
let uploading = false;

async function refreshKnowledge() {
  const button = document.querySelector('#refresh-knowledge');
  button.disabled = true;
  knowledgeStatus.textContent = 'Loading knowledge list…';
  try {
    const response = await fetch('/api/knowledge', { cache: 'no-store' });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Could not list knowledge.');
    knowledgeList.replaceChildren();
    document.querySelector('#procedure-count').textContent = data.procedures;
    knowledgeStatus.textContent = data.files.length
      ? `${data.files.length} files · ${data.procedures} skills`
      : 'No knowledge loaded yet. Choose documents above to get started.';
    for (const file of data.files) {
      const article = document.createElement('article');
      article.className = 'knowledge-file';
      const title = document.createElement('h4');
      title.textContent = file.filename;
      const source = document.createElement('p');
      source.textContent = file.source;
      const list = document.createElement('ul');
      for (const skill of file.skills) {
        const item = document.createElement('li');
        const tag = document.createElement('code');
        tag.textContent = `<${skill.tag}>`;
        item.append(tag, document.createTextNode(` · section ${skill.section} · ${skill.characters} characters`));
        list.append(item);
      }
      article.append(title, source, list);
      knowledgeList.append(article);
    }
  } catch (err) {
    knowledgeStatus.textContent = err.message;
  } finally {
    button.disabled = false;
  }
}

document.querySelector('#open-loader').addEventListener('click', () => {
  knowledgeDialog.showModal();
  document.querySelector('#loader-section').scrollIntoView({ block: 'start' });
  refreshKnowledge();
});
document.querySelector('#show-knowledge').addEventListener('click', async () => {
  knowledgeDialog.showModal();
  await refreshKnowledge();
  document.querySelector('#knowledge-section').scrollIntoView({ block: 'start' });
});
document.querySelector('#close-knowledge').addEventListener('click', () => knowledgeDialog.close());
document.querySelector('#refresh-knowledge').addEventListener('click', refreshKnowledge);

uploadForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (uploading) return;
  const selected = [
    ...document.querySelector('#document-files').files,
    ...document.querySelector('#document-folder').files,
  ];
  const supported = selected.filter(file => /\.(txt|md|docx)$/i.test(file.name) && !file.name.startsWith('~$'));
  const files = [...new Map(supported.map(file => [file.webkitRelativePath || file.name, file])).values()];
  if (!files.length) {
    uploadStatus.textContent = 'Choose at least one .txt, .md, or .docx file.';
    return;
  }
  if (files.length > 200 || files.reduce((total, file) => total + file.size, 0) >= 100 * 1024 * 1024) {
    uploadStatus.textContent = 'Choose fewer or smaller files: at most 200 files and under 100 MB per batch.';
    return;
  }
  const body = new FormData();
  files.forEach(file => body.append('files', file, file.webkitRelativePath || file.name));
  body.append('offline_tags', document.querySelector('#offline-tags').checked ? 'true' : 'false');
  uploading = true;
  uploadSubmit.disabled = true;
  uploadSubmit.textContent = 'Loading…';
  uploadResults.replaceChildren();
  const skipped = selected.length - supported.length;
  uploadStatus.textContent = `Uploading ${files.length} files…${skipped ? ` Skipped ${skipped} unsupported or temporary files.` : ''}`;
  let completed = false;
  try {
    const response = await fetch('/api/load', { method: 'POST', body });
    if (!response.ok) {
      const data = await response.json();
      throw new Error(data.error || 'Could not load documents.');
    }
    if (!response.body) throw new Error('Your browser does not support import progress streaming.');
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let pending = '';
    function eventLine(line) {
      if (!line.trim()) return;
      const item = JSON.parse(line);
      if (item.type === 'loading') {
        uploadStatus.textContent = `Loading ${item.filename}… Untagged notes may need time for AI labels.`;
      } else if (item.type === 'loaded' || item.type === 'failed') {
        const result = document.createElement('li');
        result.className = item.type === 'failed' ? 'import-failed' : '';
        result.textContent = item.type === 'loaded'
          ? `${item.filename}: ${item.procedures} skills — ${item.skills.map(tag => `<${tag}>`).join(', ')}`
          : `${item.filename}: ${item.error}`;
        uploadResults.append(result);
      } else if (item.type === 'done') {
        completed = true;
        uploadStatus.textContent = `Finished: ${item.loaded} files loaded, ${item.failed} failed.${skipped ? ` Skipped ${skipped} unsupported or temporary files.` : ''}`;
      } else {
        throw new Error('Unexpected import progress event.');
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
      if (!completed) throw new Error('Import progress was interrupted. Check loaded knowledge before retrying.');
    } finally {
      if (!completed) {
        try { await reader.cancel(); } catch (_) { /* Preserve the original error. */ }
      }
      reader.releaseLock();
    }
  } catch (err) {
    uploadStatus.textContent = err.message;
  } finally {
    uploading = false;
    uploadSubmit.disabled = false;
    uploadSubmit.textContent = 'Load selected documents';
    await refreshKnowledge();
  }
});
