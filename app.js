'use strict';

const STORAGE_KEY = 'viswa-finance-v1';

const CATEGORIES = {
  expense: [
    { name: 'Food', color: '#e0574a' },
    { name: 'Rent', color: '#7a5af5' },
    { name: 'Transport', color: '#2f6fed' },
    { name: 'Shopping', color: '#d9488f' },
    { name: 'Bills', color: '#e08a1e' },
    { name: 'Health', color: '#1c9c8c' },
    { name: 'Entertainment', color: '#c25ad9' },
    { name: 'Education', color: '#3b8f3b' },
    { name: 'Other', color: '#7b8494' },
  ],
  income: [
    { name: 'Salary', color: '#128a4b' },
    { name: 'Freelance', color: '#2fa36b' },
    { name: 'Investments', color: '#1c7c9c' },
    { name: 'Gift', color: '#8a9a2a' },
    { name: 'Other income', color: '#5f8a6f' },
  ],
};

const CURRENCY_LOCALE = { INR: 'en-IN', USD: 'en-US', EUR: 'de-DE', GBP: 'en-GB', JPY: 'ja-JP' };

// ---------- state ----------

const defaultState = () => ({ transactions: [], budgets: {}, currency: 'INR' });

function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaultState();
    return { ...defaultState(), ...JSON.parse(raw) };
  } catch {
    return defaultState();
  }
}

function saveState() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    toast('Could not save — browser storage is unavailable');
  }
}

let state = loadState();
let editingId = null;
let editingBudgets = false;

// ---------- helpers ----------

const $ = (sel) => document.querySelector(sel);
const pad = (n) => String(n).padStart(2, '0');
const todayISO = () => {
  const d = new Date();
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
};
const monthOf = (iso) => iso.slice(0, 7);
const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 8);

