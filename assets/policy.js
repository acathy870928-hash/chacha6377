/**
 * 연금·세제 정책 상수 (기준: 2026년)
 * ---------------------------------------------------------------
 * 이 파일은 "매년 바뀌는 값"만 격리해 둔 곳입니다.
 * 세법·연금제도가 개정되면 이 파일 하나만 갱신하면 됩니다.
 * 계산 로직(engine.js)에는 어떤 숫자도 하드코딩하지 않습니다.
 */

export const POLICY_VERSION = {
  year: 2026,
  label: '2026년 기준',
  note: '세법·연금제도 개정 시 이 파일을 갱신하세요. 표시된 값은 참고용이며 실제 적용값은 관계 법령을 확인해야 합니다.',
};

/* ── 1층: 국민연금 ───────────────────────────────────────────── */
export const NPS = {
  // 전체 가입자 평균소득월액(A값). 매년 고시됩니다.
  aValue: 3_089_062,
  aValueNote: 'A값(전체 가입자 평균소득월액) — 최근 고시 기준',

  // 기본연금액 산식의 비례상수. 소득대체율 43% 기준 = 1.29
  // 기본연금액(연) = 상수 × (A + B) × (1 + 0.05 × n/12),  n = 20년 초과 가입월수
  constant: 1.29,
  targetReplacementRate: 0.43,

  minJoinYears: 10,          // 노령연금 최소 가입기간
  normalStartAge: 65,        // 1969년생 이후 수급개시연령
  earliestStartAge: 60,      // 조기노령연금 하한
  latestStartAge: 70,        // 연기연금 상한

  earlyPenaltyPerYear: 0.06,   // 조기수령: 1년당 6% 감액
  deferBonusPerYear: 0.072,    // 연기수령: 1년당 7.2% 증액

  inflationLinked: true,       // 물가연동 → 실질가치 유지
};

/* ── 2층: 퇴직연금(DB/DC/IRP) ───────────────────────────────── */
export const RETIREMENT_PENSION = {
  // DC형 사용자부담금: 연간 임금총액의 1/12 (= 월 소득의 약 8.33%)
  dcEmployerRateOfMonthlyPay: 1 / 12,

  // 퇴직소득세 연금수령 감면율
  taxCutWithin10Years: 0.30,   // 연금수령 1~10년차: 30% 감면
  taxCutAfter10Years: 0.40,    // 11년차 이후: 40% 감면

  // 퇴직소득 실효세율 기본 가정(근속연수·환산급여에 따라 실제로는 크게 달라짐)
  defaultEffectiveSeveranceTaxRate: 0.03,

  minPensionAgeForAccount: 55, // 연금계좌 연금수령 개시 가능 연령
  minPensionYears: 10,         // 연금수령 요건: 10년 이상 분할
};

/* ── 3층: 개인연금(연금저축 / IRP) ──────────────────────────── */
export const PRIVATE_PENSION = {
  annuitySavingLimit: 6_000_000,   // 연금저축 단독 세액공제 한도
  combinedLimit: 9_000_000,        // 연금저축 + IRP 합산 한도

  // 세액공제율 (지방소득세 포함)
  highRate: 0.165,                 // 총급여 5,500만원 이하 (종합소득 4,500만원 이하)
  lowRate: 0.132,                  // 초과
  highRateSalaryCeiling: 55_000_000,

  contributionCapPerYear: 18_000_000, // 연금계좌 연간 납입한도(세액공제 여부 무관)
};

/* ── 연금 수령 단계 과세 ────────────────────────────────────── */
export const PENSION_INCOME_TAX = {
  // 사적연금 저율 분리과세(연령별) — 지방소득세 포함
  rateByAge: [
    { minAge: 80, rate: 0.033 },
    { minAge: 70, rate: 0.044 },
    { minAge: 55, rate: 0.055 },
  ],

  // 사적연금 연간 수령액이 이 금액을 넘으면 종합과세 또는 16.5% 분리과세 선택
  separateTaxationThreshold: 15_000_000,
  highSeparateRate: 0.165,

  // 연금소득공제 구간 (국민연금 등 공적연금 과세 계산용)
  deductionBrackets: [
    { upTo: 3_500_000, base: 0, rate: 1.00 },
    { upTo: 7_000_000, base: 3_500_000, rate: 0.40 },
    { upTo: 14_000_000, base: 4_900_000, rate: 0.20 },
    { upTo: Infinity, base: 6_300_000, rate: 0.10 },
  ],
  deductionCap: 9_000_000,
};

/* ── 종합소득세율 (지방소득세 별도 10%) ─────────────────────── */
export const INCOME_TAX_BRACKETS = [
  { upTo: 14_000_000, rate: 0.06, progressiveDeduction: 0 },
  { upTo: 50_000_000, rate: 0.15, progressiveDeduction: 1_260_000 },
  { upTo: 88_000_000, rate: 0.24, progressiveDeduction: 5_760_000 },
  { upTo: 150_000_000, rate: 0.35, progressiveDeduction: 15_440_000 },
  { upTo: 300_000_000, rate: 0.38, progressiveDeduction: 19_940_000 },
  { upTo: 500_000_000, rate: 0.40, progressiveDeduction: 25_940_000 },
  { upTo: 1_000_000_000, rate: 0.42, progressiveDeduction: 35_940_000 },
  { upTo: Infinity, rate: 0.45, progressiveDeduction: 65_940_000 },
];

export const LOCAL_INCOME_TAX_RATE = 0.10; // 소득세액의 10%
export const BASIC_DEDUCTION_PER_PERSON = 1_500_000;

/* ── 주택연금 (종신지급 정액형) ─────────────────────────────── */
export const HOUSING_PENSION = {
  minAge: 55,
  maxHouseValue: 1_200_000_000, // 가입 가능 주택가격 상한
  // 주택가격 1억원당 월지급금 (가입연령 기준, 원)
  monthlyPerHundredMillion: [
    { age: 55, amount: 153_000 },
    { age: 60, amount: 204_000 },
    { age: 65, amount: 274_000 },
    { age: 70, amount: 337_000 },
    { age: 75, amount: 431_000 },
    { age: 80, amount: 561_000 },
  ],
  inflationLinked: false, // 명목 고정 → 실질가치가 매년 하락
};

/* ── 시뮬레이션 기본 가정 ───────────────────────────────────── */
export const DEFAULT_ASSUMPTIONS = {
  inflation: 0.023,      // 물가상승률
  salaryGrowth: 0.030,   // 임금상승률
  returnPre: 0.050,      // 은퇴 전 운용수익률
  returnPost: 0.035,     // 은퇴 후 운용수익률
  lifeExpectancy: 90,    // 기대수명
};

/* ── 진단 기준선 ────────────────────────────────────────────── */
export const BENCHMARKS = {
  targetReplacementRate: 0.70, // 적정 소득대체율(국제 권고 70%)
  minReplacementRate: 0.50,    // 최소 방어선
  safeWithdrawalRate: 0.04,    // 안전인출률
};
