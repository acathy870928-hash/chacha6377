import test from 'node:test';
import assert from 'node:assert/strict';

import {
  koreanNumberToInt,
  extractAmount,
  extractDate,
  extractMerchant,
  extractCategory,
  extractHeadcount,
  parseExpense,
  splitUtterances,
} from '../src/parser.js';

// 기준일: 2026-08-06 (목요일)
const NOW = new Date(2026, 7, 6, 14, 30);

test('한국어 수 표현을 정수로 변환한다', () => {
  assert.equal(koreanNumberToInt('32000'), 32000);
  assert.equal(koreanNumberToInt('32,000'), 32000);
  assert.equal(koreanNumberToInt('3만2천'), 32000);
  assert.equal(koreanNumberToInt('3만 2천'), 32000);
  assert.equal(koreanNumberToInt('만'), 10000);
  assert.equal(koreanNumberToInt('십오만'), 150000);
  assert.equal(koreanNumberToInt('이만오천'), 25000);
  assert.equal(koreanNumberToInt('백이십만'), 1200000);
  assert.equal(koreanNumberToInt('커피'), null);
});

test('금액을 추출한다', () => {
  assert.equal(extractAmount('스타벅스에서 12000원 결제').amount, 12000);
  assert.equal(extractAmount('점심 3만 2천원').amount, 32000);
  assert.equal(extractAmount('회식 45,000원 썼어').amount, 45000);
  assert.equal(extractAmount('택시비 만원').amount, 10000);
  assert.equal(extractAmount('주유 오만원').amount, 50000);
  assert.equal(extractAmount('원 없이 3만5천 결제').amount, 35000);
  assert.equal(extractAmount('금액 없는 문장'), null);
});

test('인원수 표현이 금액으로 잘못 잡히지 않는다', () => {
  const parsed = parseExpense('거래처 미팅 4명 식대 8만원', { now: NOW });
  assert.equal(parsed.amount, 80000);
  assert.equal(parsed.headcount, 4);
});

test('날짜 표현이 있는 문장에서 금액을 올바르게 잡는다', () => {
  assert.equal(extractAmount('8월 6일 점심 3만원').amount, 30000);
  assert.equal(extractAmount('6일 김밥천국 9000원').amount, 9000);
});

test('날짜는 기본으로 오늘이 설정된다', () => {
  const result = extractDate('스타벅스 커피 12000원', NOW);
  assert.equal(result.date, '2026-08-06');
  assert.equal(result.explicit, false);
});

test('상대 날짜 표현을 반영한다', () => {
  assert.equal(extractDate('어제 점심', NOW).date, '2026-08-05');
  assert.equal(extractDate('그저께 회식', NOW).date, '2026-08-04');
  assert.equal(extractDate('오늘 택시비', NOW).date, '2026-08-06');
});

test('요일 표현을 반영한다', () => {
  // 2026-08-06 은 목요일
  assert.equal(extractDate('월요일 점심', NOW).date, '2026-08-03');
  assert.equal(extractDate('지난주 금요일 회식', NOW).date, '2026-07-31');
  assert.equal(extractDate('목요일 회의', NOW).date, '2026-07-30');
});

test('절대 날짜 표현을 반영한다', () => {
  assert.equal(extractDate('7월 21일 출장 숙박비', NOW).date, '2026-07-21');
  assert.equal(extractDate('3일 사무용품 구매', NOW).date, '2026-08-03');
  assert.equal(extractDate('12월 24일 거래처 선물', NOW).date, '2025-12-24');
});

test('사용처를 추출한다', () => {
  assert.equal(extractMerchant('스타벅스에서 커피 12000원'), '스타벅스');
  assert.equal(extractMerchant('어제 김밥천국에서 점심'), '김밥천국');
  assert.equal(extractMerchant('가맹점 이디야 3000원'), '이디야');
  assert.equal(extractMerchant('편의점에서 간식 구매'), '편의점');
  assert.equal(extractMerchant('배달의민족 점심 도시락'), '배달의민족');
});

test('계정과목을 추정한다', () => {
  assert.equal(extractCategory('거래처 미팅 저녁 식사'), '접대비');
  assert.equal(extractCategory('팀 회식 삼겹살'), '복리후생비');
  assert.equal(extractCategory('택시비 결제'), '교통비');
  assert.equal(extractCategory('A4 용지랑 토너 구매'), '사무용품비');
  assert.equal(extractCategory('점심 김밥'), '식대');
  assert.equal(extractCategory('출장 호텔 숙박'), '숙박비');
  assert.equal(extractCategory('알 수 없는 지출'), '기타');
});

test('인원수를 추출한다', () => {
  assert.equal(extractHeadcount('5명 회식'), 5);
  assert.equal(extractHeadcount('세 명이서 점심'), 3);
  assert.equal(extractHeadcount('혼자 먹은 점심'), null);
  assert.equal(extractHeadcount('점심 식사'), null);
});

test('문장 전체를 지출 항목으로 파싱한다', () => {
  const result = parseExpense('어제 거래처 미팅으로 스타벅스에서 3만 2천원 3명', { now: NOW });
  assert.equal(result.date, '2026-08-05');
  assert.equal(result.merchant, '스타벅스');
  assert.equal(result.amount, 32000);
  assert.equal(result.category, '접대비');
  assert.equal(result.headcount, 3);
  assert.match(result.purpose, /거래처 미팅/);
});

test('날짜를 말하지 않으면 오늘 날짜로 채워진다', () => {
  const result = parseExpense('김밥천국에서 점심 9000원', { now: NOW });
  assert.equal(result.date, '2026-08-06');
  assert.equal(result.dateExplicit, false);
  assert.equal(result.amount, 9000);
  assert.equal(result.category, '식대');
});

test('사용목적을 명시하면 그대로 사용한다', () => {
  const result = parseExpense('법인카드 5만원 목적은 협력사 방문 다과', { now: NOW });
  assert.equal(result.amount, 50000);
  assert.equal(result.purpose, '협력사 방문 다과');
});

test('여러 건이 섞인 발화를 문장 단위로 나눈다', () => {
  const parts = splitUtterances('오늘 점심 만원 그리고 택시비 8000원');
  assert.equal(parts.length, 2);
  assert.equal(parseExpense(parts[0], { now: NOW }).amount, 10000);
  assert.equal(parseExpense(parts[1], { now: NOW }).amount, 8000);
});
