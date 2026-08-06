/** 지출 내역과 사용자 설정을 브라우저 localStorage 에 보관한다. */

const EXPENSE_KEY = 'corp-card:expenses:v1';
const SETTINGS_KEY = 'corp-card:settings:v1';

const DEFAULT_SETTINGS = {
  userName: '',
  department: '',
  cardName: '법인카드',
  autoSave: false,
};

function read(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    return JSON.parse(raw);
  } catch {
    return fallback;
  }
}

function write(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch {
    return false; // 시크릿 모드 등 저장이 막힌 환경
  }
}

export function loadSettings() {
  return { ...DEFAULT_SETTINGS, ...read(SETTINGS_KEY, {}) };
}

export function saveSettings(settings) {
  return write(SETTINGS_KEY, { ...DEFAULT_SETTINGS, ...settings });
}

export function loadExpenses() {
  const list = read(EXPENSE_KEY, []);
  return Array.isArray(list) ? list : [];
}

function persist(list) {
  write(EXPENSE_KEY, list);
  return list;
}

function newId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `e${Date.now()}${Math.floor(Math.random() * 1000)}`;
}

export function addExpense(expense) {
  const list = loadExpenses();
  const record = {
    id: newId(),
    createdAt: new Date().toISOString(),
    ...expense,
  };
  list.unshift(record);
  persist(list);
  return record;
}

export function updateExpense(id, patch) {
  const list = loadExpenses().map((item) => (item.id === id ? { ...item, ...patch, id } : item));
  persist(list);
  return list.find((item) => item.id === id) ?? null;
}

export function removeExpense(id) {
  persist(loadExpenses().filter((item) => item.id !== id));
}

export function replaceAll(list) {
  return persist(list);
}

/** 'YYYY-MM' 목록을 최신순으로 돌려준다. */
export function listMonths(expenses) {
  const months = new Set(expenses.map((item) => String(item.date ?? '').slice(0, 7)).filter(Boolean));
  return [...months].sort().reverse();
}

export function filterByMonth(expenses, month) {
  if (!month || month === 'all') return expenses;
  return expenses.filter((item) => String(item.date ?? '').startsWith(month));
}

export function sumAmount(expenses) {
  return expenses.reduce((total, item) => total + (Number(item.amount) || 0), 0);
}
