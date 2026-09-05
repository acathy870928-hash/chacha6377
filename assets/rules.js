/**
 * 진단 룰 엔진
 * ---------------------------------------------------------------
 * 계산 결과(metrics/timeline)를 읽어 "무엇이 위험한가"를 판정합니다.
 * AI가 아니라 명시적 규칙이 판정하므로, 결과가 항상 재현 가능합니다.
 */

import {
  NPS, PRIVATE_PENSION, PENSION_INCOME_TAX, RETIREMENT_PENSION, BENCHMARKS,
} from './policy.js';
import { taxCreditDiagnosis } from './engine.js';

const SEVERITY_ORDER = { critical: 0, warning: 1, info: 2, good: 3 };

const won = (v) => `${Math.round(v).toLocaleString('ko-KR')}원`;
const manwon = (v) => {
  const n = Math.round(v);
  const abs = Math.abs(n);
  if (abs >= 100_000_000) {
    const eok = n / 100_000_000;
    return `${eok.toFixed(abs >= 1_000_000_000 ? 0 : 1)}억원`;
  }
  return `${Math.round(n / 10_000).toLocaleString('ko-KR')}만원`;
};
const pct = (v) => `${(v * 100).toFixed(1)}%`;

/**
 * @param {object} result  simulate()의 반환값
 * @param {object} input   normalize 이전 사용자 입력
 * @returns {Array<{id,severity,title,body,action}>}
 */
