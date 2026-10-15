import { Fragment, useMemo, type ReactNode } from 'react';

const KEYWORDS: Record<string, string[]> = {
  python: ['def', 'class', 'import', 'from', 'as', 'return', 'if', 'elif', 'else', 'for', 'while', 'in', 'not', 'and', 'or', 'try', 'except', 'finally', 'with', 'lambda', 'yield', 'None', 'True', 'False', 'pass', 'raise', 'is', 'async', 'await'],
  sql: ['select', 'from', 'where', 'join', 'left', 'right', 'inner', 'outer', 'on', 'group', 'by', 'order', 'having', 'with', 'as', 'insert', 'into', 'update', 'delete', 'create', 'table', 'over', 'partition', 'and', 'or', 'not', 'null', 'case', 'when', 'then', 'else', 'end', 'limit', 'distinct', 'union', 'sum', 'count', 'avg'],
  java: ['public', 'private', 'protected', 'class', 'interface', 'static', 'void', 'int', 'double', 'new', 'return', 'if', 'else', 'for', 'while', 'try', 'catch', 'throw', 'throws', 'import', 'package', 'extends', 'implements', 'final', 'String', 'boolean', 'null', 'true', 'false'],
  js: ['const', 'let', 'var', 'function', 'return', 'if', 'else', 'for', 'while', 'import', 'export', 'from', 'class', 'new', 'async', 'await', 'null', 'undefined', 'true', 'false', 'interface', 'type'],
};

function langOf(ext: string): keyof typeof KEYWORDS | null {
  if (['.py', '.ipynb'].includes(ext)) return 'python';
  if (ext === '.sql') return 'sql';
  if (ext === '.java') return 'java';
  if (['.js', '.jsx', '.ts', '.tsx'].includes(ext)) return 'js';
  return null;
}

/**
 * Lightweight read-only highlighter (keywords, strings, comments, numbers). Text is rendered as
 * React text nodes — never as HTML — so uploaded content cannot inject markup.
 */
function highlightLine(line: string, lang: keyof typeof KEYWORDS | null): ReactNode[] {
  if (!lang) return [line];
  const kw = new Set(KEYWORDS[lang]);
  const re = new RegExp(`(${lang === 'sql' ? '--' : lang === 'python' ? '#' : '//'}.*$)|("(?:[^"\\\\]|\\\\.)*"|'(?:[^'\\\\]|\\\\.)*')|(\\b\\d+(?:\\.\\d+)?\\b)|([A-Za-z_]\\w*)`, 'g');
  const out: ReactNode[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(line))) {
    if (m.index > last) out.push(line.slice(last, m.index));
    const [tok] = m;
    if (m[1]) out.push(<span key={i++} className="tok-c">{tok}</span>);
    else if (m[2]) out.push(<span key={i++} className="tok-s">{tok}</span>);
    else if (m[3]) out.push(<span key={i++} className="tok-n">{tok}</span>);
    else if (kw.has(lang === 'sql' ? tok.toLowerCase() : tok)) out.push(<span key={i++} className="tok-k">{tok}</span>);
    else out.push(tok);
    last = m.index + tok.length;
  }
  if (last < line.length) out.push(line.slice(last));
  return out;
}

export function CodeView({ text, ext, errorLines = [], maxLines = 2000 }: { text: string; ext: string; errorLines?: number[]; maxLines?: number }) {
  const lines = useMemo(() => text.split('\n').slice(0, maxLines), [text, maxLines]);
  const lang = langOf(ext);
  const errs = new Set(errorLines);
  return (
    <div className="code-view" role="region" aria-label="Code preview" tabIndex={0}>
      <div className="gutter">{lines.map((_, i) => i + 1).join('\n')}</div>
      <pre>
        {lines.map((l, i) => (
          <Fragment key={i}>
            {errs.has(i + 1) ? <span className="hl-err">{highlightLine(l, lang)}</span> : highlightLine(l, lang)}
            {'\n'}
          </Fragment>
        ))}
      </pre>
    </div>
  );
}
