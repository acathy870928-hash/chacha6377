/**
 * 차트 렌더러 — 라이브러리 없는 순수 인라인 SVG
 * ---------------------------------------------------------------
 * · 색은 역할(role)로만 참조합니다. 실제 hex는 styles.css의 CSS 변수에 있고,
 *   라이트/다크 값이 그곳에서 한 번에 교체됩니다.
 * · 계열 색상은 고정 순서로만 배정합니다(순환 금지).
 * · 부족분은 계열색이 아니라 '상태색(critical)'을 씁니다 —
 *   상태는 시리즈가 아니기 때문입니다.
 */

const NS = 'http://www.w3.org/2000/svg';

export const SERIES = [
  { key: 'npsNet', label: '국민연금', varName: '--series-1' },
  { key: 'severanceWithdraw', label: '퇴직연금', varName: '--series-2' },
  { key: 'personalWithdraw', label: '개인연금', varName: '--series-3' },
  { key: 'otherWithdraw', label: '기타자산', varName: '--series-4' },
  { key: 'housingNet', label: '주택연금', varName: '--series-5' },
];

export const SHORTFALL = { key: 'shortfall', label: '부족', varName: '--status-critical' };

/* ── 표기 ──────────────────────────────────────────────────── */
export function money(v) {
  const n = Math.round(v);
  if (n === 0) return '0';
  const abs = Math.abs(n);
  if (abs >= 100_000_000) return `${(n / 100_000_000).toFixed(abs >= 1_000_000_000 ? 0 : 1)}억`;
  if (abs >= 10_000) return `${Math.round(n / 10_000).toLocaleString('ko-KR')}만`;
  return n.toLocaleString('ko-KR');
}
export const wonFull = (v) => `${Math.round(v).toLocaleString('ko-KR')}원`;

/* ── DOM 헬퍼 ──────────────────────────────────────────────── */
function el(tag, attrs = {}, text) {
  const node = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  if (text !== undefined) node.textContent = text;
  return node;
}

function niceCeil(v) {
  if (v <= 0) return 1;
  const mag = Math.pow(10, Math.floor(Math.log10(v)));
  const norm = v / mag;
  const step = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10;
  return step * mag;
}

function ensureTooltip(container) {
  container.style.position = container.style.position || 'relative';
  let tip = container.querySelector('.viz-tip');
  if (!tip) {
    tip = document.createElement('div');
    tip.className = 'viz-tip';
    tip.setAttribute('role', 'status');
    tip.hidden = true;
    container.appendChild(tip);
  }
  return tip;
}

function placeTip(container, tip, x, y) {
  const w = container.clientWidth;
  const tw = tip.offsetWidth || 180;
  let left = x + 14;
  if (left + tw > w - 8) left = x - tw - 14;
  tip.style.left = `${Math.max(4, left)}px`;
  tip.style.top = `${Math.max(4, y - 12)}px`;
}

