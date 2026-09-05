import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  realRate, futureValueFactor, presentValueFactor,
  estimateNpsBasicMonthly, adjustNpsForStartAge, estimateHousingPensionMonthly,
  pensionIncomeDeduction, comprehensiveIncomeTax, publicPensionTax,
  privatePensionTaxRate, taxCreditDiagnosis, simulate,
} from '../assets/engine.js';
import { NPS, PRIVATE_PENSION } from '../assets/policy.js';

const near = (a, b, tol = 1e-6) => assert.ok(Math.abs(a - b) <= tol, `${a} != ${b} (tol ${tol})`);

test('실질수익률 변환 (피셔 방정식)', () => {
  near(realRate(0.05, 0.023), 1.05 / 1.023 - 1);
  near(realRate(0.03, 0.03), 0);
});

test('연금 계수: 손 검산값과 일치', () => {
  near(futureValueFactor(0.05, 10), 12.577892535548828, 1e-9);
  near(presentValueFactor(0.05, 10), 7.721734929184818, 1e-9);
  near(futureValueFactor(0, 10), 10);
  near(presentValueFactor(0, 10), 10);
  near(futureValueFactor(0.05, 0), 0);
});

test('국민연금: 40년 가입·평균소득 = A값이면 소득대체율 43%', () => {
  const { monthly } = estimateNpsBasicMonthly({ joinYears: 40, avgMonthlyIncome: NPS.aValue });
  near(monthly / NPS.aValue, NPS.targetReplacementRate, 0.001);
});

test('국민연금: 최소 가입기간 미달 시 수급 불가', () => {
  const r = estimateNpsBasicMonthly({ joinYears: 8, avgMonthlyIncome: 3_000_000 });
  assert.equal(r.eligible, false);
  assert.equal(r.monthly, 0);
});

test('국민연금: 조기수령 5년 -30%, 연기수령 5년 +36%', () => {
  assert.equal(adjustNpsForStartAge(1_000_000, 60).monthly, 700_000);
  assert.equal(adjustNpsForStartAge(1_000_000, 70).monthly, 1_360_000);
  assert.equal(adjustNpsForStartAge(1_000_000, 65).monthly, 1_000_000);
});

test('국민연금: 개시연령은 60~70세로 제한된다', () => {
  assert.equal(adjustNpsForStartAge(1_000_000, 50).monthly, 700_000);
  assert.equal(adjustNpsForStartAge(1_000_000, 80).monthly, 1_360_000);
});

test('주택연금: 주택가격에 비례하고 가입연령이 높을수록 많다', () => {
  const at60 = estimateHousingPensionMonthly({ houseValue: 300_000_000, startAge: 60 });
  const at70 = estimateHousingPensionMonthly({ houseValue: 300_000_000, startAge: 70 });
  assert.ok(at70 > at60);
  near(estimateHousingPensionMonthly({ houseValue: 600_000_000, startAge: 65 }), at60 * 0 + 274_000 * 6, 1);
  assert.equal(estimateHousingPensionMonthly({ houseValue: 300_000_000, startAge: 50 }), 0);
});

test('연금소득공제 구간 계산', () => {
  near(pensionIncomeDeduction(3_000_000), 3_000_000);
  near(pensionIncomeDeduction(10_000_000), 5_500_000);   // 490만 + (1000만-700만)×20%
  near(pensionIncomeDeduction(20_000_000), 6_900_000);   // 630만 + (2000만-1400만)×10%
});

test('종합소득세 = 과표×세율 - 누진공제, 지방세 10% 가산', () => {
  near(comprehensiveIncomeTax(10_000_000), 10_000_000 * 0.06 * 1.1);
  near(comprehensiveIncomeTax(30_000_000), (30_000_000 * 0.15 - 1_260_000) * 1.1);
  assert.equal(comprehensiveIncomeTax(-5), 0);
});

test('국민연금 세금: 소액 수령 시 과세되지 않는다', () => {
  assert.equal(publicPensionTax(4_000_000), 0);
  assert.ok(publicPensionTax(24_000_000) > 0);
});

test('사적연금 분리과세율은 연령이 높을수록 낮아진다', () => {
  assert.equal(privatePensionTaxRate(60), 0.055);
  assert.equal(privatePensionTaxRate(72), 0.044);
  assert.equal(privatePensionTaxRate(85), 0.033);
});

test('세액공제: 한도 900만원을 채우면 미사용 여력이 0', () => {
  const d = taxCreditDiagnosis({
    annualSalary: 50_000_000,
    annualSavingContribution: 6_000_000,
    annualIrpContribution: 3_000_000,
  });
  assert.equal(d.rate, PRIVATE_PENSION.highRate);
  assert.equal(d.eligibleAmount, 9_000_000);
  assert.equal(d.unusedRoom, 0);
  assert.equal(d.forgoneCredit, 0);
  assert.equal(d.currentCredit, 1_485_000);
});

test('세액공제: 연금저축 단독 한도 600만원을 넘는 납입은 인정되지 않는다', () => {
  const d = taxCreditDiagnosis({
    annualSalary: 80_000_000,
    annualSavingContribution: 9_000_000,
    annualIrpContribution: 0,
  });
  assert.equal(d.rate, PRIVATE_PENSION.lowRate);
  assert.equal(d.eligibleAmount, 6_000_000);
  assert.equal(d.unusedRoom, 3_000_000);
});

