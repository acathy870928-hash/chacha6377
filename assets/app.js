/**
 * 화면 조립 — 입력을 읽고, 엔진을 돌리고, 결과를 그립니다.
 * 계산 로직은 여기에 없습니다(engine.js / rules.js).
 */

import { simulate } from './engine.js';
import { diagnose, buildChecklist, overallScore, scoreGrade } from './rules.js';
import {
  renderAssetChart, renderIncomeStack, renderCompositionBar,
  renderScoreMeter, renderTable, money,
} from './charts.js';
import { POLICY_VERSION, BENCHMARKS } from './policy.js';

const $ = (sel) => document.querySelector(sel);
const MAN = 10_000; // 만원 → 원

const num = (id) => Number($(`#${id}`).value) || 0;
const manwon = (id) => num(id) * MAN;
const percent = (id) => num(id) / 100;

const STORAGE_KEY = 'pension-planner:v1';
const THEME_KEY = 'pension-planner:theme';

let npsMode = 'direct';

/* ── 입력 수집 ──────────────────────────────────────────── */
function readForm() {
  return {
    profile: {
      currentAge: num('currentAge'),
      retireAge: num('retireAge'),
      lifeExpectancy: num('lifeExpectancy'),
      monthlyIncome: manwon('monthlyIncome'),
      desiredMonthlySpend: manwon('desiredMonthlySpend'),
    },
    nps: {
      mode: npsMode,
      directMonthly: manwon('npsDirect'),
      joinYears: num('npsJoinYears'),
      avgMonthlyIncome: manwon('npsAvgIncome'),
      startAge: num('npsStartAge'),
    },
    severance: { balance: manwon('sevBalance'), monthlyContribution: manwon('sevMonthly') },
    personal: { balance: manwon('perBalance'), monthlyContribution: manwon('perMonthly') },
    other: { assets: manwon('otherAssets'), monthlySaving: manwon('otherMonthly') },
    housing: {
      enabled: $('#housingEnabled').checked,
      houseValue: manwon('houseValue'),
      startAge: num('houseStartAge'),
    },
    assumptions: {
      inflation: percent('inflation'),
      salaryGrowth: percent('salaryGrowth'),
      returnPre: percent('returnPre'),
      returnPost: percent('returnPost'),
    },
  };
}

/* ── 결과 렌더 ──────────────────────────────────────────── */
const pctText = (v) => `${(v * 100).toFixed(1)}%`;

function renderStats(result) {
  const { metrics, inputsResolved } = result;
  const depletion = metrics.depletionAge === null
    ? { value: '고갈 없음', sub: `${metrics.lifeExpectancy}세까지 유지` }
    : { value: `${metrics.depletionAge}세`, sub: `이후 ${metrics.lifeExpectancy - metrics.depletionAge}년 무방비` };

  const items = [
    { label: '자산 고갈 시점', value: depletion.value, sub: depletion.sub },
    {
      label: '생활비 충족률',
      value: pctText(metrics.fundedRatio),
      sub: metrics.totalShortfallPv > 0 ? `부족 ${money(metrics.totalShortfallPv)}원` : '전액 조달',
    },
    {
      label: '소득대체율',
      value: pctText(metrics.replacementRate),
      sub: `적정 ${pctText(BENCHMARKS.targetReplacementRate)} · 은퇴 직전 ${money(inputsResolved.preRetirementMonthlyIncome)}/월`,
    },
    {
      label: '은퇴 첫해 월 소득',
      value: `${money(metrics.firstYearMonthlyIncome)}원`,
      sub: `희망 ${money(metrics.desiredMonthlySpend)}원`,
    },
    {
      label: '은퇴 시점 총자산',
      value: `${money(metrics.retirementAssets)}원`,
      sub: `${inputsResolved.yearsToRetire}년 뒤 · 오늘 가치`,
    },
    {
      label: '평생 보장 소득',
      value: `${money(metrics.guaranteedMonthly)}원/월`,
      sub: `국민연금 ${money(inputsResolved.npsMonthly)}원 포함`,
    },
    {
      label: '필요 추가 저축',
      value: metrics.requiredExtraMonthlySaving > 0 ? `${money(metrics.requiredExtraMonthlySaving)}원/월` : '없음',
      sub: metrics.requiredExtraMonthlySaving > 0 ? '부족액을 은퇴까지 메우려면' : '현재 계획으로 충분',
    },
    {
      label: '소득 공백기',
      value: metrics.bridgeYears > 0 ? `${metrics.bridgeYears}년` : '없음',
      sub: metrics.bridgeYears > 0 ? '은퇴 후 국민연금 개시 전까지' : '은퇴 즉시 국민연금 수급',
    },
  ];

  $('#stats').innerHTML = items.map((it) => `
    <div class="stat">
      <dt>${it.label}</dt>
      <dd>${it.value}<span class="stat-sub">${it.sub}</span></dd>
    </div>`).join('');
}

