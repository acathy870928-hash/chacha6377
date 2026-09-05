/**
 * 연금설계 계산 엔진 — 순수 함수 모듈 (DOM 의존성 없음)
 * ---------------------------------------------------------------
 * 설계 원칙
 *  1) 모든 금액은 "오늘의 돈"(실질가치)으로 계산합니다.
 *     명목 물가상승률은 실질수익률 변환으로 흡수되며,
 *     물가에 연동되지 않는 소득(주택연금 등)만 별도로 가치가 깎입니다.
 *  2) 세율·한도 등 정책값은 policy.js에서만 가져옵니다.
 *  3) 이 모듈은 어떤 값도 추측하지 않습니다. 계산만 합니다.
 */

import {
  NPS, RETIREMENT_PENSION, PRIVATE_PENSION, PENSION_INCOME_TAX,
  INCOME_TAX_BRACKETS, LOCAL_INCOME_TAX_RATE, BASIC_DEDUCTION_PER_PERSON,
  HOUSING_PENSION, BENCHMARKS,
} from './policy.js';

/* ── 금융 유틸 ──────────────────────────────────────────────── */

/** 명목수익률 → 실질수익률 (피셔 방정식) */
export function realRate(nominal, inflation) {
  return (1 + nominal) / (1 + inflation) - 1;
}

/** 기말 연금의 미래가치 계수: 매년 1원을 n년간 적립했을 때의 원리금 */
export function futureValueFactor(rate, years) {
  if (years <= 0) return 0;
  if (Math.abs(rate) < 1e-9) return years;
  return (Math.pow(1 + rate, years) - 1) / rate;
}

/** 기말 연금의 현재가치 계수: 매년 1원을 n년간 받을 때의 현재가치 */
export function presentValueFactor(rate, years) {
  if (years <= 0) return 0;
  if (Math.abs(rate) < 1e-9) return years;
  return (1 - Math.pow(1 + rate, -years)) / rate;
}

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const round = (v) => Math.round(v);

/* ── 국민연금 ───────────────────────────────────────────────── */

/**
 * 국민연금 기본연금액 간이 추정 (월액, 실질가치)
 * 기본연금액(연) = 상수 × (A + B) × (1 + 0.05 × n/12)
 *   A = 전체 가입자 평균소득월액, B = 본인 가입기간 평균소득월액
 *   n = 20년 초과 가입월수
 * ※ 실제 연금액은 가입시기별 소득대체율 가중평균으로 산정되므로 오차가 있습니다.
 */
export function estimateNpsBasicMonthly({ joinYears, avgMonthlyIncome }) {
  if (joinYears < NPS.minJoinYears) {
    return { monthly: 0, eligible: false, reason: `가입기간 ${NPS.minJoinYears}년 미만 — 노령연금 수급 불가` };
  }
  const A = NPS.aValue;
  const B = Math.max(0, avgMonthlyIncome);
  const excessMonths = Math.max(0, (joinYears - 20) * 12);
  const annual = NPS.constant * (A + B) * (1 + 0.05 * (excessMonths / 12));
  const capped = Math.min(joinYears, 40);
  const proration = capped >= 20 ? 1 : capped / 20; // 20년 미만은 가입기간 비례
  return { monthly: round((annual / 12) * proration), eligible: true, reason: null };
}

/** 조기수령 감액 / 연기수령 증액 반영 */
export function adjustNpsForStartAge(baseMonthly, startAge) {
  const normal = NPS.normalStartAge;
  const age = clamp(startAge, NPS.earliestStartAge, NPS.latestStartAge);
  if (age < normal) {
    const years = normal - age;
    return { monthly: round(baseMonthly * (1 - NPS.earlyPenaltyPerYear * years)), adjustment: -NPS.earlyPenaltyPerYear * years };
  }
  if (age > normal) {
    const years = age - normal;
    return { monthly: round(baseMonthly * (1 + NPS.deferBonusPerYear * years)), adjustment: NPS.deferBonusPerYear * years };
  }
  return { monthly: round(baseMonthly), adjustment: 0 };
}

/* ── 주택연금 ───────────────────────────────────────────────── */

