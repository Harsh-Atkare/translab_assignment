import { useCallback, useEffect, useState } from 'react';

import { ask, listDocuments } from './api.js';
import DocumentRail from './components/DocumentRail.jsx';
import Entry from './components/Entry.jsx';
import Toast from './components/Toast.jsx';
import { useTheme } from './hooks.js';

const SUGGESTIONS = [
  'Summarise this document',
  'What are the key requirements?',
  'What dates or deadlines are mentioned?',
];

function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
         strokeLinecap="round">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
         strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" />
    </svg>
  );
}

export default function App() {
  const [theme, toggleTheme] = useTheme();
  const [documents, setDocuments] = useState([]);
  const [totalChunks, setTotalChunks] = useState(0);
  const [question, setQuestion] = useState('');
  const [entries, setEntries] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const refresh = useCallback(async () => {
    try {
      const data = await listDocuments();
      setDocuments(data.documents);
      setTotalChunks(data.total_chunks);
    } catch {

    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function submit(text) {
    const q = (text ?? question).trim();
    if (!q || busy) return;

    setBusy(true);
    setQuestion('');


    setEntries((prev) => [{ question: q, pending: true }, ...prev]);

    try {
      const r = await ask(q);
      setEntries((prev) => [
        {
          question: q,
          answer: r.answer || 'The model returned an empty answer.',
          sources: r.sources,
          seconds: r.seconds,
          timings: r.timings,
        },
        ...prev.slice(1),
      ]);
    } catch (err) {


      setError(err.message);
      setEntries((prev) => prev.slice(1));
      setQuestion(q);
    } finally {
      setBusy(false);
    }
  }

  const hasDocs = documents.length > 0;

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <h1>Knowledge Assistant</h1>
          <span className="rule" />
          <span className="kicker">Ask your documents</span>
        </div>

        <button
          className="theme-toggle"
          onClick={toggleTheme}
          aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} theme`}
        >
          {theme === 'light' ? <MoonIcon /> : <SunIcon />}
          {theme === 'light' ? 'Dark' : 'Light'}
        </button>
      </header>

      <div className="layout">
        <DocumentRail
          documents={documents}
          totalChunks={totalChunks}
          onChanged={refresh}
          onError={setError}
        />

        <main className="main">
          <form
            className="ask"
            onSubmit={(e) => {
              e.preventDefault();
              submit();
            }}
          >
            <div className="ask-row">
              <input
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder={
                  hasDocs
                    ? 'Ask a question about your documents…'
                    : 'Upload a PDF first'
                }
                disabled={!hasDocs || busy}
              />
              <button className="btn" type="submit" disabled={!hasDocs || busy}>
                {busy ? 'Asking…' : 'Ask'}
              </button>
            </div>

            {hasDocs && entries.length === 0 && (
              <div className="suggestions">
                {SUGGESTIONS.map((s) => (
                  <button key={s} type="button" onClick={() => submit(s)}>
                    {s}
                  </button>
                ))}
              </div>
            )}
          </form>

          {entries.length > 0 ? (
            <div className="results">
              {entries.map((entry, i) => (
                <Entry
                  key={entries.length - i}
                  entry={entry}
                  index={i}
                  total={entries.length}
                />
              ))}
            </div>
          ) : (
            <div className="empty">
              <h2>{hasDocs ? 'Ready when you are' : 'No documents yet'}</h2>
              <p>
                {hasDocs
                  ? 'Answers are drawn only from the sources on the left, with the page they came from.'
                  : 'Add a text-based PDF from the panel on the left to get started.'}
              </p>
            </div>
          )}
        </main>
      </div>

      <Toast message={error} onClose={() => setError(null)} />
    </div>
  );
}