/* ── 1) 자산 잔액 추이 (단일 계열 영역 + 선) ───────────────── */
export function renderAssetChart(container, timeline, opts = {}) {
  container.innerHTML = '';
  const tip = ensureTooltip(container);

  const W = 720, H = 300;
  const M = { top: 16, right: 16, bottom: 34, left: 56 };
  const iw = W - M.left - M.right;
  const ih = H - M.top - M.bottom;

  const svg = el('svg', {
    viewBox: `0 0 ${W} ${H}`, class: 'viz-svg', role: 'img',
    'aria-label': '은퇴 이후 연도별 잔여 자산 추이',
  });

  const maxY = niceCeil(Math.max(1, ...timeline.map((d) => d.balances.total)));
  const ages = timeline.map((d) => d.age);
  const x = (age) => M.left + ((age - ages[0]) / Math.max(1, ages.at(-1) - ages[0])) * iw;
  const y = (v) => M.top + ih - (v / maxY) * ih;

  // 격자 + y축 눈금 (되도록 눈에 띄지 않게)
  for (let i = 0; i <= 4; i++) {
    const v = (maxY / 4) * i;
    svg.appendChild(el('line', { x1: M.left, x2: M.left + iw, y1: y(v), y2: y(v), class: 'viz-grid' }));
    svg.appendChild(el('text', { x: M.left - 8, y: y(v) + 4, class: 'viz-axis-label', 'text-anchor': 'end' }, money(v)));
  }

  // x축 눈금 (5년 간격)
  for (const age of ages) {
    if (age % 5 !== 0 && age !== ages[0] && age !== ages.at(-1)) continue;
    svg.appendChild(el('text', { x: x(age), y: M.top + ih + 22, class: 'viz-axis-label', 'text-anchor': 'middle' }, `${age}`));
  }
  svg.appendChild(el('line', { x1: M.left, x2: M.left + iw, y1: y(0), y2: y(0), class: 'viz-baseline' }));

  const pts = timeline.map((d) => [x(d.age), y(d.balances.total)]);
  const linePath = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ');
  svg.appendChild(el('path', { d: `${linePath} L${pts.at(-1)[0].toFixed(1)},${y(0)} L${pts[0][0].toFixed(1)},${y(0)} Z`, class: 'viz-area' }));
  svg.appendChild(el('path', { d: linePath, class: 'viz-line' }));

  // 고갈 시점 표시
  if (opts.depletionAge != null) {
    const dx = x(opts.depletionAge);
    svg.appendChild(el('line', { x1: dx, x2: dx, y1: M.top, y2: y(0), class: 'viz-marker-line' }));
    const anchor = dx > M.left + iw * 0.7 ? 'end' : 'start';
    svg.appendChild(el('text', {
      x: dx + (anchor === 'end' ? -6 : 6), y: M.top + 12, class: 'viz-marker-label', 'text-anchor': anchor,
    }, `${opts.depletionAge}세 고갈`));
  }

  const focus = el('g', { class: 'viz-focus', opacity: 0 });
  focus.appendChild(el('line', { class: 'viz-crosshair', y1: M.top, y2: M.top + ih }));
  focus.appendChild(el('circle', { r: 5, class: 'viz-dot' }));
  svg.appendChild(focus);

  const hit = el('rect', { x: M.left, y: M.top, width: iw, height: ih, fill: 'transparent', class: 'viz-hit' });
  svg.appendChild(hit);
  container.appendChild(svg);

  const onMove = (evt) => {
    const rect = svg.getBoundingClientRect();
    const px = ((evt.clientX - rect.left) / rect.width) * W;
    const age = Math.round(ages[0] + ((px - M.left) / iw) * (ages.at(-1) - ages[0]));
    const d = timeline.find((r) => r.age === age) || timeline[0];
    focus.setAttribute('opacity', 1);
    focus.querySelector('line').setAttribute('x1', x(d.age));
    focus.querySelector('line').setAttribute('x2', x(d.age));
    focus.querySelector('circle').setAttribute('cx', x(d.age));
    focus.querySelector('circle').setAttribute('cy', y(d.balances.total));
    tip.hidden = false;
    tip.innerHTML = `<b>${d.age}세</b><dl>
      <div><dt>잔여 자산</dt><dd>${wonFull(d.balances.total)}</dd></div>
      <div><dt>퇴직연금</dt><dd>${money(d.balances.severance)}</dd></div>
      <div><dt>개인연금</dt><dd>${money(d.balances.personal)}</dd></div>
      <div><dt>기타자산</dt><dd>${money(d.balances.other)}</dd></div></dl>`;
    const cw = container.clientWidth;
    placeTip(container, tip, (x(d.age) / W) * cw, (y(d.balances.total) / H) * container.clientHeight);
  };
  svg.addEventListener('pointermove', onMove);
  svg.addEventListener('pointerleave', () => { focus.setAttribute('opacity', 0); tip.hidden = true; });
}

/* ── 2) 연도별 소득원 구성 (누적 막대) ─────────────────────── */
export function renderIncomeStack(container, timeline) {
  container.innerHTML = '';
  const tip = ensureTooltip(container);

  const W = 720, H = 300;
  const M = { top: 16, right: 16, bottom: 34, left: 56 };
  const iw = W - M.left - M.right;
  const ih = H - M.top - M.bottom;

  const series = SERIES.filter((s) => timeline.some((d) => d[s.key] > 0));
  const stackKeys = [...series, SHORTFALL];

  const totals = timeline.map((d) => stackKeys.reduce((s, k) => s + Math.max(0, d[k.key]), 0));
  const maxY = niceCeil(Math.max(1, ...totals));

  const svg = el('svg', {
    viewBox: `0 0 ${W} ${H}`, class: 'viz-svg', role: 'img',
    'aria-label': '연도별 연금 소득원 구성',
  });

  const bandW = iw / timeline.length;
  const barW = Math.max(3, bandW - 3);
  const y = (v) => M.top + ih - (v / maxY) * ih;

  for (let i = 0; i <= 4; i++) {
    const v = (maxY / 4) * i;
    svg.appendChild(el('line', { x1: M.left, x2: M.left + iw, y1: y(v), y2: y(v), class: 'viz-grid' }));
    svg.appendChild(el('text', { x: M.left - 8, y: y(v) + 4, class: 'viz-axis-label', 'text-anchor': 'end' }, money(v)));
  }

  timeline.forEach((d, i) => {
    const bx = M.left + i * bandW + (bandW - barW) / 2;
    let acc = 0;
    const g = el('g', { class: 'viz-bar-group', tabindex: 0 });
    for (const k of stackKeys) {
      const v = Math.max(0, d[k.key]);
      if (v <= 0) continue;
      const h = (v / maxY) * ih;
      // 세그먼트 사이 2px 표면 간격 — 색 대비가 아니라 '틈'이 경계를 만든다
      const drawH = Math.max(1, h - 2);
      g.appendChild(el('rect', {
        x: bx, y: y(acc + v), width: barW, height: drawH, rx: 1.5,
        fill: `var(${k.varName})`,
      }));
      acc += v;
    }
    g.addEventListener('pointerenter', (evt) => {
      tip.hidden = false;
      const rows = stackKeys.filter((k) => d[k.key] > 0)
        .map((k) => `<div><dt><i style="background:var(${k.varName})"></i>${k.label}</dt><dd>${money(d[k.key] / 12)}/월</dd></div>`).join('');
      tip.innerHTML = `<b>${d.age}세</b><dl>${rows}
        <div class="viz-tip-total"><dt>합계</dt><dd>${money(d.netIncome / 12)}/월</dd></div></dl>`;
      const rect = svg.getBoundingClientRect();
      placeTip(container, tip, evt.clientX - rect.left, evt.clientY - rect.top);
    });
    g.addEventListener('pointerleave', () => { tip.hidden = true; });
    svg.appendChild(g);
  });

  for (const d of timeline) {
    if (d.age % 5 !== 0 && d.age !== timeline[0].age && d.age !== timeline.at(-1).age) continue;
    const i = timeline.indexOf(d);
    svg.appendChild(el('text', {
      x: M.left + i * bandW + bandW / 2, y: M.top + ih + 22, class: 'viz-axis-label', 'text-anchor': 'middle',
    }, `${d.age}`));
  }
  svg.appendChild(el('line', { x1: M.left, x2: M.left + iw, y1: y(0), y2: y(0), class: 'viz-baseline' }));

  container.appendChild(svg);
  container.appendChild(buildLegend(stackKeys, timeline));
}

