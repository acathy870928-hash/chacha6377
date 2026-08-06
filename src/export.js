/** 지출 내역을 회계팀에 전달할 수 있는 형태(CSV / 붙여넣기용 TSV)로 변환한다. */

export const COLUMNS = [
  { key: 'date', label: '사용일자' },
  { key: 'merchant', label: '사용처' },
  { key: 'amount', label: '금액' },
  { key: 'category', label: '계정과목' },
  { key: 'purpose', label: '사용목적' },
  { key: 'headcount', label: '인원' },
  { key: 'department', label: '부서' },
  { key: 'userName', label: '사용자' },
  { key: 'cardName', label: '카드' },
  { key: 'raw', label: '원본 음성' },
];

function cell(item, key) {
  const value = item[key];
  if (value === null || value === undefined) return '';
  return String(value);
}

function escapeCsv(value) {
  if (/[",\n\r]/.test(value)) return `"${value.replace(/"/g, '""')}"`;
  return value;
}

export function toCsv(expenses) {
  const header = COLUMNS.map((c) => escapeCsv(c.label)).join(',');
  const rows = expenses.map((item) => COLUMNS.map((c) => escapeCsv(cell(item, c.key))).join(','));
  return [header, ...rows].join('\r\n');
}

/** 엑셀·그룹웨어 표에 그대로 붙여넣을 수 있는 탭 구분 텍스트. */
export function toTsv(expenses, { includeHeader = true } = {}) {
  const clean = (value) => value.replace(/[\t\n\r]/g, ' ');
  const header = COLUMNS.map((c) => c.label).join('\t');
  const rows = expenses.map((item) => COLUMNS.map((c) => clean(cell(item, c.key))).join('\t'));
  return (includeHeader ? [header, ...rows] : rows).join('\n');
}

export function downloadCsv(expenses, filename = 'corporate-card.csv') {
  // 엑셀이 UTF-8 로 인식하도록 BOM 을 붙인다.
  const blob = new Blob([`﻿${toCsv(expenses)}`], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // 클립보드 API 가 막힌 환경(비 HTTPS 등) 대비
    const area = document.createElement('textarea');
    area.value = text;
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand?.('copy') ?? false;
    area.remove();
    return ok;
  }
}

export function toJson(expenses) {
  return JSON.stringify(expenses, null, 2);
}
