import { lazy } from 'react';
import { BrowserRouter, Route, Routes, Link } from 'react-router-dom';
import { Layout } from './components/Layout';
import { DCFModelProvider } from './lib/dcfModel';
import { SettingsProvider } from './lib/settings';
import { ToastProvider } from './lib/toast';
import { CodeLab, Assistant, Reports } from './pages/Planned';
import { AuthProvider, useAuth } from './lib/auth';
import { ProjectProvider } from './lib/project';
import { AuthScreen } from './pages/Auth';
import { Activity } from 'lucide-react';
import { EmptyState } from './components/ui';
import { Compass } from 'lucide-react';

const Overview = lazy(() => import('./pages/Overview').then((m) => ({ default: m.Overview })));
const UploadPage = lazy(() => import('./pages/Upload').then((m) => ({ default: m.UploadPage })));
const Forecasting = lazy(() => import('./pages/Forecasting').then((m) => ({ default: m.Forecasting })));
const Variance = lazy(() => import('./pages/Variance').then((m) => ({ default: m.Variance })));
const Ratios = lazy(() => import('./pages/Ratios').then((m) => ({ default: m.Ratios })));
const DCF = lazy(() => import('./pages/DCF').then((m) => ({ default: m.DCF })));
const Investment = lazy(() => import('./pages/Investment').then((m) => ({ default: m.Investment })));
const Scenarios = lazy(() => import('./pages/Scenarios').then((m) => ({ default: m.Scenarios })));
const Sensitivity = lazy(() => import('./pages/Sensitivity').then((m) => ({ default: m.Sensitivity })));
const Learning = lazy(() => import('./pages/Learning').then((m) => ({ default: m.Learning })));
const Budgeting = lazy(() => import('./pages/Budgeting').then((m) => ({ default: m.Budgeting })));
const Statements = lazy(() => import('./pages/Statements').then((m) => ({ default: m.Statements })));
const CashFlow = lazy(() => import('./pages/CashFlow').then((m) => ({ default: m.CashFlow })));
const Projects = lazy(() => import('./pages/Projects').then((m) => ({ default: m.Projects })));
const RedFlags = lazy(() => import('./pages/RedFlags').then((m) => ({ default: m.RedFlags })));
const ModelCheck = lazy(() => import('./pages/ModelCheck').then((m) => ({ default: m.ModelCheck })));
const Peers = lazy(() => import('./pages/Peers').then((m) => ({ default: m.Peers })));
const SettingsPage = lazy(() => import('./pages/Settings').then((m) => ({ default: m.SettingsPage })));

export function App() {
  return (
    <SettingsProvider>
      <ToastProvider>
        <AuthProvider>
          <Gate />
        </AuthProvider>
      </ToastProvider>
    </SettingsProvider>
  );
}

/** Everything except the sign-in screen requires an account. */
function Gate() {
  const { user, loading } = useAuth();
  if (loading) return <div className="splash"><div className="brand-mark" style={{ width: 44, height: 44 }}><Activity size={22} /></div></div>;
  if (!user) return <AuthScreen />;
  return (
    <ProjectProvider key={user.id}>
        <DCFModelProvider>
          <BrowserRouter>
            <Routes>
              <Route element={<Layout />}>
                <Route index element={<Overview />} />
                <Route path="projects" element={<Projects />} />
                <Route path="upload" element={<UploadPage />} />
                <Route path="budgeting" element={<Budgeting />} />
                <Route path="forecasting" element={<Forecasting />} />
                <Route path="variance" element={<Variance />} />
                <Route path="statements" element={<Statements />} />
                <Route path="ratios" element={<Ratios />} />
                <Route path="cash-flow" element={<CashFlow />} />
                <Route path="red-flags" element={<RedFlags />} />
                <Route path="model-check" element={<ModelCheck />} />
                <Route path="peers" element={<Peers />} />
                <Route path="scenarios" element={<Scenarios />} />
                <Route path="sensitivity" element={<Sensitivity />} />
                <Route path="dcf" element={<DCF />} />
                <Route path="investment" element={<Investment />} />
                <Route path="code-lab" element={<CodeLab />} />
                <Route path="assistant" element={<Assistant />} />
                <Route path="reports" element={<Reports />} />
                <Route path="learn" element={<Learning />} />
                <Route path="settings" element={<SettingsPage />} />
                <Route path="*" element={<EmptyState icon={<Compass size={22} />} title="Page not found" action={<Link className="btn" to="/">Go to Overview</Link>}>That address does not exist.</EmptyState>} />
              </Route>
            </Routes>
          </BrowserRouter>
        </DCFModelProvider>
    </ProjectProvider>
  );
}
