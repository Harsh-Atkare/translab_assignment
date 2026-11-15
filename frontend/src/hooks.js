import { useEffect, useRef, useState } from 'react';

export function useTheme() {
  const [theme, setTheme] = useState(() => {
    try {
      return localStorage.getItem('kb-theme') || 'light';
    } catch {
      return 'light';
    }
  });

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem('kb-theme', theme);
    } catch {
 
    }
  }, [theme]);

  return [theme, () => setTheme((t) => (t === 'light' ? 'dark' : 'light'))];
}

export function useTypewriter(text, { enabled = true, charsPerTick = 3, tickMs = 16 } = {}) {
  const [shown, setShown] = useState(enabled ? '' : text);
  const done = shown.length >= (text?.length || 0);

  useEffect(() => {
    if (!enabled || !text) {
      setShown(text || '');
      return;
    }

    setShown('');
    let i = 0;

    const id = setInterval(() => {
      i += charsPerTick;
      setShown(text.slice(0, i));
      if (i >= text.length) clearInterval(id);
    }, tickMs);

    return () => clearInterval(id);
  }, [text, enabled, charsPerTick, tickMs]);

  return { shown, done };
}

export function useElapsed(active) {
  const [seconds, setSeconds] = useState(0);
  const start = useRef(null);

  useEffect(() => {
    if (!active) {
      setSeconds(0);
      start.current = null;
      return;
    }

    start.current = Date.now();
    const id = setInterval(
      () => setSeconds(Math.round((Date.now() - start.current) / 1000)),
      250
    );
    return () => clearInterval(id);
  }, [active]);

  return seconds;
}