/** 가입연령별 월지급금 추정 (주택가격 비례, 선형보간) */
export function estimateHousingPensionMonthly({ houseValue, startAge }) {
  const table = HOUSING_PENSION.monthlyPerHundredMillion;
  if (startAge < HOUSING_PENSION.minAge || houseValue <= 0) return 0;
  const value = Math.min(houseValue, HOUSING_PENSION.maxHouseValue);
  const age = clamp(startAge, table[0].age, table[table.length - 1].age);

  let perHundred = table[table.length - 1].amount;
  for (let i = 0; i < table.length - 1; i++) {
    const lo = table[i], hi = table[i + 1];
    if (age >= lo.age && age <= hi.age) {
      const t = (age - lo.age) / (hi.age - lo.age);
      perHundred = lo.amount + t * (hi.amount - lo.amount);
      break;
    }
  }
  return round((value / 100_000_000) * perHundred);
}

/* ── 과세 ───────────────────────────────────────────────────── */

/** 사적연금 저율 분리과세율 (연령별) */
export function privatePensionTaxRate(age) {
  const found = PENSION_INCOME_TAX.rateByAge.find((r) => age >= r.minAge);
  return found ? found.rate : PENSION_INCOME_TAX.rateByAge[PENSION_INCOME_TAX.rateByAge.length - 1].rate;
}

/** 연금소득공제 */
export function pensionIncomeDeduction(totalPensionIncome) {
  const brackets = PENSION_INCOME_TAX.deductionBrackets;
  let prevCeiling = 0;
  for (const b of brackets) {
    if (totalPensionIncome <= b.upTo) {
      return Math.min(PENSION_INCOME_TAX.deductionCap, b.base + (totalPensionIncome - prevCeiling) * b.rate);
    }
    prevCeiling = b.upTo;
  }
  return PENSION_INCOME_TAX.deductionCap;
}

/** 종합소득세 (지방소득세 포함) */
export function comprehensiveIncomeTax(taxableIncome) {
  if (taxableIncome <= 0) return 0;
  const b = INCOME_TAX_BRACKETS.find((x) => taxableIncome <= x.upTo);
  const income = taxableIncome * b.rate - b.progressiveDeduction;
  return Math.max(0, income * (1 + LOCAL_INCOME_TAX_RATE));
}

/** 공적연금(국민연금)에 대한 세금 간이 추정 */
export function publicPensionTax(annualPublicPension) {
  if (annualPublicPension <= 0) return 0;
  const deduction = pensionIncomeDeduction(annualPublicPension);
  const taxable = Math.max(0, annualPublicPension - deduction - BASIC_DEDUCTION_PER_PERSON);
  return round(comprehensiveIncomeTax(taxable));
}

/** 연금저축·IRP 세액공제 진단 */
export function taxCreditDiagnosis({ annualSalary, annualSavingContribution, annualIrpContribution }) {
  const rate = annualSalary <= PRIVATE_PENSION.highRateSalaryCeiling
    ? PRIVATE_PENSION.highRate : PRIVATE_PENSION.lowRate;

  const savingEligible = Math.min(annualSavingContribution, PRIVATE_PENSION.annuitySavingLimit);
  const combinedEligible = Math.min(savingEligible + annualIrpContribution, PRIVATE_PENSION.combinedLimit);

  const currentCredit = round(combinedEligible * rate);
  const maxCredit = round(PRIVATE_PENSION.combinedLimit * rate);

  return {
    rate,
    eligibleAmount: round(combinedEligible),
    unusedRoom: round(PRIVATE_PENSION.combinedLimit - combinedEligible),
    currentCredit,
    maxCredit,
    forgoneCredit: round(maxCredit - currentCredit),
    usageRatio: PRIVATE_PENSION.combinedLimit > 0 ? combinedEligible / PRIVATE_PENSION.combinedLimit : 0,
  };
}

/* ── 메인 시뮬레이션 ────────────────────────────────────────── */

/**
 * 은퇴 현금흐름 시뮬레이션
 * @returns {{ timeline: Array, metrics: Object, inputsResolved: Object }}
 */
