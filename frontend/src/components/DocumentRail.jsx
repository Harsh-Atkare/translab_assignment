import { deleteDocument } from '../api.js';
import UploadPanel from './UploadPanel.jsx';

export default function DocumentRail({ documents, totalChunks, onChanged, onError }) {
  async function remove(id) {
    try {
      await deleteDocument(id);
      onChanged();
    } catch (err) {
      onError(err.message);
    }
  }

  return (
    <aside className="rail">
      <h2 className="rail-title">
        Sources
        {documents.length > 0 && (
          <span className="count">{totalChunks} chunks</span>
        )}
      </h2>

      <UploadPanel onIndexed={onChanged} onError={onError} />

      {documents.length > 0 ? (
        <ul className="doclist">
          {documents.map((doc) => (
            <li key={doc.doc_id}>
              <span className="name" title={doc.filename}>{doc.filename}</span>
              <span className="chunks">{doc.chunks}</span>
              <button
                className="remove"
                title="Remove"
                aria-label={`Remove ${doc.filename}`}
                onClick={() => remove(doc.doc_id)}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="rail-empty">
          Nothing indexed yet. Upload a text-based PDF to start asking
          questions against it.
        </p>
      )}
    </aside>
  );
}
