import { useTypewriter } from '../hooks.js';
import Answer from './Answer.jsx';

function Sources({ sources }) {
  if (!sources?.length) return null;

  return (
    <div className="sources">
      <div className="sources-head">
        <span>Sources</span>
        <span className="line" />
        <span>{sources.length}</span>
      </div>

      {sources.map((s, i) => (
        <details className="source" key={i}>
          <summary>
            <span className="page">p. {s.page}</span>
            <span className="file">{s.filename}</span>
            <span className="score">{s.score}</span>
          </summary>
          <div className="excerpt">{s.excerpt}</div>
        </details>
      ))}
    </div>
  );
}

function Timings({ seconds, timings }) {
  if (!timings) return <div className="timings"><span>{seconds}s</span></div>;

  return (
    <div className="timings">
      <span><b>{seconds}s</b> total</span>
      <span>embed <b>{timings.embed}s</b></span>
      <span>search <b>{timings.search}s</b></span>
      <span>generate <b>{timings.generate}s</b></span>
    </div>
  );
}

export default function Entry({ entry, index, total }) {
  const { question, answer, sources, seconds, timings, error, pending } = entry;

  const animate = index === 0 && !error;
  const { shown, done } = useTypewriter(answer || '', { enabled: animate });

  return (
    <article className="entry">
      <div className="entry-index">
        {String(total - index).padStart(2, '0')}
      </div>

      <h3 className="question">{question}</h3>

      {pending ? (
        <div className="thinking">
          <span className="bead" />
          <span className="bead" />
          <span className="bead" />
          <span>Searching documents and drafting an answer…</span>
        </div>
      ) : (
        <div className={animate && !done ? 'typing' : undefined}>
          <Answer text={animate ? shown : answer} error={error} />
        </div>
      )}

      {!pending && !error && (
        <>
          <Sources sources={sources} />
          <Timings seconds={seconds} timings={timings} />
        </>
      )}
    </article>
  );
}
