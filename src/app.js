/** 화면 조작과 각 모듈을 연결하는 진입점. */

import { CATEGORIES, parseExpense, formatCurrency } from './parser.js';
import { createRecorder, isSpeechSupported } from './speech.js';
import {
  addExpense,
  filterByMonth,
  listMonths,
  loadExpenses,
  loadSettings,
  removeExpense,
  replaceAll,
  saveSettings,
  sumAmount,
  updateExpense,
} from './storage.js';
import { downloadCsv, copyToClipboard, toTsv } from './export.js';

const $ = (id) => document.getElementById(id);

const el = {
  recordBtn: $('recordBtn'),
  recordLabel: $('recordLabel'),
  status: $('status'),
  transcript: $('transcript'),
  analyzeBtn: $('analyzeBtn'),
  clearTranscriptBtn: $('clearTranscriptBtn'),
  form: $('expenseForm'),
  date: $('date'),
  amount: $('amount'),
  merchant: $('merchant'),
  category: $('category'),
  headcount: $('headcount'),
  cardName: $('cardName'),
  purpose: $('purpose'),
  submitBtn: $('submitBtn'),
  resetBtn: $('resetBtn'),
  editBadge: $('editBadge'),
  monthFilter: $('monthFilter'),
  countLabel: $('countLabel'),
  totalLabel: $('totalLabel'),
  list: $('list'),
  csvBtn: $('csvBtn'),
  copyBtn: $('copyBtn'),
  deleteMonthBtn: $('deleteMonthBtn'),
  userName: $('userName'),
  department: $('department'),
  defaultCard: $('defaultCard'),
  autoSave: $('autoSave'),
  toast: $('toast'),
};

let settings = loadSettings();
let editingId = null;
let selectedMonth = todayISO().slice(0, 7);

function todayISO() {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}

let toastTimer = null;
function toast(message) {
  el.toast.textContent = message;
  el.toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    el.toast.hidden = true;
  }, 2400);
}

function setStatus(message, isError = false) {
  el.status.textContent = message;
  el.status.classList.toggle('error', isError);
}

/* ---------- 폼 ---------- */

function initCategories() {
  el.category.innerHTML = CATEGORIES.map((name) => `<option value="${name}">${name}</option>`).join('');
}

function markFilled(input, filled) {
  input.closest('.field')?.classList.toggle('filled', Boolean(filled));
}

function clearHighlights() {
  document.querySelectorAll('.field.filled').forEach((field) => field.classList.remove('filled'));
}

function resetForm({ keepTranscript = false } = {}) {
  editingId = null;
  el.editBadge.hidden = true;
  el.submitBtn.textContent = '저장';
  el.form.reset();
  el.date.value = todayISO(); // 날짜는 항상 오늘로 자동 설정
  el.cardName.value = settings.cardName;
  el.category.value = '식대';
  clearHighlights();
  if (!keepTranscript) el.transcript.value = '';
}

function formToExpense() {
  const amount = Number(String(el.amount.value).replace(/[^\d]/g, ''));
  return {
    date: el.date.value || todayISO(),
    merchant: el.merchant.value.trim(),
    amount: Number.isFinite(amount) ? amount : 0,
    category: el.category.value,
    purpose: el.purpose.value.trim(),
    headcount: el.headcount.value ? Number(el.headcount.value) : '',
    cardName: el.cardName.value.trim() || settings.cardName,
    department: settings.department,
    userName: settings.userName,
    raw: el.transcript.value.trim(),
  };
}

function fillForm(parsed) {
  el.date.value = parsed.date;
  markFilled(el.date, parsed.dateExplicit);

  if (parsed.amount) {
    el.amount.value = parsed.amount.toLocaleString('ko-KR');
    markFilled(el.amount, true);
  }
  if (parsed.merchant) {
    el.merchant.value = parsed.merchant;
    markFilled(el.merchant, true);
  }
  if (parsed.category) {
    el.category.value = CATEGORIES.includes(parsed.category) ? parsed.category : '기타';
    markFilled(el.category, parsed.category !== '기타');
  }
  if (parsed.headcount) {
    el.headcount.value = parsed.headcount;
    markFilled(el.headcount, true);
  }
  if (parsed.purpose) {
    el.purpose.value = parsed.purpose;
    markFilled(el.purpose, true);
  }
  if (!el.cardName.value) el.cardName.value = settings.cardName;
}

