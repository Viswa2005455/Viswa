import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { setNumberStyle, type Currency, type NumberStyle, type UnitScale } from './format';
import { load, save } from './storage';

export type ThemePref = 'system' | 'dark' | 'light';
export interface Settings {
  theme: ThemePref;
  currency: Currency;
  units: UnitScale;
  reduceMotion: boolean;
  learningMode: boolean;
  periodFrom: string;
  periodTo: string;
  numberStyle: NumberStyle;
}

const DEFAULTS: Settings = {
  theme: 'system', currency: 'INR', units: 'lakhs', reduceMotion: false, learningMode: true,
  periodFrom: '2025-11', periodTo: '2026-10', numberStyle: 'auto',
};

interface Ctx { settings: Settings; update: (p: Partial<Settings>) => void; resolvedTheme: 'dark' | 'light' }
const SettingsContext = createContext<Ctx | null>(null);

function systemDark() {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-color-scheme: dark)').matches;
}

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<Settings>(() => {
    const s = { ...DEFAULTS, ...load('fis.settings', DEFAULTS) };
    setNumberStyle(s.numberStyle);
    return s;
  });
  const [sysDark, setSysDark] = useState(systemDark);

  useEffect(() => {
    const mq = window.matchMedia?.('(prefers-color-scheme: dark)');
    const on = () => setSysDark(mq.matches);
    mq?.addEventListener('change', on);
    return () => mq?.removeEventListener('change', on);
  }, []);

  const resolvedTheme = settings.theme === 'system' ? (sysDark ? 'dark' : 'light') : settings.theme;

  useEffect(() => {
    document.documentElement.dataset.theme = resolvedTheme;
    document.documentElement.dataset.motion = settings.reduceMotion ? 'reduce' : 'auto';
  }, [resolvedTheme, settings.reduceMotion]);

  const update = useCallback((p: Partial<Settings>) => {
    setSettings((s) => {
      const next = { ...s, ...p };
      setNumberStyle(next.numberStyle);
      save('fis.settings', next);
      return next;
    });
  }, []);

  const value = useMemo(() => ({ settings, update, resolvedTheme }), [settings, update, resolvedTheme]);
  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>;
}

export function useSettings() {
  const c = useContext(SettingsContext);
  if (!c) throw new Error('useSettings outside provider');
  return c;
}