function buildLegend(keys, timeline) {
  const wrap = document.createElement('ul');
  wrap.className = 'viz-legend';
  for (const k of keys) {
    if (timeline && !timeline.some((d) => d[k.key] > 0)) continue;
    const li = document.createElement('li');
    li.innerHTML = `<i style="background:var(${k.varName})"></i>${k.label}`;
    wrap.appendChild(li);
  }
  return wrap;
}

/* ── 3) 은퇴 시점 재원 구성 (100% 가로 막대 + 직접 라벨) ──── */
export function renderCompositionBar(container, segments) {
  container.innerHTML = '';
  const total = segments.reduce((s, d) => s + d.value, 0);
  if (total <= 0) {
    container.innerHTML = '<p class="viz-empty">구성할 재원이 없습니다.</p>';
    return;
  }
  const bar = document.createElement('div');
  bar.className = 'viz-compbar';
  for (const s of segments) {
    if (s.value <= 0) continue;
    const seg = document.createElement('span');
    seg.style.flexGrow = String(s.value);
    seg.style.background = `var(${s.varName})`;
    seg.title = `${s.label} ${money(s.value)}`;
    bar.appendChild(seg);
  }
  container.appendChild(bar);

  // 대비 경고(라이트 모드의 aqua/yellow)에 대한 완화책: 값을 항상 글자로 보여준다
  const list = document.createElement('ul');
  list.className = 'viz-comp-list';
  for (const s of segments) {
    if (s.value <= 0) continue;
    const li = document.createElement('li');
    li.innerHTML = `<i style="background:var(${s.varName})"></i>
      <span class="viz-comp-label">${s.label}</span>
      <span class="viz-comp-value">${money(s.value)}<em>${((s.value / total) * 100).toFixed(0)}%</em></span>`;
    list.appendChild(li);
  }
  container.appendChild(list);
}

/* ── 4) 종합점수 (히어로 숫자 + 가는 미터) ────────────────── */
export function renderScoreMeter(container, score, grade) {
  container.innerHTML = `
    <div class="score-hero">
      <div class="score-value"><b>${score}</b><span>/100</span></div>
      <div class="score-grade tone-${grade.tone}">${grade.grade} · ${grade.label}</div>
    </div>
    <div class="score-meter" role="img" aria-label="종합 점수 ${score}점 (100점 만점)">
      <div class="score-meter-fill tone-${grade.tone}" style="width:${Math.max(2, score)}%"></div>
    </div>
    <ol class="score-scale" aria-hidden="true">
      <li>위험</li><li>취약</li><li>주의</li><li>양호</li><li>안정</li>
    </ol>`;
}

/* ── 5) 표 보기 (색에 의존하지 않는 대체 경로) ────────────── */
export function renderTable(container, timeline) {
  const cols = [...SERIES, SHORTFALL];
  const head = `<tr><th scope="col">나이</th>${cols.map((c) => `<th scope="col">${c.label}</th>`).join('')}<th scope="col">잔여 자산</th></tr>`;
  const rows = timeline.map((d) => `<tr><th scope="row">${d.age}</th>${
    cols.map((c) => `<td>${d[c.key] > 0 ? money(d[c.key] / 12) : '—'}</td>`).join('')
  }<td>${money(d.balances.total)}</td></tr>`).join('');
  container.innerHTML = `<table class="viz-table"><caption>연도별 소득원과 잔여 자산 — 소득원은 세후 월 금액, 잔여 자산은 연말 잔액, 모두 오늘의 화폐가치 기준</caption><thead>${head}</thead><tbody>${rows}</tbody></table>`;
}