/* ── 시뮬레이션 통합 검증 ──────────────────────────────────── */

const baseInput = {
  profile: { currentAge: 45, retireAge: 60, lifeExpectancy: 90, monthlyIncome: 5_000_000, desiredMonthlySpend: 3_000_000 },
  nps: { mode: 'direct', directMonthly: 1_200_000, startAge: 65 },
  severance: { balance: 80_000_000, monthlyContribution: 400_000 },
  personal: { balance: 40_000_000, monthlyContribution: 500_000 },
  other: { assets: 50_000_000, monthlySaving: 300_000 },
  housing: { enabled: false, houseValue: 0, startAge: 65 },
  assumptions: { inflation: 0.023, salaryGrowth: 0.03, returnPre: 0.05, returnPost: 0.035 },
};

test('시뮬레이션: 타임라인은 은퇴연령부터 기대수명까지 이어진다', () => {
  const r = simulate(baseInput);
  assert.equal(r.timeline[0].age, 60);
  assert.equal(r.timeline.at(-1).age, 90);
  assert.equal(r.timeline.length, 31);
});

test('시뮬레이션: 자원이 전혀 없으면 은퇴 첫해에 바로 고갈된다', () => {
  const r = simulate({
    ...baseInput,
    nps: { mode: 'direct', directMonthly: 0, startAge: 65 },
    severance: { balance: 0, monthlyContribution: 0 },
    personal: { balance: 0, monthlyContribution: 0 },
    other: { assets: 0, monthlySaving: 0 },
  });
  assert.equal(r.metrics.depletionAge, 60);
  near(r.metrics.fundedRatio, 0, 1e-9);
  assert.ok(r.metrics.requiredExtraMonthlySaving > 0);
});

test('시뮬레이션: 자원이 충분하면 고갈되지 않고 충족률이 1', () => {
  const r = simulate({
    ...baseInput,
    other: { assets: 5_000_000_000, monthlySaving: 0 },
  });
  assert.equal(r.metrics.depletionAge, null);
  near(r.metrics.fundedRatio, 1, 1e-9);
  assert.equal(r.metrics.requiredExtraMonthlySaving, 0);
});

test('시뮬레이션: 저축을 늘리면 고갈 시점이 늦춰진다 (단조성)', () => {
  const low = simulate({ ...baseInput, other: { assets: 50_000_000, monthlySaving: 100_000 } });
  const high = simulate({ ...baseInput, other: { assets: 50_000_000, monthlySaving: 1_500_000 } });
  assert.ok(high.metrics.fundedRatio >= low.metrics.fundedRatio);
  const lowAge = low.metrics.depletionAge ?? 999;
  const highAge = high.metrics.depletionAge ?? 999;
  assert.ok(highAge >= lowAge, `${highAge} < ${lowAge}`);
});

test('시뮬레이션: 소득 공백기(은퇴~국민연금 개시)를 정확히 센다', () => {
  const r = simulate(baseInput);
  assert.equal(r.metrics.bridgeYears, 5);
  assert.equal(r.timeline.find((x) => x.age === 64).npsNet, 0);
  assert.ok(r.timeline.find((x) => x.age === 65).npsNet > 0);
});

test('시뮬레이션: 국민연금 연기수령은 월 수령액을 늘린다', () => {
  const normal = simulate({ ...baseInput, nps: { mode: 'direct', directMonthly: 1_200_000, startAge: 65 } });
  const defer = simulate({ ...baseInput, nps: { mode: 'direct', directMonthly: 1_200_000, startAge: 70 } });
  assert.ok(defer.inputsResolved.npsMonthly > normal.inputsResolved.npsMonthly);
});

test('시뮬레이션: 충족률과 부족액은 서로 정합한다', () => {
  const r = simulate(baseInput);
  near(r.metrics.fundedRatio, 1 - r.metrics.totalShortfallPv / r.metrics.totalNeedPv, 1e-6);
  assert.ok(r.metrics.fundedRatio >= 0 && r.metrics.fundedRatio <= 1);
});

test('시뮬레이션: 잔액은 절대 음수가 되지 않는다', () => {
  const r = simulate(baseInput);
  for (const row of r.timeline) {
    assert.ok(row.balances.total >= 0, `age ${row.age} balance ${row.balances.total}`);
    assert.ok(row.shortfall >= 0);
  }
});

test('시뮬레이션: 주택연금은 명목 고정이라 실질가치가 줄어든다', () => {
  const r = simulate({ ...baseInput, housing: { enabled: true, houseValue: 500_000_000, startAge: 65 } });
  const at65 = r.timeline.find((x) => x.age === 65).housingNet;
  const at85 = r.timeline.find((x) => x.age === 85).housingNet;
  assert.ok(at65 > 0);
  assert.ok(at85 < at65, '실질 주택연금은 시간이 갈수록 줄어야 한다');
});

test('입력 정규화: 비정상 입력을 안전한 범위로 보정한다', () => {
  const r = simulate({
    profile: { currentAge: 70, retireAge: 50, lifeExpectancy: 40, monthlyIncome: -100, desiredMonthlySpend: 'abc' },
    nps: { mode: 'direct', directMonthly: -5, startAge: 200 },
  });
  assert.ok(r.timeline.length > 0);
  assert.ok(r.timeline[0].age >= 70);
});
