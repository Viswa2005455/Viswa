export interface DCFModel {
  base_revenue: number;
  revenue_growth: number[];
  ebit_margin: number[];
  tax_rate: number;
  da_pct_revenue: number;
  capex_pct_revenue: number;
  nwc_pct_revenue: number;
  wacc: number;
  terminal_growth: number;
  terminal_method: 'gordon' | 'exit_multiple';
  exit_multiple: number | null;
  debt: number;
  cash: number;
  shares_outstanding: number | null;
  mid_year: boolean;
}

export interface DCFYear {
  year: number; revenue: number; revenue_growth: number; ebit: number; ebit_margin: number; taxes: number; nopat: number;
  da: number; ebitda: number; capex: number; delta_nwc: number; fcff: number; discount_period: number;
  discount_factor: number; pv_fcff: number;
}

export interface DCFResult {
  years: DCFYear[];
  sum_pv_fcff: number;
  terminal_value: number;
  pv_terminal_value: number;
  enterprise_value: number;
  net_debt: number;
  equity_value: number;
  value_per_share: number | null;
  terminal_value_share_of_ev: number | null;
  implied_exit_multiple: number | null;
  implied_terminal_growth: number | null;
  warnings: string[];
}

export interface UploadSummary {
  id: string; name: string; extension: string; category: string; label: string; size: number; uploaded_at: string;
  status: 'processed' | 'failed'; error: string | null; summary: string;
  recommendations: { module: string; route: string; reason: string; confidence: 'high' | 'medium' | 'low' }[];
}

export interface Series {
  upload_id: string; file: string; sheet: string; series_id: string; label: string; orientation: 'row' | 'column';
  values: number[]; period_labels: string[]; refs: string[]; source: string;
}