function renderFindings(findings) {
  const tag = { critical: '위험', warning: '주의', info: '참고', good: '양호' };
  $('#findings').innerHTML = findings.map((f) => `
    <li class="finding sev-${f.severity}">
      <div class="finding-head">
        <span class="sev-tag">${tag[f.severity]}</span>
        <h3>${f.title}</h3>
      </div>
      <p>${f.body}</p>
      <p class="action">${f.action}</p>
    </li>`).join('');
}

function renderChecklist(findings) {
  const items = buildChecklist(findings);
  $('#checklist').innerHTML = items.length
    ? items.map((c) => `<li><span class="when">${c.when}</span><span>${c.what}<span class="why">${c.why}</span></span></li>`).join('')
    : '<li>지금 당장 손봐야 할 항목이 없습니다. 연 1회 재점검만 하세요.</li>';
}

/* ── 시나리오 비교 ──────────────────────────────────────── */
const SCENARIOS = [
  {
    label: '은퇴를 3년 미루면',
    apply: (i) => ({ ...i, profile: { ...i.profile, retireAge: i.profile.retireAge + 3 } }),
  },
  {
    label: '월 20만원을 더 저축하면',
    apply: (i) => ({ ...i, personal: { ...i.personal, monthlyContribution: i.personal.monthlyContribution + 20 * MAN } }),
  },
  {
    label: '국민연금을 70세로 연기하면',
    apply: (i) => ({ ...i, nps: { ...i.nps, startAge: 70 } }),
  },
  {
    label: '국민연금을 60세로 앞당기면',
    apply: (i) => ({ ...i, nps: { ...i.nps, startAge: 60 } }),
  },
  {
    label: '생활비를 월 20만원 줄이면',
    apply: (i) => ({
      ...i,
      profile: { ...i.profile, desiredMonthlySpend: Math.max(0, i.profile.desiredMonthlySpend - 20 * MAN) },
    }),
  },
  {
    label: '수익률이 1%p 낮아지면',
    apply: (i) => ({
      ...i,
      assumptions: {
        ...i.assumptions,
        returnPre: Math.max(0, i.assumptions.returnPre - 0.01),
        returnPost: Math.max(0, i.assumptions.returnPost - 0.01),
      },
    }),
  },
];

function renderScenarios(input, baseResult) {
  const baseScore = overallScore(baseResult, diagnose(baseResult, input));
  const baseDepletion = baseResult.metrics.depletionAge;

  const rows = SCENARIOS.map((s) => {
    const alt = s.apply(structuredClone(input));
    const res = simulate(alt);
    const score = overallScore(res, diagnose(res, alt));
    const delta = score - baseScore;
    const dep = res.metrics.depletionAge;

    let depText;
    if (dep === null && baseDepletion === null) depText = '고갈 없음 유지';
    else if (dep === null) depText = '고갈이 사라집니다';
    else if (baseDepletion === null) depText = `${dep}세에 고갈됩니다`;
    else depText = `고갈 ${dep}세 (${dep - baseDepletion >= 0 ? '+' : ''}${dep - baseDepletion}년)`;

    const tone = delta > 0.5 ? 'up' : delta < -0.5 ? 'down' : '';
    const sign = delta > 0 ? '+' : '';
    return `<div>
      <label><span>${s.label}</span><b>${score}점 <em style="font-style:normal;color:var(--text-muted)">(${sign}${delta.toFixed(0)})</em></b></label>
      <div class="score-meter"><div class="score-meter-fill ${tone === 'down' ? 'tone-critical' : ''}" style="width:${Math.max(2, score)}%"></div></div>
      <p class="scenario-delta ${tone}">${depText} · 충족률 ${pctText(res.metrics.fundedRatio)}</p>
    </div>`;
  }).join('');

  $('#scenarios').innerHTML = rows;
}

