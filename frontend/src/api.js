const TIMEOUTS = {
  default: 30_000,
  ask: 300_000,
  upload: 600_000,
};


async function request(path, options = {}, timeout = TIMEOUTS.default) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);

  let res;
  try {
    res = await fetch(path, { ...options, signal: controller.signal });
  } catch (err) {
    if (err.name === 'AbortError') {
      throw new Error(
        `No response after ${Math.round(timeout / 1000)}s. Check that the ` +
          'server is still running.'
      );
    }
    throw new Error('Could not reach the server. Is it still running?');
  } finally {
    clearTimeout(timer);
  }

  let body = {};
  try {
    body = await res.json();
  } catch {

  }

  if (!res.ok) {
    throw new Error(body.detail || `Request failed (${res.status})`);
  }
  return body;
}

export const listDocuments = () => request('/api/documents');

export const uploadDocument = (file) => {
  const form = new FormData();
  form.append('file', file);
  return request('/api/documents', { method: 'POST', body: form }, TIMEOUTS.upload);
};

export const deleteDocument = (id) =>
  request(`/api/documents/${id}`, { method: 'DELETE' });

export const ask = (question) =>
  request(
    '/api/ask',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    },
    TIMEOUTS.ask
  );