/** 인식/입력된 문장을 폼에 반영한다. */
function analyze(text, { fromVoice = false } = {}) {
  const raw = String(text ?? '').trim();
  if (!raw) {
    setStatus('인식된 내용이 없습니다.', true);
    return;
  }

  el.transcript.value = raw;
  const parsed = parseExpense(raw);
  clearHighlights();
  fillForm(parsed);

  if (!parsed.amount) {
    setStatus('금액을 찾지 못했습니다. 금액만 직접 채워 주세요.', true);
    el.amount.focus();
    return;
  }

  const summary = `${parsed.date} · ${parsed.merchant || '사용처 미상'} · ${formatCurrency(parsed.amount)}`;
  if (fromVoice && settings.autoSave) {
    saveCurrentForm();
    setStatus(`자동 저장됨 — ${summary}`);
    return;
  }
  setStatus(`${summary} — 확인 후 저장을 눌러 주세요.`);
}

function saveCurrentForm() {
  const expense = formToExpense();
  if (!expense.amount) {
    toast('금액을 입력해 주세요.');
    el.amount.focus();
    return false;
  }

  if (editingId) {
    updateExpense(editingId, expense);
    toast('수정했습니다.');
  } else {
    addExpense(expense);
    toast(`저장했습니다 — ${formatCurrency(expense.amount)}`);
  }

  selectedMonth = expense.date.slice(0, 7);
  resetForm();
  render();
  return true;
}

/* ---------- 목록 ---------- */

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (ch) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]
  ));
}

function currentList() {
  return filterByMonth(loadExpenses(), selectedMonth).sort((a, b) => (a.date < b.date ? 1 : -1));
}

function renderMonthFilter(expenses) {
  const months = listMonths(expenses);
  if (!months.includes(selectedMonth)) months.unshift(selectedMonth);

  el.monthFilter.innerHTML = [
    ...months.map((m) => {
      const [y, mo] = m.split('-');
      return `<option value="${m}">${y}년 ${Number(mo)}월</option>`;
    }),
    '<option value="all">전체</option>',
  ].join('');
  el.monthFilter.value = selectedMonth;
}

function renderList(items) {
  if (!items.length) {
    el.list.innerHTML = '<p class="empty">아직 등록된 내역이 없습니다.<br />녹음 버튼을 눌러 첫 건을 입력해 보세요.</p>';
    return;
  }

  el.list.innerHTML = items
    .map((item) => {
      const meta = [
        item.purpose,
        item.headcount ? `${item.headcount}명` : '',
        item.cardName,
      ]
        .filter(Boolean)
        .map(escapeHtml)
        .join(' · ');

      return `
        <article class="item" data-id="${item.id}">
          <div class="item-main">
            <span class="item-date">${escapeHtml(item.date)}</span>
            <span class="item-merchant">${escapeHtml(item.merchant || '사용처 미상')}</span>
            <span class="chip">${escapeHtml(item.category || '기타')}</span>
          </div>
          <div class="item-right">
            <span class="item-amount">${escapeHtml(formatCurrency(item.amount))}</span>
          </div>
          <div class="item-meta">${meta || '&nbsp;'}</div>
          <div class="item-actions">
            <button type="button" class="icon-btn edit" data-action="edit">수정</button>
            <button type="button" class="icon-btn remove" data-action="remove">삭제</button>
          </div>
        </article>`;
    })
    .join('');
}

function render() {
  const all = loadExpenses();
  renderMonthFilter(all);
  const items = currentList();
  renderList(items);
  el.countLabel.textContent = `${items.length}건`;
  el.totalLabel.textContent = formatCurrency(sumAmount(items)) || '0원';
}