function shiftMonth(key, delta) {
  const [y, m] = key.split('-').map(Number);
  const d = new Date(y, m - 1 + delta, 1);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`;
}

function monthLabel(key, opts = { month: 'short' }) {
  const [y, m] = key.split('-').map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString(undefined, opts);
}

function money(n, { sign = false } = {}) {
  const fmt = new Intl.NumberFormat(CURRENCY_LOCALE[state.currency] || undefined, {
    style: 'currency',
    currency: state.currency,
    maximumFractionDigits: state.currency === 'JPY' ? 0 : 2,
  });
  const s = fmt.format(Math.abs(n));
  if (!sign) return n < 0 ? `−${s}` : s;
  return (n < 0 ? '−' : '+') + s;
}

function escapeHTML(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
}

function categoryColor(type, name) {
  return (CATEGORIES[type] || []).find((c) => c.name === name)?.color || '#7b8494';
}

function totalsFor(month) {
  let income = 0, expense = 0;
  for (const t of state.transactions) {
    if (monthOf(t.date) !== month) continue;
    if (t.type === 'income') income += t.amount; else expense += t.amount;
  }
  return { income, expense };
}

let toastTimer;
function toast(msg) {
  const el = $('#toast');
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 2200);
}

function download(filename, content, type) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = Object.assign(document.createElement('a'), { href: url, download: filename });
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ---------- rendering ----------

const monthInput = $('#month');
const currentMonth = () => monthInput.value || monthOf(todayISO());

function render() {
  renderSummary();
  renderDonut();
  renderTrend();
  renderBudgets();
  renderTransactions();
}

function renderSummary() {
  const month = currentMonth();
  const balance = state.transactions.reduce((s, t) => s + (t.type === 'income' ? t.amount : -t.amount), 0);
  const { income, expense } = totalsFor(month);
  const prev = totalsFor(shiftMonth(month, -1));

  $('#stat-balance').textContent = money(balance);
  $('#stat-balance').className = 'amount ' + (balance < 0 ? 'negative' : '');
  $('#stat-income').textContent = money(income);
  $('#stat-expense').textContent = money(expense);

  const label = monthLabel(month, { month: 'long', year: 'numeric' });
  $('#stat-income-sub').textContent = compareText(label, income, prev.income);
  $('#stat-expense-sub').textContent = compareText(label, expense, prev.expense);

  const rate = income > 0 ? Math.round(((income - expense) / income) * 100) : null;
  const el = $('#stat-savings');
  el.textContent = rate === null ? '—' : `${rate}%`;
  el.className = 'amount ' + (rate === null ? '' : rate < 0 ? 'negative' : 'positive');
}

function compareText(label, cur, prev) {
  if (!prev) return label;
  const pct = Math.round(((cur - prev) / prev) * 100);
  return `${label} · ${pct >= 0 ? '▲' : '▼'} ${Math.abs(pct)}% vs last month`;
}

function renderDonut() {
  const month = currentMonth();
  const byCat = new Map();
  for (const t of state.transactions) {
    if (t.type !== 'expense' || monthOf(t.date) !== month) continue;
    byCat.set(t.category, (byCat.get(t.category) || 0) + t.amount);
  }
  const entries = [...byCat.entries()].sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((s, [, v]) => s + v, 0);

  const svg = $('#donut');
  const legend = $('#donut-legend');
  const r = 46, c = 2 * Math.PI * r;
  let offset = 0;
  let arcs = `<circle cx="60" cy="60" r="${r}" fill="none" stroke="var(--surface-2)" stroke-width="16"/>`;
  for (const [name, v] of entries) {
    const len = (v / total) * c;
    // 1px gap between segments when there is more than one
    const dash = entries.length > 1 ? Math.max(len - 1, 0.1) : len;
    arcs += `<circle cx="60" cy="60" r="${r}" fill="none" stroke="${categoryColor('expense', name)}" stroke-width="16"
      stroke-dasharray="${dash} ${c - dash}" stroke-dashoffset="${-offset}" transform="rotate(-90 60 60)"><title>${escapeHTML(name)}: ${money(v)}</title></circle>`;
    offset += len;
  }
  arcs += `<text x="60" y="58" text-anchor="middle" class="donut-total">${total ? money(total) : '—'}</text>
    <text x="60" y="70" text-anchor="middle" class="donut-label">spent</text>`;
  svg.innerHTML = arcs;

  legend.innerHTML = entries.length
    ? entries.map(([name, v]) => `<li><i class="dot" style="background:${categoryColor('expense', name)}"></i>${escapeHTML(name)}
        <span class="val">${money(v)} · ${Math.round((v / total) * 100)}%</span></li>`).join('')
    : '<li class="empty">No expenses this month.</li>';
}

function renderTrend() {
  const month = currentMonth();
  const months = Array.from({ length: 6 }, (_, i) => shiftMonth(month, i - 5));
  const data = months.map((m) => ({ m, ...totalsFor(m) }));
  const max = Math.max(1, ...data.flatMap((d) => [d.income, d.expense]));
  $('#trend').innerHTML = data.map((d) => `
    <div class="col${d.m === month ? ' current' : ''}">
      <div class="bars">
        <div class="bar income" style="height:${(d.income / max) * 100}%" title="Income ${money(d.income)}"></div>
        <div class="bar expense" style="height:${(d.expense / max) * 100}%" title="Expenses ${money(d.expense)}"></div>
      </div>
      <span class="lbl">${monthLabel(d.m)}</span>
    </div>`).join('');
}

function renderBudgets() {
  const list = $('#budgets');
  const form = $('#budget-form');
  list.hidden = editingBudgets;
  form.hidden = !editingBudgets;
  $('#edit-budgets').hidden = editingBudgets;

  if (editingBudgets) {
    form.innerHTML = CATEGORIES.expense.map((c) => `
      <label for="b-${c.name}">${c.name}</label>
      <input id="b-${c.name}" type="number" min="0" step="1" name="${c.name}" value="${state.budgets[c.name] ?? ''}" placeholder="No limit">`).join('')
      + `<div class="form-actions"><button class="btn primary" type="submit">Save budgets</button>
         <button class="btn" type="button" id="cancel-budgets">Cancel</button></div>`;
    $('#cancel-budgets').onclick = () => { editingBudgets = false; renderBudgets(); };
    return;
  }

  const month = currentMonth();
  const spent = {};
  for (const t of state.transactions) {
    if (t.type === 'expense' && monthOf(t.date) === month) spent[t.category] = (spent[t.category] || 0) + t.amount;
  }
  const rows = Object.entries(state.budgets).filter(([, limit]) => limit > 0);
  list.innerHTML = rows.length
    ? rows.map(([name, limit]) => {
        const s = spent[name] || 0;
        const pct = (s / limit) * 100;
        const cls = pct > 100 ? 'over' : pct >= 80 ? 'warn' : '';
        const left = limit - s;
        return `<li>
          <div class="budget-row"><span>${escapeHTML(name)}</span>
            <span class="val">${money(s)} / ${money(limit)} · ${left >= 0 ? `${money(left)} left` : `${money(-left)} over`}</span></div>
          <div class="meter ${cls}" role="progressbar" aria-label="${escapeHTML(name)} budget used"
            aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.min(100, Math.round(pct))}"><i style="width:${Math.min(100, pct)}%"></i></div>
        </li>`;
      }).join('')
    : '<li class="empty">No budgets set. Click Edit to add monthly limits.</li>';
}

function renderTransactions() {
  const month = currentMonth();
  const q = $('#search').value.trim().toLowerCase();
  const type = $('#filter-type').value;
  const items = state.transactions
    .filter((t) => monthOf(t.date) === month)
    .filter((t) => type === 'all' || t.type === type)
    .filter((t) => !q || t.note.toLowerCase().includes(q) || t.category.toLowerCase().includes(q))
    .sort((a, b) => b.date.localeCompare(a.date) || b.created - a.created);

  $('#tx-list').innerHTML = items.map((t) => {
    const color = categoryColor(t.type, t.category);
    const date = new Date(t.date + 'T00:00').toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
    return `<li data-id="${t.id}">
      <span class="tx-icon" style="background:${color}" aria-hidden="true">${escapeHTML(t.category[0])}</span>
      <div class="tx-main">
        <div class="tx-title">${escapeHTML(t.note || t.category)}</div>
        <div class="tx-meta">${escapeHTML(t.category)} · ${date}</div>
      </div>
      <span class="tx-amt ${t.type === 'income' ? 'positive' : 'negative'}">${money(t.type === 'income' ? t.amount : -t.amount, { sign: true })}</span>
      <div class="tx-actions">
        <button class="icon-btn" data-action="edit" aria-label="Edit">Edit</button>
        <button class="icon-btn" data-action="delete" aria-label="Delete">Delete</button>
      </div>
    </li>`;
  }).join('');
  const empty = $('#tx-empty');
  empty.hidden = items.length > 0;
  empty.textContent = q || type !== 'all' ? 'No matching transactions.' : 'No transactions for this month yet.';
}

// ---------- form ----------

const form = $('#tx-form');

function fillCategories(type, selected) {
  const sel = $('#category-select');
  sel.innerHTML = CATEGORIES[type].map((c) => `<option${c.name === selected ? ' selected' : ''}>${c.name}</option>`).join('');
}

function resetForm() {
  editingId = null;
  form.reset();
  form.date.value = todayISO();
  fillCategories('expense');
  $('#submit-btn').textContent = 'Add';
  $('#cancel-edit').hidden = true;
}

form.addEventListener('change', (e) => {
  if (e.target.name === 'type') fillCategories(e.target.value);
});

form.addEventListener('submit', (e) => {
  e.preventDefault();
  const amount = Math.round(parseFloat(form.amount.value) * 100) / 100;
  if (!(amount > 0)) return toast('Enter an amount greater than zero');
  const tx = {
    type: form.type.value,
    amount,
    category: form.category.value,
    date: form.date.value,
    note: form.note.value.trim(),
  };
  if (editingId) {
    const existing = state.transactions.find((t) => t.id === editingId);
    Object.assign(existing, tx);
    toast('Transaction updated');
  } else {
    state.transactions.push({ id: uid(), created: Date.now(), ...tx });
    toast(tx.type === 'income' ? 'Income added' : 'Expense added');
  }
  saveState();
  // jump to the month of the saved transaction so it's visible
  monthInput.value = monthOf(tx.date);
  resetForm();
  render();
});

$('#cancel-edit').addEventListener('click', resetForm);

$('#tx-list').addEventListener('click', (e) => {
  const btn = e.target.closest('button[data-action]');
  if (!btn) return;
  const id = btn.closest('li').dataset.id;
  const tx = state.transactions.find((t) => t.id === id);
  if (!tx) return;
  if (btn.dataset.action === 'delete') {
    if (!confirm(`Delete this ${tx.type} of ${money(tx.amount)}?`)) return;
    state.transactions = state.transactions.filter((t) => t.id !== id);
    if (editingId === id) resetForm();
    saveState();
    render();
    toast('Transaction deleted');
  } else {
    editingId = id;
    form.type.value = tx.type;
    fillCategories(tx.type, tx.category);
    form.amount.value = tx.amount;
    form.date.value = tx.date;
    form.note.value = tx.note;
    $('#submit-btn').textContent = 'Save';
    $('#cancel-edit').hidden = false;
    form.scrollIntoView({ behavior: 'smooth', block: 'center' });
    form.amount.focus({ preventScroll: true });
  }
});

// ---------- budgets ----------

$('#edit-budgets').addEventListener('click', () => { editingBudgets = true; renderBudgets(); });

$('#budget-form').addEventListener('submit', (e) => {
  e.preventDefault();
  const budgets = {};
  for (const input of e.target.querySelectorAll('input')) {
    const v = parseFloat(input.value);
    if (v > 0) budgets[input.name] = v;
  }
  state.budgets = budgets;
  editingBudgets = false;
  saveState();
  renderBudgets();
  toast('Budgets saved');
});

// ---------- toolbar ----------

monthInput.addEventListener('change', render);
$('#search').addEventListener('input', renderTransactions);
$('#filter-type').addEventListener('change', renderTransactions);

$('#currency').addEventListener('change', (e) => {
  state.currency = e.target.value;
  saveState();
  render();
});

$('#export-csv').addEventListener('click', () => {
  const rows = [['Date', 'Type', 'Category', 'Amount', 'Note']];
  for (const t of [...state.transactions].sort((a, b) => a.date.localeCompare(b.date))) {
    rows.push([t.date, t.type, t.category, t.amount.toFixed(2), t.note]);
  }
  const csv = rows.map((r) => r.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(',')).join('\n');
  download(`transactions-${todayISO()}.csv`, csv, 'text/csv');
});

$('#export-json').addEventListener('click', () => {
  download(`finance-backup-${todayISO()}.json`, JSON.stringify(state, null, 2), 'application/json');
});

$('#import-json').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  e.target.value = '';
  if (!file) return;
  try {
    const data = JSON.parse(await file.text());
    if (!Array.isArray(data.transactions)) throw new Error('missing transactions');
    const valid = data.transactions.every((t) =>
      t && typeof t.id === 'string' && (t.type === 'income' || t.type === 'expense') &&
      typeof t.amount === 'number' && /^\d{4}-\d{2}-\d{2}$/.test(t.date) && typeof t.category === 'string');
    if (!valid) throw new Error('invalid transaction');
    if (!confirm(`Replace current data with ${data.transactions.length} transactions from the backup?`)) return;
    state = { ...defaultState(), ...data, transactions: data.transactions.map((t) => ({ note: '', created: 0, ...t })) };
    saveState();
    $('#currency').value = state.currency;
    render();
    toast('Backup restored');
  } catch {
    toast('That file is not a valid backup');
  }
});

$('#load-sample').addEventListener('click', () => {
  if (state.transactions.length && !confirm('Add sample transactions to your existing data?')) return;
  const month = monthOf(todayISO());
  const sample = [];
  const add = (m, day, type, category, amount, note) =>
    sample.push({ id: uid(), created: Date.now(), type, category, amount, note, date: `${shiftMonth(month, m)}-${pad(day)}` });
  for (let m = -5; m <= 0; m++) {
    const wobble = 1 + ((m * 37) % 11) / 100;
    add(m, 1, 'income', 'Salary', 65000, 'Monthly salary');
    add(m, 2, 'expense', 'Rent', 18000, 'Apartment rent');
    add(m, 5, 'expense', 'Bills', Math.round(2400 * wobble), 'Electricity & internet');
    add(m, 8, 'expense', 'Food', Math.round(6200 * wobble), 'Groceries');
    add(m, 12, 'expense', 'Transport', Math.round(2100 * wobble), 'Metro card & fuel');
    add(m, 15, 'expense', 'Shopping', Math.round(4500 / wobble), 'Clothes');
    add(m, 20, 'expense', 'Entertainment', Math.round(1800 * wobble), 'Movies & streaming');
    if (m % 2 === 0) add(m, 22, 'income', 'Freelance', 12000, 'Website project');
  }
  // keep sample dates in the past/today for the current month
  const today = todayISO();
  state.transactions.push(...sample.filter((t) => t.date <= today));
  if (!Object.keys(state.budgets).length) {
    state.budgets = { Food: 7000, Shopping: 4000, Entertainment: 2000, Transport: 2500 };
  }
  saveState();
  render();
  toast('Sample data loaded');
});

$('#reset').addEventListener('click', () => {
  if (!confirm('Delete all transactions and budgets? This cannot be undone.')) return;
  state = { ...defaultState(), currency: state.currency };
  saveState();
  resetForm();
  render();
  toast('All data cleared');
});

// ---------- init ----------

monthInput.value = monthOf(todayISO());
$('#currency').value = state.currency;
resetForm();
render();