/* ── AI 브리핑 ──────────────────────────────────────────── */
let aiAbort = null;

function aiPayload(input, result, findings, score) {
  const { metrics, inputsResolved } = result;
  return {
    score,
    metrics: {
      고갈나이: metrics.depletionAge,
      기대수명: metrics.lifeExpectancy,
      생활비충족률: Number((metrics.fundedRatio * 100).toFixed(1)),
      소득대체율: Number((metrics.replacementRate * 100).toFixed(1)),
      은퇴첫해월소득: metrics.firstYearMonthlyIncome,
      희망월생활비: metrics.desiredMonthlySpend,
      은퇴시점총자산: metrics.retirementAssets,
      평생보장월소득: metrics.guaranteedMonthly,
      필요추가월저축: metrics.requiredExtraMonthlySaving,
      소득공백기년수: metrics.bridgeYears,
      국민연금월액: inputsResolved.npsMonthly,
    },
    profile: {
      현재나이: input.profile.currentAge,
      은퇴나이: input.profile.retireAge,
      국민연금개시나이: input.nps.startAge,
    },
    findings: findings.map((f) => ({ 등급: f.severity, 제목: f.title, 조치: f.action })),
  };
}

async function runAi(payload) {
  const mount = $('#ai-mount');
  if (aiAbort) aiAbort.abort();
  aiAbort = new AbortController();

  mount.innerHTML = '<p class="ai-status">브리핑을 작성하는 중…</p>';
  try {
    const res = await fetch('/api/advisor', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload),
      signal: aiAbort.signal,
    });

    if (res.status === 503 || res.status === 404) {
      mount.innerHTML = `<div class="ai-disabled">
        AI 브리핑이 꺼져 있습니다. 위의 진단·시나리오는 <b>AI 없이 전부 동작</b>합니다.<br>
        켜려면 배포 환경에 <code>ANTHROPIC_API_KEY</code> 환경변수를 설정하세요.</div>`;
      return;
    }
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || `요청 실패 (${res.status})`);
    mount.innerHTML = `<div class="ai-body"></div>`;
    mount.querySelector('.ai-body').textContent = data.text;
  } catch (err) {
    if (err.name === 'AbortError') return;
    mount.innerHTML = `<p class="ai-status">브리핑을 불러오지 못했습니다: ${err.message}</p>`;
  }
}

/* ── 메인 파이프라인 ────────────────────────────────────── */
let lastPayload = null;

function run() {
  const input = readForm();
  const result = simulate(input);
  const findings = diagnose(result, input);
  const score = overallScore(result, findings);

  renderScoreMeter($('#score'), score, scoreGrade(score));
  renderStats(result);
  renderAssetChart($('#chart-assets'), result.timeline, { depletionAge: result.metrics.depletionAge });
  renderIncomeStack($('#chart-income'), result.timeline);
  renderCompositionBar($('#chart-composition'), [
    { label: '퇴직연금', value: result.metrics.assetsAtRetirement.severance, varName: '--series-2' },
    { label: '개인연금', value: result.metrics.assetsAtRetirement.personal, varName: '--series-3' },
    { label: '기타 금융자산', value: result.metrics.assetsAtRetirement.other, varName: '--series-4' },
  ]);
  renderFindings(findings);
  renderChecklist(findings);
  renderScenarios(input, result);

  if (!$('#table-view').hidden) renderTable($('#table-view'), result.timeline);

  lastPayload = aiPayload(input, result, findings, score);
  return { input, result };
}