function startEdit(id) {
  const item = loadExpenses().find((e) => e.id === id);
  if (!item) return;

  editingId = id;
  el.editBadge.hidden = false;
  el.submitBtn.textContent = '수정 저장';
  el.date.value = item.date;
  el.amount.value = Number(item.amount || 0).toLocaleString('ko-KR');
  el.merchant.value = item.merchant ?? '';
  el.category.value = CATEGORIES.includes(item.category) ? item.category : '기타';
  el.headcount.value = item.headcount ?? '';
  el.cardName.value = item.cardName ?? settings.cardName;
  el.purpose.value = item.purpose ?? '';
  el.transcript.value = item.raw ?? '';
  clearHighlights();
  el.form.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

/* ---------- 설정 ---------- */

function applySettingsToInputs() {
  el.userName.value = settings.userName;
  el.department.value = settings.department;
  el.defaultCard.value = settings.cardName;
  el.autoSave.checked = settings.autoSave;
}

function persistSettingsFromInputs() {
  settings = {
    userName: el.userName.value.trim(),
    department: el.department.value.trim(),
    cardName: el.defaultCard.value.trim() || '법인카드',
    autoSave: el.autoSave.checked,
  };
  saveSettings(settings);
  if (!editingId) el.cardName.value = settings.cardName;
}

/* ---------- 음성 ---------- */

const recorder = createRecorder({
  onStateChange(listening) {
    el.recordBtn.classList.toggle('listening', listening);
    el.recordBtn.setAttribute('aria-pressed', String(listening));
    el.recordLabel.textContent = listening ? '말하는 중…' : '녹음 시작';
    if (listening) setStatus('듣고 있습니다. 끝나면 버튼을 다시 눌러 주세요.');
  },
  onInterim(text) {
    el.transcript.value = text;
  },
  onResult(text) {
    analyze(text, { fromVoice: true });
  },
  onError(message) {
    setStatus(message, true);
  },
});

/* ---------- 이벤트 ---------- */

function bindEvents() {
  el.recordBtn.addEventListener('click', () => recorder.toggle());

  el.analyzeBtn.addEventListener('click', () => analyze(el.transcript.value));

  el.transcript.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      analyze(el.transcript.value);
    }
  });

  el.clearTranscriptBtn.addEventListener('click', () => {
    el.transcript.value = '';
    setStatus('버튼을 누르고 말씀하세요.');
    el.transcript.focus();
  });

  el.form.addEventListener('submit', (event) => {
    event.preventDefault();
    saveCurrentForm();
  });

  el.resetBtn.addEventListener('click', () => {
    resetForm();
    setStatus('버튼을 누르고 말씀하세요.');
  });

  // 금액 입력에 천 단위 구분 자동 적용
  el.amount.addEventListener('input', () => {
    const digits = el.amount.value.replace(/[^\d]/g, '');
    el.amount.value = digits ? Number(digits).toLocaleString('ko-KR') : '';
  });

  el.list.addEventListener('click', (event) => {
    const button = event.target.closest('button[data-action]');
    if (!button) return;
    const id = button.closest('.item')?.dataset.id;
    if (!id) return;

    if (button.dataset.action === 'edit') startEdit(id);
    if (button.dataset.action === 'remove') {
      if (!confirm('이 내역을 삭제할까요?')) return;
      removeExpense(id);
      if (editingId === id) resetForm();
      render();
      toast('삭제했습니다.');
    }
  });

  el.monthFilter.addEventListener('change', () => {
    selectedMonth = el.monthFilter.value;
    render();
  });

  el.csvBtn.addEventListener('click', () => {
    const items = currentList();
    if (!items.length) return toast('내려받을 내역이 없습니다.');
    downloadCsv(items, `법인카드_${selectedMonth}.csv`);
    toast('CSV 파일을 내려받았습니다.');
  });

  el.copyBtn.addEventListener('click', async () => {
    const items = currentList();
    if (!items.length) return toast('복사할 내역이 없습니다.');
    const ok = await copyToClipboard(toTsv(items));
    toast(ok ? '표로 복사했습니다. 엑셀에 붙여넣으세요.' : '복사에 실패했습니다.');
  });

  el.deleteMonthBtn.addEventListener('click', () => {
    const items = currentList();
    if (!items.length) return toast('삭제할 내역이 없습니다.');
    if (!confirm(`${items.length}건을 삭제할까요? 되돌릴 수 없습니다.`)) return;
    const ids = new Set(items.map((item) => item.id));
    replaceAll(loadExpenses().filter((item) => !ids.has(item.id)));
    resetForm();
    render();
    toast('삭제했습니다.');
  });

  [el.userName, el.department, el.defaultCard, el.autoSave].forEach((input) => {
    input.addEventListener('change', persistSettingsFromInputs);
  });
}

/* ---------- 시작 ---------- */

function init() {
  initCategories();
  applySettingsToInputs();
  resetForm();
  bindEvents();
  render();

  if (!isSpeechSupported()) {
    el.recordBtn.disabled = true;
    el.recordBtn.style.opacity = '0.5';
    setStatus('이 브라우저는 음성 인식을 지원하지 않습니다. 아래 칸에 문장을 입력한 뒤 “문장 분석”을 눌러 주세요.', true);
  }
}

init();