export function diagnose(result, input) {
  const { metrics, inputsResolved, timeline } = result;
  const findings = [];
  const add = (f) => findings.push(f);

  /* 1. 소득대체율 */
  if (metrics.replacementRate < BENCHMARKS.minReplacementRate && metrics.fundedRatio < 0.95) {
    add({
      id: 'replacement-critical',
      severity: 'critical',
      title: `소득대체율 ${pct(metrics.replacementRate)} — 최소 방어선 미달`,
      body: `은퇴 직전 소득(${manwon(inputsResolved.preRetirementMonthlyIncome)}/월) 대비 은퇴 첫해 실수령이 ${manwon(metrics.firstYearMonthlyIncome)}/월에 그칩니다. 국제적으로 권고되는 적정 대체율은 ${pct(BENCHMARKS.targetReplacementRate)}, 최소 방어선은 ${pct(BENCHMARKS.minReplacementRate)}입니다.`,
      action: `월 ${manwon(metrics.requiredExtraMonthlySaving)} 추가 적립 또는 은퇴 시점 연기를 우선 검토하세요.`,
    });
  } else if (metrics.replacementRate < BENCHMARKS.targetReplacementRate) {
    add({
      id: 'replacement-warning',
      // 목표 생활비를 온전히 조달하고 있다면 이것은 '선택'이지 '결함'이 아닙니다.
      severity: metrics.fundedRatio >= 0.95 ? 'info' : 'warning',
      title: `소득대체율 ${pct(metrics.replacementRate)} — 적정선(${pct(BENCHMARKS.targetReplacementRate)})에 미달`,
      body: '생활수준을 유지하기에는 다소 부족합니다. 다만 최소 방어선은 넘겼습니다.',
      action: '지출 구조 조정 또는 연금저축 납입 증액으로 격차를 좁힐 수 있습니다.',
    });
  } else {
    add({
      id: 'replacement-good',
      severity: 'good',
      title: `소득대체율 ${pct(metrics.replacementRate)} — 적정 수준`,
      body: '은퇴 직후 생활수준 유지에 큰 무리가 없는 구조입니다.',
      action: '현재 적립 계획을 유지하고 연 1회 재점검하세요.',
    });
  }

  /* 2. 자산 고갈 리스크 */
  if (metrics.depletionAge !== null) {
    const yearsUncovered = metrics.lifeExpectancy - metrics.depletionAge;
    add({
      id: 'depletion',
      severity: yearsUncovered >= 10 ? 'critical' : 'warning',
      title: `${metrics.depletionAge}세에 자산 고갈 — 이후 ${yearsUncovered}년이 무방비`,
      body: `기대수명 ${metrics.lifeExpectancy}세까지 필요한 생활비의 ${pct(1 - metrics.fundedRatio)}가 조달되지 않습니다. 부족액은 현재가치로 ${manwon(metrics.totalShortfallPv)}입니다.`,
      action: `고갈 이후에도 남는 것은 국민연금뿐입니다(월 ${manwon(inputsResolved.npsMonthly)}). 종신형 연금 전환이나 주택연금으로 '죽을 때까지 나오는 소득'을 늘리는 것이 근본 해법입니다.`,
    });
  } else {
    add({
      id: 'depletion-none',
      severity: 'good',
      title: `기대수명 ${metrics.lifeExpectancy}세까지 자산이 고갈되지 않습니다`,
      body: `필요 생활비의 ${pct(metrics.fundedRatio)}를 조달할 수 있는 구조입니다.`,
      action: '기대수명을 5년 더 늘려 재계산해 보고 여유가 유지되는지 확인하세요.',
    });
  }

  /* 3. 소득 공백기 (은퇴 ~ 국민연금 개시) */
  if (metrics.bridgeYears > 0) {
    const bridge = timeline.filter((r) => r.npsNet === 0 && r.age < NPS.latestStartAge + 1);
    const avgShortfall = bridge.length ? bridge.reduce((s, r) => s + r.shortfall, 0) / bridge.length : 0;
    add({
      id: 'bridge-gap',
      severity: avgShortfall > 0 ? 'critical' : 'warning',
      title: `소득 공백기 ${metrics.bridgeYears}년 (${input.profile?.retireAge ?? '?'}세 은퇴 → ${input.nps?.startAge ?? NPS.normalStartAge}세 수급)`,
      body: avgShortfall > 0
        ? `이 기간 동안 매년 평균 ${manwon(avgShortfall)}이 부족합니다. 국민연금이 아직 나오지 않는데 생활비는 그대로 나가는, 은퇴설계에서 가장 위험한 구간입니다.`
        : `이 기간은 사적연금과 금융자산만으로 버텨야 합니다. 현재 계획으로는 메워지지만, 이 구간의 자산 소진 속도가 가장 빠릅니다.`,
      action: '공백기 전용 재원(예금·채권 등 안전자산)을 별도로 떼어 두거나, 국민연금 조기수령과 재취업 소득을 비교 검토하세요.',
    });
  }

  /* 4. 세액공제 한도 미사용 */
  const annualSalary = (input.profile?.monthlyIncome ?? 0) * 12;
  const credit = taxCreditDiagnosis({
    annualSalary,
    annualSavingContribution: (input.personal?.monthlyContribution ?? 0) * 12,
    annualIrpContribution: (input.severance?.monthlyContribution ?? 0) * 12,
  });
  if (credit.unusedRoom > 0) {
    add({
      id: 'tax-credit-room',
      severity: credit.usageRatio < 0.5 ? 'warning' : 'info',
      title: `세액공제 한도 ${manwon(credit.unusedRoom)} 미사용 — 매년 ${won(credit.forgoneCredit)} 손해`,
      body: `연금저축·IRP 합산 세액공제 한도는 ${manwon(PRIVATE_PENSION.combinedLimit)}(연금저축 단독 ${manwon(PRIVATE_PENSION.annuitySavingLimit)})입니다. 현재 ${manwon(credit.eligibleAmount)}만 인정받아 공제액이 ${won(credit.currentCredit)}에 머뭅니다. 적용 공제율은 ${pct(credit.rate)}입니다.`,
      action: `한도를 채우면 연 ${won(credit.maxCredit)}까지 환급받습니다. 이것은 시장 수익률과 무관하게 확정적으로 얻는 ${pct(credit.rate)} 수익입니다.`,
    });
  } else {
    add({
      id: 'tax-credit-full',
      severity: 'good',
      title: `세액공제 한도를 모두 활용 중 (연 ${won(credit.currentCredit)} 환급)`,
      body: `연금저축·IRP 합산 ${manwon(PRIVATE_PENSION.combinedLimit)} 한도를 채우고 있습니다.`,
      action: `한도 초과분은 세액공제를 받지 못하지만 과세이연 효과는 있습니다(연간 납입한도 ${manwon(PRIVATE_PENSION.contributionCapPerYear)}).`,
    });
  }

  /* 5. 사적연금 연 1,500만원 벽 */
  if (metrics.thresholdBreached) {
    add({
      id: 'threshold-1500',
      severity: 'warning',
      title: `사적연금 수령액이 연 ${manwon(PENSION_INCOME_TAX.separateTaxationThreshold)}을 초과합니다`,
      body: `최대 연 ${manwon(metrics.peakPrivateAnnual)}을 수령하게 됩니다. 이 선을 넘으면 3.3~5.5% 저율 분리과세가 끝나고, 전액에 대해 종합과세 또는 ${pct(PENSION_INCOME_TAX.highSeparateRate)} 분리과세 중 선택해야 합니다.`,
      action: '수령 기간을 늘려 연간 수령액을 1,500만원 아래로 분산하거나, 일부를 비과세 재원(기타 금융자산)으로 대체해 인출하세요.',
    });
  }

  /* 6. 국민연금 가입기간 */
  if (input.nps?.mode === 'estimate' && (input.nps?.joinYears ?? 0) < NPS.minJoinYears) {
    add({
      id: 'nps-min-years',
      severity: 'critical',
      title: `국민연금 가입기간 ${input.nps.joinYears}년 — 최소 ${NPS.minJoinYears}년 미달`,
      body: '가입기간이 10년에 미치지 못하면 노령연금을 받지 못하고 반환일시금으로 정산됩니다. 평생 나오는 소득이 통째로 사라집니다.',
      action: '임의가입·추후납부(추납)·임의계속가입으로 최소 가입기간을 채우는 것이 최우선 과제입니다.',
    });
  }

  /* 7. 국민연금 개시연령 전략 */
  if (input.nps?.startAge && input.nps.startAge < NPS.normalStartAge) {
    const lossPct = NPS.earlyPenaltyPerYear * (NPS.normalStartAge - input.nps.startAge);
    add({
      id: 'nps-early',
      severity: 'warning',
      title: `국민연금 조기수령 — 평생 ${pct(lossPct)} 감액`,
      body: '조기수령 감액은 일시적인 것이 아니라 사망할 때까지 영구적으로 적용됩니다. 일반적으로 76~78세를 넘겨 생존하면 정상수령이 유리해집니다.',
      action: '공백기 자금을 다른 재원으로 메울 수 있다면 정상수령이 장수 리스크에 더 강합니다.',
    });
  } else if (input.nps?.startAge > NPS.normalStartAge) {
    const gainPct = NPS.deferBonusPerYear * (input.nps.startAge - NPS.normalStartAge);
    add({
      id: 'nps-defer',
      severity: 'info',
      title: `국민연금 연기수령 — 평생 ${pct(gainPct)} 증액`,
      body: '연기수령은 물가연동되는 종신소득을 늘리는, 장수 리스크에 대한 가장 저렴한 보험입니다.',
      action: '연기 기간의 생활비를 다른 재원으로 감당할 수 있는지 현금흐름표에서 확인하세요.',
    });
  }

  /* 8. 연금계좌 개시 가능연령보다 이른 은퇴 */
  const retireAge = input.profile?.retireAge ?? 60;
  if (retireAge < RETIREMENT_PENSION.minPensionAgeForAccount) {
    add({
      id: 'early-retire-account',
      severity: 'critical',
      title: `${retireAge}세 은퇴 — 연금계좌는 ${RETIREMENT_PENSION.minPensionAgeForAccount}세부터 인출 가능`,
      body: `퇴직연금·연금저축은 ${RETIREMENT_PENSION.minPensionAgeForAccount}세 이전에 연금으로 받을 수 없습니다. 중도 해지하면 기타소득세 ${pct(0.165)}가 부과되어 세액공제로 받은 혜택을 되돌려주게 됩니다.`,
      action: `${retireAge}세부터 ${RETIREMENT_PENSION.minPensionAgeForAccount}세까지를 버틸 별도 재원이 반드시 필요합니다.`,
    });
  }

  /* 9. 3층 구조 편중 */
  const layer = {
    국민연금: inputsResolved.npsMonthly * 12 * Math.max(0, metrics.lifeExpectancy - (input.nps?.startAge ?? NPS.normalStartAge)),
    퇴직연금: metrics.assetsAtRetirement.severance,
    개인연금: metrics.assetsAtRetirement.personal,
    기타자산: metrics.assetsAtRetirement.other,
  };
  const layerTotal = Object.values(layer).reduce((a, b) => a + b, 0);
  if (layerTotal > 0) {
    const [topName, topValue] = Object.entries(layer).sort((a, b) => b[1] - a[1])[0];
    const share = topValue / layerTotal;
    if (share > 0.7) {
      add({
        id: 'concentration',
        severity: 'warning',
        title: `노후 재원의 ${pct(share)}가 '${topName}' 한 곳에 집중`,
        body: '한 층에 편중되면 그 층의 제도 변경·시장 충격·과세 변화가 노후 전체를 흔듭니다.',
        action: '3층(국민·퇴직·개인) 균형을 맞추면 제도 리스크와 과세 리스크가 동시에 분산됩니다.',
      });
    }
  }

  /* 10. 주택연금 실질가치 하락 */
  if (input.housing?.enabled) {
    const first = timeline.find((r) => r.housingNet > 0);
    const last = timeline.at(-1);
    if (first && last.housingNet > 0) {
      const erosion = 1 - last.housingNet / first.housingNet;
      add({
        id: 'housing-erosion',
        severity: 'info',
        title: `주택연금은 명목 고정 — ${metrics.lifeExpectancy}세에 실질 구매력 ${pct(erosion)} 감소`,
        body: `가입 시점 월 ${manwon(inputsResolved.housingMonthlyNominal)}으로 확정되며 물가에 연동되지 않습니다. 국민연금과 성격이 완전히 다릅니다.`,
        action: '주택연금은 "물가를 이기는 소득"이 아니라 "끊기지 않는 소득"으로 취급하고, 물가 방어는 국민연금과 투자자산에 맡기세요.',
      });
    }
  }

  /* 11. 가정의 낙관성 점검 */
  const a = input.assumptions || {};
  if ((a.returnPre ?? 0.05) > 0.08) {
    add({
      id: 'optimistic-return',
      severity: 'warning',
      title: `은퇴 전 수익률 가정 ${pct(a.returnPre)} — 낙관적입니다`,
      body: '장기 실질수익률을 높게 잡으면 부족액이 과소평가됩니다. 30년 계획에서 이 가정 하나가 결과를 두 배로 왜곡할 수 있습니다.',
      action: '수익률을 5%로 낮춰 다시 계산해 보고, 그 결과에서도 견딜 수 있는 계획인지 확인하세요.',
    });
  }
  if ((a.inflation ?? 0.023) < 0.015) {
    add({
      id: 'optimistic-inflation',
      severity: 'warning',
      title: `물가상승률 가정 ${pct(a.inflation)} — 과소평가 가능성`,
      body: '물가를 낮게 잡으면 30년 뒤 필요 생활비가 크게 축소되어 계산됩니다.',
      action: '2~2.5% 구간으로 다시 계산해 결과의 민감도를 확인하세요.',
    });
  }

  /* 12. 장수 리스크 */
  if (metrics.lifeExpectancy < 90) {
    add({
      id: 'longevity',
      severity: 'info',
      title: `기대수명 ${metrics.lifeExpectancy}세 가정 — 장수 리스크 점검 필요`,
      body: '평균 기대수명은 절반이 그보다 오래 산다는 뜻입니다. 은퇴설계는 평균이 아니라 "오래 살 경우"에 맞춰야 합니다.',
      action: '기대수명을 95세로 놓고 다시 계산해 보세요. 그때도 버틴다면 계획이 견고한 것입니다.',
    });
  }

  return findings.sort((x, y) => SEVERITY_ORDER[x.severity] - SEVERITY_ORDER[y.severity]);
}