export function simulate(input) {
  const {
    profile, nps, severance, personal, other, housing, assumptions,
  } = normalizeInput(input);

  const rPre = realRate(assumptions.returnPre, assumptions.inflation);
  const rPost = realRate(assumptions.returnPost, assumptions.inflation);
  const gReal = realRate(assumptions.salaryGrowth, assumptions.inflation);

  const yearsToRetire = Math.max(0, profile.retireAge - profile.currentAge);

  /* --- 1) 국민연금 월액 확정 (실질가치) --- */
  let npsBaseMonthly;
  let npsEstimateNote = null;
  if (nps.mode === 'direct') {
    npsBaseMonthly = nps.directMonthly;
  } else {
    const est = estimateNpsBasicMonthly({ joinYears: nps.joinYears, avgMonthlyIncome: nps.avgMonthlyIncome });
    npsBaseMonthly = est.monthly;
    npsEstimateNote = est.reason;
  }
  const npsAdjusted = adjustNpsForStartAge(npsBaseMonthly, nps.startAge);

  /* --- 2) 주택연금 월액 (가입 시점 명목 고정) --- */
  const housingMonthlyNominal = housing.enabled
    ? estimateHousingPensionMonthly({ houseValue: housing.houseValue, startAge: housing.startAge })
    : 0;

  /* --- 3) 적립기: 은퇴 시점 잔액 (실질가치) --- */
  const accumulate = (balance, monthlyContribution) => {
    let bal = balance;
    let annual = monthlyContribution * 12;
    for (let i = 0; i < yearsToRetire; i++) {
      bal = bal * (1 + rPre) + annual;
      annual *= (1 + gReal);
    }
    return bal;
  };

  const balances = {
    severance: accumulate(severance.balance, severance.monthlyContribution),
    personal: accumulate(personal.balance, personal.monthlyContribution),
    other: accumulate(other.assets, other.monthlySaving),
  };
  const retirementAssets = balances.severance + balances.personal + balances.other;

  /* --- 4) 은퇴 직전 소득 (실질가치) --- */
  const preRetirementMonthlyIncome = profile.monthlyIncome * Math.pow(1 + gReal, yearsToRetire);

  /* --- 5) 인출기 시뮬레이션 --- */
  const annualNeed = profile.desiredMonthlySpend * 12;
  const timeline = [];
  let depletionAge = null;
  let firstYearNetMonthly = 0;
  let bridgeShortfallTotal = 0;
  let bridgeYears = 0;

  const startAge = profile.retireAge;
  const endAge = profile.lifeExpectancy;

  for (let age = startAge; age <= endAge; age++) {
    const t = age - startAge;

    // 기초 잔액에 운용수익 반영
    if (t > 0) {
      balances.severance *= (1 + rPost);
      balances.personal *= (1 + rPost);
      balances.other *= (1 + rPost);
    }

    // (a) 국민연금 — 물가연동이므로 실질가치 일정
    const npsAnnualGross = age >= nps.startAge ? npsAdjusted.monthly * 12 : 0;
    const npsTax = publicPensionTax(npsAnnualGross);
    const npsNet = npsAnnualGross - npsTax;

    // (b) 주택연금 — 명목 고정이므로 실질가치가 매년 하락
    const yearsSinceHousing = housing.enabled ? age - housing.startAge : -1;
    const housingNet = yearsSinceHousing >= 0
      ? (housingMonthlyNominal * 12) / Math.pow(1 + assumptions.inflation, Math.max(0, age - profile.currentAge))
      : 0;

    let remaining = annualNeed - npsNet - housingNet;
    let severanceWithdraw = 0, personalWithdraw = 0, otherWithdraw = 0;
    let privateTax = 0, severanceTax = 0;

    const lowRate = privatePensionTaxRate(age);
    const severanceTaxRate = RETIREMENT_PENSION.defaultEffectiveSeveranceTaxRate *
      (1 - (t < 10 ? RETIREMENT_PENSION.taxCutWithin10Years : RETIREMENT_PENSION.taxCutAfter10Years));

    // (c) 퇴직연금 계좌 — 이연퇴직소득 재원은 1,500만원 한도 대상이 아님
    if (remaining > 0 && balances.severance > 0 && age >= RETIREMENT_PENSION.minPensionAgeForAccount) {
      const gross = Math.min(balances.severance, remaining / (1 - severanceTaxRate));
      severanceWithdraw = gross;
      severanceTax = gross * severanceTaxRate;
      balances.severance -= gross;
      remaining -= (gross - severanceTax);
    }

    // (d) 개인연금 계좌 — 저율 분리과세 구간(연 1,500만원)까지 우선 인출
    if (remaining > 0 && balances.personal > 0 && age >= RETIREMENT_PENSION.minPensionAgeForAccount) {
      const room = PENSION_INCOME_TAX.separateTaxationThreshold;
      const grossNeeded = remaining / (1 - lowRate);
      const gross = Math.min(balances.personal, grossNeeded, room);
      personalWithdraw += gross;
      privateTax += gross * lowRate;
      balances.personal -= gross;
      remaining -= gross * (1 - lowRate);
    }

    // (e) 기타 금융자산 (원금 인출은 비과세로 가정)
    if (remaining > 0 && balances.other > 0) {
      const gross = Math.min(balances.other, remaining);
      otherWithdraw = gross;
      balances.other -= gross;
      remaining -= gross;
    }

    // (f) 여전히 부족하면 개인연금 추가 인출 (16.5% 고율 분리과세)
    if (remaining > 0 && balances.personal > 0) {
      const highRate = PENSION_INCOME_TAX.highSeparateRate;
      const gross = Math.min(balances.personal, remaining / (1 - highRate));
      personalWithdraw += gross;
      privateTax += gross * highRate;
      balances.personal -= gross;
      remaining -= gross * (1 - highRate);
    }

    const shortfall = Math.max(0, remaining);
    if (shortfall > 1 && depletionAge === null) depletionAge = age;

    const totalTax = npsTax + severanceTax + privateTax;
    const netIncome = annualNeed - shortfall;

    if (age === startAge) firstYearNetMonthly = netIncome / 12;
    if (age < nps.startAge) { bridgeYears++; bridgeShortfallTotal += shortfall; }

    timeline.push({
      age,
      need: round(annualNeed),
      npsGross: round(npsAnnualGross),
      npsNet: round(npsNet),
      housingNet: round(housingNet),
      severanceWithdraw: round(severanceWithdraw),
      personalWithdraw: round(personalWithdraw),
      otherWithdraw: round(otherWithdraw),
      tax: round(totalTax),
      netIncome: round(netIncome),
      shortfall: round(shortfall),
      privateAnnualForThreshold: round(personalWithdraw),
      balances: {
        severance: round(Math.max(0, balances.severance)),
        personal: round(Math.max(0, balances.personal)),
        other: round(Math.max(0, balances.other)),
        total: round(Math.max(0, balances.severance + balances.personal + balances.other)),
      },
    });
  }

  /* --- 6) 지표 산출 --- */
  const totalNeedPv = timeline.reduce((s, r, i) => s + r.need / Math.pow(1 + rPost, i), 0);
  const totalShortfallPv = timeline.reduce((s, r, i) => s + r.shortfall / Math.pow(1 + rPost, i), 0);
  const fundedRatio = totalNeedPv > 0 ? 1 - totalShortfallPv / totalNeedPv : 1;

  // 부족액을 메우기 위해 은퇴까지 추가로 저축해야 할 월 금액 (실질)
  const fvFactor = futureValueFactor(rPre, yearsToRetire);
  const requiredExtraMonthlySaving = fvFactor > 0 ? (totalShortfallPv / fvFactor) / 12 : 0;

  const replacementRate = preRetirementMonthlyIncome > 0
    ? firstYearNetMonthly / preRetirementMonthlyIncome : 0;

  const guaranteedMonthly = npsAdjusted.monthly + (housing.enabled ? housingMonthlyNominal : 0);
  const peakPrivateAnnual = Math.max(0, ...timeline.map((r) => r.personalWithdraw));

  return {
    inputsResolved: {
      npsBaseMonthly: round(npsBaseMonthly),
      npsMonthly: npsAdjusted.monthly,
      npsAdjustment: npsAdjusted.adjustment,
      npsEstimateNote,
      housingMonthlyNominal,
      yearsToRetire,
      realReturnPre: rPre,
      realReturnPost: rPost,
      realSalaryGrowth: gReal,
      preRetirementMonthlyIncome: round(preRetirementMonthlyIncome),
    },
    metrics: {
      retirementAssets: round(retirementAssets),
      assetsAtRetirement: {
        severance: round(accumulate(severance.balance, severance.monthlyContribution)),
        personal: round(accumulate(personal.balance, personal.monthlyContribution)),
        other: round(accumulate(other.assets, other.monthlySaving)),
      },
      firstYearMonthlyIncome: round(firstYearNetMonthly),
      desiredMonthlySpend: round(profile.desiredMonthlySpend),
      replacementRate,
      targetReplacementRate: BENCHMARKS.targetReplacementRate,
      depletionAge,
      lifeExpectancy: profile.lifeExpectancy,
      fundedRatio,
      totalNeedPv: round(totalNeedPv),
      totalShortfallPv: round(totalShortfallPv),
      requiredExtraMonthlySaving: round(requiredExtraMonthlySaving),
      guaranteedMonthly: round(guaranteedMonthly),
      bridgeYears: Math.max(0, nps.startAge - profile.retireAge),
      bridgeShortfallTotal: round(bridgeShortfallTotal),
      peakPrivateAnnual: round(peakPrivateAnnual),
      thresholdBreached: peakPrivateAnnual > PENSION_INCOME_TAX.separateTaxationThreshold,
    },
    timeline,
  };
}

