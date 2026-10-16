import {
  LayoutDashboard, FolderKanban, Wallet, TrendingUp, GitCompareArrows, FileSpreadsheet, Percent, Layers, SlidersHorizontal,
  Calculator, Landmark, Droplets, UploadCloud, Code2, Bot, FileText, GraduationCap, Settings as SettingsIcon, ShieldAlert, Users, FileSearch,
  type LucideIcon,
} from 'lucide-react';

export interface NavItem { to: string; label: string; icon: LucideIcon; ready: boolean; group: string }

/** `ready: false` marks modules that are clearly labelled "Under development" in the UI. */
export const NAV: NavItem[] = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, ready: true, group: 'Workspace' },
  { to: '/projects', label: 'My Projects', icon: FolderKanban, ready: true, group: 'Workspace' },
  { to: '/upload', label: 'Upload & Analyse', icon: UploadCloud, ready: true, group: 'Workspace' },
  { to: '/budgeting', label: 'Budgeting', icon: Wallet, ready: true, group: 'Planning' },
  { to: '/forecasting', label: 'Forecasting', icon: TrendingUp, ready: true, group: 'Planning' },
  { to: '/variance', label: 'Variance Analysis', icon: GitCompareArrows, ready: true, group: 'Planning' },
  { to: '/statements', label: 'Financial Statements', icon: FileSpreadsheet, ready: true, group: 'Analysis' },
  { to: '/ratios', label: 'Ratio Analysis', icon: Percent, ready: true, group: 'Analysis' },
  { to: '/cash-flow', label: 'Cash Flow & Working Capital', icon: Droplets, ready: true, group: 'Analysis' },
  { to: '/red-flags', label: 'Red-Flag Detector', icon: ShieldAlert, ready: true, group: 'Analysis' },
  { to: '/peers', label: 'Peer Comparison', icon: Users, ready: true, group: 'Analysis' },
  { to: '/scenarios', label: 'Scenario Planning', icon: Layers, ready: true, group: 'Valuation & risk' },
  { to: '/sensitivity', label: 'Sensitivity Analysis', icon: SlidersHorizontal, ready: true, group: 'Valuation & risk' },
  { to: '/dcf', label: 'DCF Valuation', icon: Landmark, ready: true, group: 'Valuation & risk' },
  { to: '/investment', label: 'Investment Appraisal', icon: Calculator, ready: true, group: 'Valuation & risk' },
  { to: '/model-check', label: 'Excel Model Checker', icon: FileSearch, ready: true, group: 'Tools' },
  { to: '/code-lab', label: 'Data & Code Lab', icon: Code2, ready: false, group: 'Tools' },
  { to: '/assistant', label: 'AI Finance Assistant', icon: Bot, ready: false, group: 'Tools' },
  { to: '/reports', label: 'Reports & Exports', icon: FileText, ready: false, group: 'Tools' },
  { to: '/learn', label: 'Learning Centre', icon: GraduationCap, ready: true, group: 'Learn' },
  { to: '/settings', label: 'Settings', icon: SettingsIcon, ready: true, group: 'Learn' },
];