const debounce = (fn, ms = 200) => {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
};
const runDebounced = debounce(run, 180);

/* ── 이벤트 배선 ────────────────────────────────────────── */
function setNpsMode(mode) {
  npsMode = mode;
  document.querySelectorAll('[data-nps-mode]').forEach((b) => {
    b.setAttribute('aria-pressed', String(b.dataset.npsMode === mode));
  });
  document.querySelectorAll('[data-nps]').forEach((f) => { f.hidden = f.dataset.nps !== mode; });
}

function applyTheme(theme) {
  if (theme === 'light' || theme === 'dark') document.documentElement.setAttribute('data-theme', theme);
  else document.documentElement.removeAttribute('data-theme');
}

function currentTheme() {
  return document.documentElement.getAttribute('data-theme')
    || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
}

function serialize() {
  const data = { npsMode, fields: {} };
  document.querySelectorAll('#form input').forEach((i) => {
    data.fields[i.id] = i.type === 'checkbox' ? i.checked : i.value;
  });
  return data;
}

function restore(data) {
  if (!data || !data.fields) return;
  for (const [id, v] of Object.entries(data.fields)) {
    const input = document.getElementById(id);
    if (!input) continue;
    if (input.type === 'checkbox') input.checked = Boolean(v);
    else input.value = v;
  }
  setNpsMode(data.npsMode === 'estimate' ? 'estimate' : 'direct');
  $('[data-housing]').hidden = !$('#housingEnabled').checked;
}

function init() {
  $('#policy-year').textContent = POLICY_VERSION.label;

  try {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved) applyTheme(saved);
  } catch { /* 저장소 접근이 막혀 있어도 동작해야 합니다 */ }

  document.querySelectorAll('[data-nps-mode]').forEach((btn) => {
    btn.addEventListener('click', () => { setNpsMode(btn.dataset.npsMode); run(); });
  });

  $('#housingEnabled').addEventListener('change', (e) => {
    $('[data-housing]').hidden = !e.target.checked;
    run();
  });

  $('#form').addEventListener('input', runDebounced);

  $('#btn-theme').addEventListener('click', () => {
    const next = currentTheme() === 'dark' ? 'light' : 'dark';
    applyTheme(next);
    try { localStorage.setItem(THEME_KEY, next); } catch { /* noop */ }
  });

  $('#btn-print').addEventListener('click', () => window.print());

  $('#btn-table').addEventListener('click', (e) => {
    const view = $('#table-view');
    const show = view.hidden;
    view.hidden = !show;
    e.target.setAttribute('aria-expanded', String(show));
    e.target.textContent = show ? '표 닫기' : '표로 보기';
    if (show) renderTable(view, simulate(readForm()).timeline);
  });

  $('#btn-save').addEventListener('click', (e) => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(serialize()));
      e.target.textContent = '저장됨';
      setTimeout(() => { e.target.textContent = '저장'; }, 1400);
    } catch {
      e.target.textContent = '저장 불가';
      setTimeout(() => { e.target.textContent = '저장'; }, 1400);
    }
  });

  $('#btn-load').addEventListener('click', (e) => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) { e.target.textContent = '저장된 값 없음'; setTimeout(() => { e.target.textContent = '불러오기'; }, 1400); return; }
      restore(JSON.parse(raw));
      run();
    } catch { /* 손상된 저장값은 무시합니다 */ }
  });

  $('#btn-reset').addEventListener('click', () => {
    $('#form').reset();
    setNpsMode('direct');
    $('[data-housing]').hidden = true;
    run();
  });

  $('#ai-card').addEventListener('click', (e) => {
    if (e.target.id === 'btn-ai' && lastPayload) runAi(lastPayload);
  });

  setNpsMode('direct');
  $('[data-housing]').hidden = !$('#housingEnabled').checked;
  run();

  $('#ai-mount').innerHTML =
    '<div class="btn-row"><button type="button" class="ghost-btn" id="btn-ai">이 결과를 AI로 해석하기</button></div>';

  window.addEventListener('resize', debounce(() => run(), 250));
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
else init();

export { readForm, run };
