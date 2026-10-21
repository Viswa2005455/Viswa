import { UnderDevelopment } from '../components/ui';

export const CodeLab = () => (
  <UnderDevelopment title="Data & Code Lab" phase="Phase 5"
    summary="Explain, review and (only with your approval) run Python, SQL and Java in an isolated sandbox."
    planned={['Code editor with syntax highlighting, search, diff view', 'Python/SQL/Java explanations and debugging',
      'Sandboxed execution: container isolation, no network, CPU/memory/time limits, explicit approval before every run',
      'Corrected-file export']}
    available={[{ to: '/upload', label: 'Upload code for a syntax check & outline' }]} />
);