/** 진단 결과에서 실행 체크리스트를 만든다 */
export function buildChecklist(findings) {
  const priority = { critical: '지금 바로', warning: '3개월 안에', info: '올해 안에', good: '유지' };
  return findings
    .filter((f) => f.severity !== 'good')
    .map((f) => ({ when: priority[f.severity], what: f.action, why: f.title }));
}

/** 종합 점수 (0~100) */
export function overallScore(result, findings) {
  const { metrics } = result;
  const funded = Math.max(0, Math.min(1, metrics.fundedRatio));
  const rr = Math.max(0, Math.min(1, metrics.replacementRate / BENCHMARKS.targetReplacementRate));

  // 부족액과 대체율 미달은 비선형으로 더 무겁게 반영합니다.
  // 본인이 정한 목표 생활비를 온전히 조달한다면, 대체율이 낮다는 이유로
  // 다시 감점하지 않습니다(의도적으로 검소한 노후를 택한 경우).
  const rrScored = Math.max(rr, funded);
  let score = 40 * Math.pow(funded, 2) + 30 * Math.pow(rrScored, 1.5);
  score += metrics.depletionAge === null
    ? 20
    : Math.max(0, 20 * ((metrics.depletionAge - 60) / Math.max(1, metrics.lifeExpectancy - 60)));

  const penalties = findings.filter((f) => f.severity === 'critical').length * 5
    + findings.filter((f) => f.severity === 'warning').length * 2;
  score += Math.max(0, 10 - penalties);
  return Math.round(Math.max(0, Math.min(100, score)));
}

export function scoreGrade(score) {
  if (score >= 85) return { grade: 'A', label: '안정', tone: 'good' };
  if (score >= 70) return { grade: 'B', label: '양호', tone: 'good' };
  if (score >= 55) return { grade: 'C', label: '주의', tone: 'warning' };
  if (score >= 40) return { grade: 'D', label: '취약', tone: 'warning' };
  return { grade: 'E', label: '위험', tone: 'critical' };
}
