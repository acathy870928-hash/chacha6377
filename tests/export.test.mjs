import test from 'node:test';
import assert from 'node:assert/strict';

import { toCsv, toTsv, COLUMNS } from '../src/export.js';

const SAMPLE = [
  {
    date: '2026-08-05',
    merchant: '스타벅스',
    amount: 32000,
    category: '접대비',
    purpose: '거래처 미팅',
    headcount: 3,
    department: '영업1팀',
    userName: '홍길동',
    cardName: '법인카드 1234',
    raw: '어제 거래처 미팅으로 스타벅스에서 3만 2천원 3명',
  },
];

test('CSV 헤더와 값을 순서대로 출력한다', () => {
  const csv = toCsv(SAMPLE);
  const [header, row] = csv.split('\r\n');
  assert.equal(header, COLUMNS.map((c) => c.label).join(','));
  assert.match(row, /^2026-08-05,스타벅스,32000,접대비/);
});

test('쉼표·따옴표가 들어간 값을 이스케이프한다', () => {
  const csv = toCsv([{ ...SAMPLE[0], purpose: '점심, 저녁 "겸용"' }]);
  assert.match(csv, /"점심, 저녁 ""겸용"""/);
});

test('빈 값은 빈 칸으로 출력한다', () => {
  const csv = toCsv([{ date: '2026-08-06', amount: 9000 }]);
  const row = csv.split('\r\n')[1];
  assert.equal(row.split(',').length, COLUMNS.length);
  assert.match(row, /^2026-08-06,,9000,/);
});

test('붙여넣기용 TSV 는 탭으로 구분되고 줄바꿈이 제거된다', () => {
  const tsv = toTsv([{ ...SAMPLE[0], purpose: '거래처\n미팅' }]);
  const row = tsv.split('\n')[1];
  assert.equal(row.split('\t').length, COLUMNS.length);
  assert.match(row, /거래처 미팅/);
});
