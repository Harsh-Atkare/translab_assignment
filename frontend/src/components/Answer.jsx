import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const CITATION = /(\[pages?\s+[\d,\s-]+\])/gi;
function decorate(children) {
  return Array.isArray(children)
    ? children.map((child, i) => decorateOne(child, i))
    : decorateOne(children, 0);
}

function decorateOne(child, key) {
  if (typeof child !== 'string') return child;

  const parts = child.split(CITATION);
  if (parts.length === 1) return child;

  return parts.map((part, i) =>
    CITATION.test(part) ? (
      <span className="cite" key={`${key}-${i}`}>{part.replace(/[[\]]/g, '')}</span>
    ) : (
      part
    )
  );
}

function CodeBlock({ children }) {
  const [copied, setCopied] = useState(false);
  const text = String(children).replace(/\n$/, '');

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {

    }
  }

  return (
    <div className="codeblock">
      <button className="copy" onClick={copy} type="button">
        {copied ? 'Copied' : 'Copy'}
      </button>
      <pre><code>{text}</code></pre>
    </div>
  );
}

const components = {
  p: ({ children }) => <p>{decorate(children)}</p>,
  li: ({ children }) => <li>{decorate(children)}</li>,
  strong: ({ children }) => <strong>{decorate(children)}</strong>,
  em: ({ children }) => <em>{decorate(children)}</em>,
  td: ({ children }) => <td>{decorate(children)}</td>,
  code: ({ inline, children, ...rest }) =>
    inline ? <code {...rest}>{children}</code> : <CodeBlock>{children}</CodeBlock>,

  pre: ({ children }) => children,

  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noreferrer noopener">{children}</a>
  ),
};

function balanceFences(text) {
  const fences = (text.match(/```/g) || []).length;
  return fences % 2 === 1 ? `${text}\n\`\`\`` : text;
}

export default function Answer({ text, error }) {
  if (error) return <p className="answer error">{text}</p>;

  return (
    <div className="answer markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {balanceFences(text || '')}
      </ReactMarkdown>
    </div>
  );
}
