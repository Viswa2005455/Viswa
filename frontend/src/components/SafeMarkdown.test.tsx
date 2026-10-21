import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { SafeMarkdown } from './SafeMarkdown';

describe('SafeMarkdown', () => {
  it('renders headings, lists and bold', () => {
    const html = renderToStaticMarkup(<SafeMarkdown text={'## Summary\n- **ROE** rose\n- margin fell\n\n1. first\n2. second'} />);
    expect(html).toContain('<h4 class="md-h">Summary</h4>');
    expect(html).toContain('<li><b>ROE</b> rose</li>');
    expect(html).toContain('<ol><li>first</li><li>second</li></ol>');
  });

  it('never turns model output into HTML', () => {
    const html = renderToStaticMarkup(<SafeMarkdown text={'<script>alert(1)</script> <img src=x onerror=alert(1)> **<b>x</b>**'} />);
    expect(html).not.toContain('<script>');
    expect(html).not.toContain('<img');
    expect(html).toContain('&lt;script&gt;');
  });
});