/* ── 입력 정규화 ────────────────────────────────────────────── */
export function normalizeInput(raw) {
  const n = (v, d = 0) => (Number.isFinite(Number(v)) ? Number(v) : d);
  const p = raw.profile || {};
  const currentAge = clamp(n(p.currentAge, 40), 19, 100);
  const retireAge = clamp(n(p.retireAge, 60), currentAge, 100);
  const lifeExpectancy = clamp(n(p.lifeExpectancy, 90), retireAge + 1, 120);

  const a = raw.assumptions || {};
  const npsRaw = raw.nps || {};
  const houseRaw = raw.housing || {};

  return {
    profile: {
      currentAge, retireAge, lifeExpectancy,
      monthlyIncome: Math.max(0, n(p.monthlyIncome, 0)),
      desiredMonthlySpend: Math.max(0, n(p.desiredMonthlySpend, 0)),
    },
    nps: {
      mode: npsRaw.mode === 'estimate' ? 'estimate' : 'direct',
      directMonthly: Math.max(0, n(npsRaw.directMonthly, 0)),
      joinYears: Math.max(0, n(npsRaw.joinYears, 0)),
      avgMonthlyIncome: Math.max(0, n(npsRaw.avgMonthlyIncome, 0)),
      startAge: clamp(n(npsRaw.startAge, NPS.normalStartAge), NPS.earliestStartAge, NPS.latestStartAge),
    },
    severance: {
      balance: Math.max(0, n(raw.severance?.balance, 0)),
      monthlyContribution: Math.max(0, n(raw.severance?.monthlyContribution, 0)),
    },
    personal: {
      balance: Math.max(0, n(raw.personal?.balance, 0)),
      monthlyContribution: Math.max(0, n(raw.personal?.monthlyContribution, 0)),
    },
    other: {
      assets: Math.max(0, n(raw.other?.assets, 0)),
      monthlySaving: Math.max(0, n(raw.other?.monthlySaving, 0)),
    },
    housing: {
      enabled: Boolean(houseRaw.enabled),
      houseValue: Math.max(0, n(houseRaw.houseValue, 0)),
      startAge: clamp(n(houseRaw.startAge, 65), HOUSING_PENSION.minAge, 100),
    },
    assumptions: {
      inflation: n(a.inflation, 0.023),
      salaryGrowth: n(a.salaryGrowth, 0.03),
      returnPre: n(a.returnPre, 0.05),
      returnPost: n(a.returnPost, 0.035),
    },
  };
}
