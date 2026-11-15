import { useRef, useState } from 'react';

import { uploadDocument } from '../api.js';
import { useElapsed } from '../hooks.js';

const STAGES = [
  { label: 'Extracting text', after: 0 },
  { label: 'Splitting into chunks', after: 2 },
  { label: 'Generating embeddings', after: 4 },
  { label: 'Writing to vector store', after: 12 },
];

export default function UploadPanel({ onIndexed, onError }) {
  const inputRef = useRef(null);
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState(null);

  const elapsed = useElapsed(busy);
  const stageIndex = STAGES.reduce(
    (acc, s, i) => (elapsed >= s.after ? i : acc),
    0
  );

  async function send(file) {
    if (!file) return;

    if (!file.name.toLowerCase().endsWith('.pdf')) {
      return setFlash({ kind: 'error', text: 'Only PDF files are accepted.' });
    }

    setBusy(true);
    setFlash(null);

    try {
      const r = await uploadDocument(file);
      setFlash({
        kind: 'ok',
        text: `${r.filename} — ${r.pages} pages, ${r.chunks} chunks in ${r.seconds}s`,
      });
      onIndexed();
    } catch (err) {
      setFlash({ kind: 'error', text: err.message });
      onError?.(err.message);
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = ''; // allow re-upload
    }
  }

  function onDrop(e) {
    e.preventDefault();
    setOver(false);
    if (!busy) send(e.dataTransfer.files[0]);
  }

  return (
    <div>
      <div
        className={`dropzone${over ? ' over' : ''}${busy ? ' busy' : ''}`}
        onClick={() => !busy && inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
      >
        {busy ? (
          <>
            <div className="progress"><span /></div>
            <ul className="stage-list">
              {STAGES.map((s, i) => (
                <li
                  key={s.label}
                  className={i === stageIndex ? 'active' : i < stageIndex ? 'done' : ''}
                >
                  <span className="dot" />
                  {s.label}
                </li>
              ))}
            </ul>
            <div className="elapsed">{elapsed}s elapsed</div>
          </>
        ) : (
          <>
            <div className="icon">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none"
                   stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
                <path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5" />
                <path d="M4 16v2.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V16" />
              </svg>
            </div>
            <p className="lead">Drop a PDF</p>
            <p className="hint">or click to browse · max 20 MB</p>
          </>
        )}
      </div>

      <input
        ref={inputRef}
        type="file"
        accept="application/pdf"
        hidden
        onChange={(e) => send(e.target.files[0])}
      />

      {flash && (
        <div className={`flash${flash.kind === 'error' ? ' error' : ''}`}>
          {flash.text}
        </div>
      )}
    </div>
  );
}
