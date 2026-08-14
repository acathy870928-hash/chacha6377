const pptxgen = require('pptxgenjs');
const fs = require('fs'), path = require('path');
const HERE = __dirname;

const C = { ink:'16211C', body:'44524B', mute:'7A867F', line:'E3E9E5',
  green:'14A05A', deep:'0B7C44', soft:'F3FAF6', amber:'9A7420', amberSoft:'FBF5E4',
  red:'A9422F', redSoft:'FBF0ED', blue:'1F6FEB', blueSoft:'EFF4FD',
  paper:'FBFCFB', white:'FFFFFF', dark:'14201B' };
const F = { h:'맑은 고딕', b:'맑은 고딕' };

const p = new pptxgen();
p.layout = 'LAYOUT_WIDE';
p.author = 'iFA AX팀';
p.title = 'Insurance AI 상담 화면 설계';

const img = n => path.join(HERE, `app_${n}.png`);
const dim = n => { const b = fs.readFileSync(img(n)); return { w:b.readUInt32BE(16), h:b.readUInt32BE(20) }; };
function fit(s, n, box) {
  const d = dim(n), r = Math.min(box.w/d.w, box.h/d.h), w = d.w*r, h = d.h*r;
  s.addImage({ path:img(n), x:box.x+(box.w-w)/2, y:box.y+(box.h-h)/2, w, h });
}
let PAGE = 1;
function head(s, eyebrow, title, sub) {
  s.addText(eyebrow, { x:0.6, y:0.36, w:12.1, h:0.24, fontFace:F.b, fontSize:11, color:C.deep, bold:true, charSpacing:2 });
  s.addText(title, { x:0.6, y:0.62, w:12.1, h:0.58, fontFace:F.h, fontSize:27, bold:true, color:C.ink });
  if (sub) s.addText(sub, { x:0.6, y:1.22, w:12.1, h:0.34, fontFace:F.b, fontSize:13, color:C.mute });
}
function foot(s) { PAGE += 1;
  s.addText(String(PAGE), { x:12.45, y:6.95, w:0.45, h:0.3, fontFace:F.b, fontSize:10, color:C.mute, align:'right' }); }
function card(s, o) {
  s.addShape(p.ShapeType.roundRect, { x:o.x, y:o.y, w:o.w, h:o.h, rectRadius:0.09,
    fill:{color:o.fill||C.white}, line:{color:o.stroke||C.line, width:1} });
}

/* 1 표지 */ {
  const s = p.addSlide(); s.background = { color:C.dark };
  s.addShape(p.ShapeType.roundRect, { x:0.9, y:1.85, w:0.6, h:0.6, rectRadius:0.14, fill:{color:C.green}, line:{color:C.green} });
  s.addText('IA', { x:0.9, y:1.85, w:0.6, h:0.6, fontFace:F.h, fontSize:18, bold:true, color:C.white, align:'center', valign:'middle' });
  s.addText('Insurance AI', { x:1.66, y:1.88, w:6, h:0.3, fontFace:F.h, fontSize:16, bold:true, color:C.white });
  s.addText('Better decisions, clearly.', { x:1.66, y:2.17, w:6, h:0.26, fontFace:F.b, fontSize:11.5, color:'9BB0A6' });
  s.addText('FA 보험 상담 AI\n상담 화면 설계', { x:0.9, y:2.9, w:11.5, h:1.8, fontFace:F.h, fontSize:42, bold:true, color:C.white, lineSpacing:50 });
  s.addText('2026년 10월 1일 오픈 · 1차 범위', { x:0.94, y:4.85, w:11.5, h:0.36, fontFace:F.b, fontSize:15.5, color:'8FE3BE' });
  s.addShape(p.ShapeType.line, { x:0.94, y:5.42, w:2.2, h:0, line:{color:C.green, width:3} });
  s.addText('주식회사 아이에프에이 AX팀 · 2026.08.14', { x:0.94, y:5.66, w:11.5, h:0.3, fontFace:F.b, fontSize:12, color:'6E7F77' });
}

/* 2 한 장 요약 */ {
  const s = p.addSlide(); s.background={color:C.paper};
  head(s, '한 장 요약', '10월 1일에 무엇이 열리는가', '7주 안에 만들 수 있는 범위로 잘랐습니다.');
  [['문제','약관은 서로 90%가 닮았다','섞어놓고 찾으면 아무거나 집어옵니다. 검색은 「모르겠다」를 못 해서 틀려도 티가 나지 않습니다.'],
   ['해법','찾기 전에 정확한 상품을 짚어낸다','보험사 → 상품 → 가입 시점으로 약관 1권을 정확히 짚고, 그 안에서만 찾습니다.'],
   ['안전장치','면책이 먼저, 근거는 조항으로','면책을 먼저 판정하고, 어느 약관 몇 조인지를 항상 붙입니다.'],
   ['효용','선배에게 묻던 것을 대체','24시간 · 같은 기준 · 근거 제시. 쓸수록 고객별 약관이 쌓입니다.'],
  ].forEach(([tag,t,d],i)=>{
    const x = 0.6 + i*3.09;
    card(s, { x, y:1.82, w:2.86, h:2.42 });
    s.addText(tag, { x:x+0.24, y:1.98, w:2.4, h:0.22, fontFace:F.b, fontSize:10, bold:true, color:C.deep, charSpacing:1.5 });
    s.addText(t, { x:x+0.24, y:2.26, w:2.4, h:0.5, fontFace:F.h, fontSize:14, bold:true, color:C.ink });
    s.addText(d, { x:x+0.24, y:2.84, w:2.4, h:1.24, fontFace:F.b, fontSize:10.5, color:C.body, lineSpacing:16 });
  });
  [{ y:4.52, label:'1차 · 10월 1일', on:1, items:['약관 스코프 확정','면책 우선 보상 답변','약관북 · 보장맵','미등록 약관 확보 요청'] },
   { y:5.02, label:'2차', on:0, items:['My Data 연동','보장분석 결합','금액 답변 (초개인화)'] },
  ].forEach(r=>{
    s.addText(r.label, { x:0.6, y:r.y, w:1.7, h:0.38, fontFace:F.b, fontSize:10.5, bold:true, color:r.on?C.deep:C.mute, valign:'middle' });
    let cx = 2.35;
    r.items.forEach(t=>{
      const w = 0.42 + t.length*0.145;
      s.addShape(p.ShapeType.roundRect, { x:cx, y:r.y, w, h:0.38, rectRadius:0.19,
        fill:{color:r.on?C.soft:'F2F4F3'}, line:{color:r.on?'CFE9DB':C.line, width:1} });
      s.addText((r.on?'✓  ':'')+t, { x:cx, y:r.y, w, h:0.38, fontFace:F.b, fontSize:10.5,
        bold:!!r.on, color:r.on?C.deep:C.mute, align:'center', valign:'middle' });
      cx += w + 0.14;
    });
  });
  card(s, { x:0.6, y:5.62, w:12.1, h:1.0, fill:C.soft, stroke:'CFE9DB' });
  s.addText([
    { text:'1차에서 금액은 말하지 않습니다. ', options:{bold:true, color:C.deep} },
    { text:'가입 담보와 가입금액이 있어야 하고, 그건 2차입니다.\n', options:{color:C.body} },
    { text:'고객 등록도 필수가 아닙니다. ', options:{bold:true, color:C.deep} },
    { text:'한 건만 확인하고 끝낼 수 있어야 도구가 실제로 쓰입니다.', options:{color:C.body} },
  ], { x:0.9, y:5.74, w:11.5, h:0.78, fontFace:F.b, fontSize:11.5, lineSpacing:17 });
  foot(s);
}

/* 3 문제 */ {
  const s = p.addSlide(); s.background={color:C.paper};
  head(s, '문제', '「약관을 넣어두면 답한다」가 약관에서는 안 됩니다');
  s.addTable([
    ['문서 종류','문서끼리 얼마나 다른가','넣어두면?'].map(t=>({text:t, options:{bold:true, color:C.mute, fill:'EEF2F0', fontSize:11}})),
    ...[['사내 규정 · 매뉴얼','각자 완전히 다름','잘 됨',0],
        ['뉴스 · 리포트','주제가 전부 다름','잘 됨',0],
        ['계약서 (건별)','당사자 · 금액이 다름','대체로 됨',0],
        ['제품 매뉴얼 (모델별)','일부 겹침','주의',1],
        ['보험 약관','서로 80~90% 동일','안 됨',2]].map(([a,b,c,k])=>[
      {text:a, options:{bold:k===2, color:k===2?C.red:C.ink}},
      {text:b, options:{bold:k===2, color:k===2?C.red:C.body}},
      {text:c, options:{bold:true, align:'center', color:k===2?C.red:(k===1?C.amber:C.deep)}}])
  ], { x:0.6, y:1.62, w:7.2, colW:[2.7,2.8,1.7], rowH:0.44, fontFace:F.b, fontSize:11.5,
       border:{type:'solid', color:C.line, pt:1}, valign:'middle' });
  card(s, { x:8.1, y:1.62, w:4.6, h:2.42, fill:C.redSoft, stroke:'F0D5CE' });
  s.addText('검색은 「모르겠다」를 못 합니다', { x:8.36, y:1.82, w:4.1, h:0.4, fontFace:F.h, fontSize:14.5, bold:true, color:C.red });
  s.addText('후보를 점수순으로 내놓게 되어 있어 100권이 다 닮아도 1등은 반드시 나옵니다. 그 1등으로 「상해 9급, 50만원」이라고 자신 있게 답합니다.\n\n틀렸을 때 틀렸다는 신호가 남지 않습니다.',
    { x:8.36, y:2.3, w:4.1, h:1.6, fontFace:F.b, fontSize:11, color:C.body, lineSpacing:17 });
  card(s, { x:0.6, y:4.34, w:12.1, h:1.78 });
  s.addText('사람에게 같은 조건을 주면 사람도 못 합니다', { x:0.9, y:4.54, w:11.5, h:0.36, fontFace:F.h, fontSize:15, bold:true, color:C.ink });
  s.addText('표지를 떼고, 본문에서 상품명을 지우고, 페이지를 찢어 섞은 뒤 「계단에서 굴러 골절됐는데 보장돼요?」라고 물으면 30년 차도 못 맞춥니다.\n능력의 문제가 아니라 조건의 문제입니다 — 조건을 바꾸면 됩니다.',
    { x:0.9, y:4.98, w:11.5, h:0.94, fontFace:F.b, fontSize:12.5, color:C.body, lineSpacing:20 });
  foot(s);
}

/* 4 해법 */ {
  const s = p.addSlide(); s.background={color:C.paper};
  head(s, '해법', '사람이 하던 순서를 그대로 시킵니다', '새로 발명하는 것이 아닙니다.');
  [['1단계','어느 약관인지 확정한다','AI가 추측하지 않습니다. 사용자가 고르거나 계약 정보로 정해집니다.'],
   ['2단계','짚어낸 약관 한 권만 펼친다','그 1권 안에서만 찾습니다. 밖의 조항은 점수가 높아도 버립니다.'],
   ['3단계','정해진 순서로 확인한다','담보 → 지급사유 → 등급 → 금액 → 면책 → 대기기간 → 한도 → 결론. 8칸을 매번 채웁니다.'],
   ['4단계','근거와 함께 답한다','「제5조 제2항에 따라 …」 못 찾은 항목은 「해당 조항 없음」으로 밝힙니다.'],
  ].forEach(([n,t,d],i)=>{
    const y = 1.86 + i*1.18;
    card(s, { x:0.6, y, w:12.1, h:1.02 });
    s.addShape(p.ShapeType.roundRect, { x:0.6, y, w:0.08, h:1.02, rectRadius:0.03, fill:{color:C.green}, line:{color:C.green} });
    s.addText(n, { x:0.96, y:y+0.16, w:1.05, h:0.3, fontFace:F.b, fontSize:11.5, bold:true, color:C.deep, charSpacing:1 });
    s.addText(t, { x:2.06, y:y+0.13, w:4.4, h:0.36, fontFace:F.h, fontSize:15, bold:true, color:C.ink });
    s.addText(d, { x:2.06, y:y+0.53, w:10.3, h:0.36, fontFace:F.b, fontSize:11.5, color:C.body });
  });
  s.addText('네 단계가 각각 요구사항 IA-FUN-001 · IA-AI-002 · IA-FUN-004 · IA-AI-001에 대응합니다.',
    { x:0.6, y:6.68, w:12.1, h:0.3, fontFace:F.b, fontSize:11, color:C.mute });
  foot(s);
}

/* 5 차별점 */ {
  const s = p.addSlide(); s.background={color:C.paper};
  head(s, '차별점', '약관을 검색하는 도구가 아니라, 고객의 보장을 아는 도구입니다',
    '약관을 물어보면 답하는 AI는 이미 있습니다. 우리가 다른 지점은 「단위」입니다.');
  const rows = [
    ['묻는 단위', '약관 한 건', '고객 한 명'],
    ['질문 형태', '「이 약관에 음주 면책 있나요」', '「차승희 고객, 골절되면 어디서 나와요」'],
    ['찾는 범위', '물어본 약관 1건', '그 고객이 가입한 계약 전부'],
    ['다시 물을 때', '약관을 매번 다시 특정', '폴더를 열면 끝 — 쌓일수록 빨라짐'],
    ['놓치는 것', '다른 계약에 있는 같은 담보', '여러 계약에 걸친 담보를 함께 제시'],
  ];
  s.addShape(p.ShapeType.roundRect, { x:4.55, y:1.78, w:3.9, h:0.46, rectRadius:0.07, fill:{color:'F2F4F3'}, line:{color:C.line} });
  s.addText('기존 약관 Q&A AI', { x:4.55, y:1.78, w:3.9, h:0.46, fontFace:F.b, fontSize:12, bold:true, color:C.mute, align:'center', valign:'middle' });
  s.addShape(p.ShapeType.roundRect, { x:8.6, y:1.78, w:4.1, h:0.46, rectRadius:0.07, fill:{color:C.green}, line:{color:C.green} });
  s.addText('Insurance AI', { x:8.6, y:1.78, w:4.1, h:0.46, fontFace:F.b, fontSize:12, bold:true, color:C.white, align:'center', valign:'middle' });
  rows.forEach(([k,a,b],i)=>{
    const y = 2.34 + i*0.72;
    s.addText(k, { x:0.6, y, w:3.8, h:0.6, fontFace:F.b, fontSize:11.5, color:C.mute, align:'right', valign:'middle' });
    card(s, { x:4.55, y, w:3.9, h:0.6, fill:'F8F9F8' });
    s.addText(a, { x:4.75, y, w:3.5, h:0.6, fontFace:F.b, fontSize:11.5, color:C.body, valign:'middle' });
    card(s, { x:8.6, y, w:4.1, h:0.6, fill:C.soft, stroke:'CFE9DB' });
    s.addText(b, { x:8.8, y, w:3.7, h:0.6, fontFace:F.b, fontSize:11.5, bold:true, color:C.deep, valign:'middle' });
  });
  s.addShape(p.ShapeType.roundRect, { x:0.6, y:6.06, w:12.1, h:0.74, rectRadius:0.09, fill:{color:C.dark}, line:{color:C.dark} });
  s.addText('고객별로 약관을 넣어두면, 그 고객의 정확한 보장을 언제든 물어볼 수 있습니다.',
    { x:0.6, y:6.06, w:12.1, h:0.74, fontFace:F.h, fontSize:13.5, bold:true, color:C.white, align:'center', valign:'middle' });
  foot(s);
}

/* 6 확장 구조 */ {
  const s = p.addSlide(); s.background={color:C.paper};
  head(s, '확장 구조', '스코프를 좁히는 수단을 단계적으로 늘려갑니다', '한 번에 다 만들지 않습니다. 각 단계는 그 자체로 쓸모가 있습니다.');
  [['STEP 1','설계사 직접 선택','보험사 → 상품 검색 → 가입 시점','약관 1권 확정','조항 조회 · 면책 확인','2~3번',C.deep,C.soft,'CFE9DB','1차 · 10/1'],
   ['STEP 2','고객 My Data 연동','증권 · 상품코드 · 계약일자 자동 조회','약관이 자동 확정','「내 보험」 기준 답변','0회',C.blue,C.blueSoft,'CFDCF5','2차'],
   ['STEP 3','보장분석 결합','담보 · 특약 단위 보장 데이터','가입 담보 · 보장금액','보장공백 · 비교 · 즉답','—',C.amber,C.amberSoft,'EADFC4','2차'],
  ].forEach(([tag,t,sub,got,can,cost,col,fill,stroke,when],i)=>{
    const x = 0.6 + i*4.13, w = 3.84;
    s.addShape(p.ShapeType.roundRect, { x, y:1.9, w, h:0.5, rectRadius:0.08, fill:{color:col}, line:{color:col} });
    s.addText(tag, { x, y:1.9, w:w-1.2, h:0.5, fontFace:F.b, fontSize:12, bold:true, color:C.white, align:'center', valign:'middle', charSpacing:1.5 });
    s.addShape(p.ShapeType.roundRect, { x:x+w-1.3, y:2.01, w:1.14, h:0.28, rectRadius:0.14, fill:{color:C.white}, line:{color:C.white} });
    s.addText(when, { x:x+w-1.3, y:2.01, w:1.14, h:0.28, fontFace:F.b, fontSize:9, bold:true, color:col, align:'center', valign:'middle' });
    card(s, { x, y:2.4, w, h:2.5, fill, stroke });
    s.addText(t, { x:x+0.26, y:2.58, w:w-0.52, h:0.34, fontFace:F.h, fontSize:16, bold:true, color:col });
    s.addText(sub, { x:x+0.26, y:2.94, w:w-0.52, h:0.5, fontFace:F.b, fontSize:11, color:C.body, lineSpacing:16 });
    s.addShape(p.ShapeType.line, { x:x+0.26, y:3.5, w:w-0.52, h:0, line:{color:stroke, width:1} });
    [['확보',got],['가능해지는 것',can],['클릭',cost]].forEach(([k,v],j)=>{
      s.addText(k, { x:x+0.26, y:3.64+j*0.42, w:1.2, h:0.3, fontFace:F.b, fontSize:9.5, color:C.mute });
      s.addText(v, { x:x+1.46, y:3.64+j*0.42, w:w-1.72, h:0.3, fontFace:F.b, fontSize:10.5, bold:true, color:C.ink });
    });
    if (i<2) s.addText('▶', { x:x+w+0.03, y:3.45, w:0.24, h:0.3, fontFace:F.b, fontSize:12, color:C.mute, align:'center' });
  });
  card(s, { x:0.6, y:5.08, w:12.1, h:1.0, fill:C.blueSoft, stroke:'CFDCF5' });
  s.addText([
    { text:'STEP 3에 오면 질문의 상당수가 약관 검색을 아예 타지 않습니다. ', options:{bold:true, color:C.blue} },
    { text:'「얼마 나와요?」는 보장 데이터로 즉답되고, 약관은 「왜 그런가 · 면책은 없나」를 볼 때만 펼칩니다.\n어려운 문제를 푸는 대신 — ', options:{color:C.body} },
    { text:'애초에 그 문제를 만나는 횟수를 줄이는 구조', options:{bold:true, color:C.ink} },
    { text:'입니다.', options:{color:C.body} },
  ], { x:0.9, y:5.2, w:11.5, h:0.78, fontFace:F.b, fontSize:11.5, lineSpacing:17 });
  s.addShape(p.ShapeType.roundRect, { x:0.6, y:6.24, w:12.1, h:0.56, rectRadius:0.08, fill:{color:C.dark}, line:{color:C.dark} });
  s.addText('STEP 1만 해도 지금보다 낫고, 뒤 단계가 늦어져도 서비스는 그대로 돕니다.',
    { x:0.6, y:6.24, w:12.1, h:0.56, fontFace:F.h, fontSize:13, bold:true, color:C.white, align:'center', valign:'middle' });
  foot(s);
}

/* 화면 슬라이드 */
function screen(eyebrow, title, sub, shot, notes) {
  const s = p.addSlide(); s.background={color:C.paper};
  // 왼쪽에 설명을 몰고 오른쪽을 화면에 전부 내준다 — 슬라이드에서 UI가 읽혀야 한다
  s.addText(eyebrow, { x:0.55, y:0.42, w:3.5, h:0.24, fontFace:F.b, fontSize:10.5, color:C.deep, bold:true, charSpacing:1.8 });
  s.addText(title, { x:0.55, y:0.68, w:3.6, h:1.1, fontFace:F.h, fontSize:21, bold:true, color:C.ink, lineSpacing:28 });
  s.addText(sub, { x:0.55, y:1.86, w:3.6, h:0.9, fontFace:F.b, fontSize:11.5, color:C.mute, lineSpacing:17 });
  notes.forEach(([t,d],i)=>{
    const y = 2.94 + i*1.28;
    s.addShape(p.ShapeType.roundRect, { x:0.55, y, w:0.07, h:1.06, rectRadius:0.03, fill:{color:C.green}, line:{color:C.green} });
    s.addText(t, { x:0.82, y:y+0.02, w:3.3, h:0.32, fontFace:F.h, fontSize:12, bold:true, color:C.ink });
    s.addText(d, { x:0.82, y:y+0.34, w:3.3, h:0.68, fontFace:F.b, fontSize:10, color:C.body, lineSpacing:15 });
  });
  fit(s, shot + '_main', { x:4.45, y:0.42, w:8.45, h:6.62 });
  foot(s);
}

screen('화면 ① 일반 답변', '먼저 일반으로 답하고, 개인화는 고르게 합니다',
  '「골절되면 보상되나요?」는 일반지식만으로 답이 나옵니다. 그 답으로 충분한 경우가 많습니다.', 'branch',
  [['일반 답변은 실패가 아니다','「이 답변으로 충분해요」를 같은 무게로 둡니다.'],
   ['입구는 약관이지 고객이 아니다','상품을 고르면 그 약관 기준으로 답이 바뀝니다.'],
   ['여기서 금액은 말하지 않는다','담보 · 지급 조건 · 면책은 상품과 판마다 다릅니다.']]);

screen('화면 ② 약관 스코프 확정', '찾기 전에 정확한 상품을 짚어냅니다',
  '보험사는 치거나 눌러 고르고, 상품은 검색으로 매칭합니다. 판까지 정해져야 검색이 열립니다.', 'scope',
  [['보종은 묻지 않는다','상품명을 이미 알고 있으니 검색이 더 빠릅니다.'],
   ['겹치는 상품을 함께 본다','「참좋은동행」과 「동행Ⅱ」는 다른 약관입니다.'],
   ['실손은 판이 아니라 세대로','1~4세대가 보상 갈래를 정합니다. 판 150개가 필요 없습니다.']]);

screen('화면 ③ 답변', '면책을 먼저 판정하고 조항으로 근거를 답니다',
  '고객을 만들지 않고 그냥 묻는 경로입니다. 대부분의 상담이 여기서 끝납니다.', 'ask',
  [['면책이 먼저다','지급사유를 먼저 보이면 아래 면책은 읽히지 않습니다.'],
   ['근거를 조항으로 제시한다','제5조 1항 6호까지 짚어야 고객에게 읽어줄 수 있습니다.'],
   ['어느 약관인지 항상 보인다','안 보이면 틀려도 알아챌 수 없습니다.']]);

screen('화면 ④ 약관북', '고객 폴더를 열면 질문 범위가 그 고객으로 잠깁니다',
  '이 화면이 차별점의 실체입니다. 상담할수록 고객별 약관이 쌓입니다.', 'entry',
  [['폴더가 곧 검색 범위다','그 고객 약관 4건 안에서만 찾습니다.'],
   ['청구 누락을 잡는다','담보가 여러 계약에 걸치면 모두 보여줍니다.'],
   ['답할 수 있는 수를 밝힌다','약관이 2건뿐이면 「답할 수 있는 건 2건」이라고 씁니다.']]);

screen('화면 ⑤ 약관 등록', '지금은 하나씩 넣습니다. My Data가 열리면 한 번에 들어옵니다',
  '경로를 빠른 순으로 놓되, 아직 안 열린 것은 두되 잠급니다.', 'register',
  [['안 열린 길도 보여준다','곧 열릴 경로가 있다는 사실 자체가 안내입니다.'],
   ['이미 말한 상품은 다시 안 찾는다','지금 가장 빠른 길입니다.'],
   ['「최근 등록한 상품」은 뺐다','다른 고객 계약을 끌어오게 됩니다.']]);

/* 비용 */ {
  const s = p.addSlide(); s.background={color:C.paper};
  head(s, '비용', '약관은 사야 합니다', '벤더에 등록해야 검색되고, 등록은 유료입니다. 단가는 아직 미확정입니다.');
  card(s, { x:0.6, y:1.78, w:3.9, h:2.3, fill:C.amberSoft, stroke:'EADFC4' });
  s.addText('과금 단위는 약관 파일 수', { x:0.86, y:1.96, w:3.4, h:0.34, fontFace:F.h, fontSize:14, bold:true, color:C.amber });
  s.addText('상품 하나가 파일 하나가 아닙니다. 보장형태 × 납입방법 × 판으로 갈립니다.\n배수가 6이면 200파일에 손보 상품이 4개만 들어갑니다.',
    { x:0.86, y:2.38, w:3.4, h:1.5, fontFace:F.b, fontSize:11, color:C.body, lineSpacing:17 });
  card(s, { x:4.7, y:1.78, w:3.9, h:2.3 });
  s.addText('누가 부담하나', { x:4.96, y:1.96, w:3.4, h:0.34, fontFace:F.h, fontSize:14, bold:true, color:C.ink });
  s.addText('초기 200파일은 회사가 등록하고, 그 밖의 약관은 요청한 FA가 부담합니다.\n단가 미확정이라 지금은 금액을 띄우지 않고 요청 의사만 받습니다.',
    { x:4.96, y:2.38, w:3.4, h:1.5, fontFace:F.b, fontSize:11, color:C.body, lineSpacing:17 });
  card(s, { x:8.8, y:1.78, w:3.9, h:2.3, fill:C.soft, stroke:'CFE9DB' });
  s.addText('무엇을 살 것인가', { x:9.06, y:1.96, w:3.4, h:0.34, fontFace:F.h, fontSize:14, bold:true, color:C.deep });
  s.addText('실적 상위 상품을 사면 「영업용 약관」을 삽니다. 보상 질문은 이미 가입한 계약에서 나옵니다.\n보유 계약을 집계해 실제 조회될 약관부터 사야 합니다.',
    { x:9.06, y:2.38, w:3.4, h:1.5, fontFace:F.b, fontSize:11, color:C.body, lineSpacing:17 });
  card(s, { x:0.6, y:4.3, w:12.1, h:1.5, fill:'F8FAF9' });
  s.addText('실손은 예외입니다 — 파일 대비 효율이 가장 좋습니다', { x:0.9, y:4.48, w:11.5, h:0.34, fontFace:F.h, fontSize:14, bold:true, color:C.deep });
  s.addText('판만 세면 150개가 넘지만, 실손은 1~4세대 표준약관으로 갈리고 보상 판정의 갈래도 세대가 정합니다.\n세대 대표 판만 사도 대부분의 질문을 덮습니다. 다만 갱신 · 전환으로 세대가 바뀌므로 「가입 시점」이 아니라 「지금 적용 중인 세대」를 물어야 합니다.',
    { x:0.9, y:4.86, w:11.5, h:0.84, fontFace:F.b, fontSize:11.5, color:C.body, lineSpacing:19 });
  s.addShape(p.ShapeType.roundRect, { x:0.6, y:6.02, w:12.1, h:0.72, rectRadius:0.09, fill:{color:C.dark}, line:{color:C.dark} });
  s.addText('단가 · 상품당 파일 배수 · 판매종료 상품 색인 가능 여부 — 이 셋이 정해져야 예산 계획이 섭니다.',
    { x:0.6, y:6.02, w:12.1, h:0.72, fontFace:F.h, fontSize:13, bold:true, color:C.white, align:'center', valign:'middle' });
  foot(s);
}

/* 오픈 판정 + 지표 */ {
  const s = p.addSlide(); s.background={color:C.paper};
  head(s, '판정과 지표', '무엇이 안 되면 열지 않고, 무엇으로 성공을 볼 것인가');
  card(s, { x:0.6, y:1.72, w:6.0, h:3.5, fill:C.redSoft, stroke:'F0D5CE' });
  s.addText('열지 못하는 조건', { x:0.88, y:1.9, w:5.4, h:0.32, fontFace:F.h, fontSize:14.5, bold:true, color:C.red });
  s.addText('하나라도 걸리면 연기합니다.', { x:0.88, y:2.22, w:5.4, h:0.24, fontFace:F.b, fontSize:10.5, color:C.mute });
  s.addText([
    '확정된 약관 밖의 조항을 인용한 답변이 나온다',
    '골든셋에서 면책 조항을 놓치는 답변이 나온다',
    '조항이 없는데 그럴듯한 답을 만든다',
    '어느 약관으로 답했는지 화면에 없다',
    '고객을 만들지 않으면 질문을 못 한다',
    '담당하지 않는 고객의 자료가 조회된다',
  ].map((t,i,a)=>({ text:t, options:{ bullet:{code:'2022'}, breakLine:i<a.length-1 } })),
    { x:0.92, y:2.56, w:5.35, h:2.4, fontFace:F.b, fontSize:11.5, color:C.body, lineSpacing:19, paraSpaceAfter:5 });
  card(s, { x:6.8, y:1.72, w:5.9, h:3.5 });
  s.addText('무엇으로 볼 것인가', { x:7.08, y:1.9, w:5.3, h:0.32, fontFace:F.h, fontSize:14.5, bold:true, color:C.ink });
  s.addText('열고 나서 매주 봅니다.', { x:7.08, y:2.22, w:5.3, h:0.24, fontFace:F.b, fontSize:10.5, color:C.mute });
  [['스코프 밖 반환율','벤더 색인 · 필터 품질의 직접 지표. 가장 먼저 봅니다'],
   ['「해당 조항 없음」 비율','색인 누락인지 하한이 과한지 가릅니다'],
   ['미등록 비율','약관 없음으로 끝난 비율 — 등록 예산 증액 근거'],
   ['되묻기 이탈률','되물었는데 답하지 않고 나간 비율 — 과하면 도구가 안 쓰입니다'],
  ].forEach(([k,v],i)=>{
    const y = 2.56 + i*0.62;
    s.addText(k, { x:7.08, y, w:2.5, h:0.5, fontFace:F.b, fontSize:11.5, bold:true, color:C.deep, valign:'middle' });
    s.addText(v, { x:9.62, y, w:2.9, h:0.5, fontFace:F.b, fontSize:10, color:C.body, valign:'middle' });
  });
  s.addShape(p.ShapeType.roundRect, { x:0.6, y:5.42, w:12.1, h:0.66, rectRadius:0.09, fill:{color:C.dark}, line:{color:C.dark} });
  s.addText('통과 기준 — 스코프 밖 인용 0건 · 면책 재현율 100% · 판 일치율 100% · 특약 오귀속 0건 · 1차 금액 언급 0건',
    { x:0.6, y:5.42, w:12.1, h:0.66, fontFace:F.h, fontSize:12.5, bold:true, color:C.white, align:'center', valign:'middle' });
  card(s, { x:0.6, y:6.22, w:12.1, h:0.6, fill:C.soft, stroke:'CFE9DB' });
  s.addText([
    { text:'규정 — ', options:{bold:true, color:C.deep} },
    { text:'AI 기본법(2026.1 시행)에서 금융은 고영향 AI로 거론되지만, 이 서비스는 권리 · 의무를 결정하지 않고 FA를 보조합니다. 금융분야 AI 가이드라인의 「보조수단성」에 맞춰 최종 판단자가 사람임을 화면과 로그에 남깁니다.', options:{color:C.body} },
  ], { x:0.9, y:6.28, w:11.5, h:0.48, fontFace:F.b, fontSize:10.5, valign:'middle' });
  foot(s);
}

/* 남은 확인 */ {
  const s = p.addSlide(); s.background={color:C.paper};
  head(s, '남은 확인', '착수 즉시 확인해야 할 것', '늦게 확인할수록 되돌리기 어렵습니다.');
  [['1','판매 종료 상품 색인 가능 여부','불가하면 보상용 약관을 살 수 없습니다. 기획 전제가 무너집니다','벤더',C.red],
   ['2','상품 · 판 메타데이터 필터 지원','스코프를 확정해도 벤더가 100권을 뒤지게 됩니다','벤더',C.red],
   ['3','약관 파일 단가와 과금 단위','판당 / 용량 / 정액 중 무엇인지에 따라 등록 전략이 달라집니다','벤더',C.amber],
   ['4','상품당 파일 수(배수)','배수 6이면 200파일에 손보 상품이 4개만 들어갑니다','벤더',C.amber],
   ['5','근거 청크 · 유사도 점수 반환','없으면 조항 제시와 하한 차단이 불가능합니다','벤더',C.amber],
   ['6','1차 오픈 종목 확정','운전자 단독 또는 실손 포함 — 실손은 파일 대비 효율이 가장 좋습니다','내부',C.deep],
   ['7','FA 규모 · 알림 채널 · 원본 보관','성능 목표와 개인정보 정책의 전제값입니다','내부',C.deep],
   ['8','보장분석 · My Data 동의 범위','2차 선행 조건입니다. 1차 진행은 막지 않습니다','법무','5A6B61'],
  ].forEach(([n,t,d,who,col],i)=>{
    const y = 1.82 + i*0.62;
    s.addShape(p.ShapeType.roundRect, { x:0.6, y, w:12.1, h:0.54, rectRadius:0.07,
      fill:{color: i%2 ? C.white : 'F6F9F7'}, line:{color:C.line, width:1} });
    s.addText(n, { x:0.78, y, w:0.34, h:0.54, fontFace:F.b, fontSize:12, bold:true, color:col, align:'center', valign:'middle' });
    s.addText(t, { x:1.22, y, w:4.1, h:0.54, fontFace:F.h, fontSize:12, bold:true, color:C.ink, valign:'middle' });
    s.addText(d, { x:5.4, y, w:6.2, h:0.54, fontFace:F.b, fontSize:11, color:C.body, valign:'middle' });
    s.addShape(p.ShapeType.roundRect, { x:11.72, y:y+0.12, w:0.82, h:0.3, rectRadius:0.15, fill:{color:'F2F4F3'}, line:{color:C.line, width:1} });
    s.addText(who, { x:11.72, y:y+0.12, w:0.82, h:0.3, fontFace:F.b, fontSize:9.5, bold:true, color:C.mute, align:'center', valign:'middle' });
  });
  s.addText('1 · 2번은 가격 협상보다 먼저 확인합니다. 부정으로 나오면 계획을 다시 짜야 합니다.',
    { x:0.6, y:6.86, w:12.1, h:0.28, fontFace:F.b, fontSize:11, color:C.mute });
  foot(s);
}

/* 닫는 장 */ {
  const s = p.addSlide(); s.background={color:C.dark};
  s.addText('정리하면', { x:0.9, y:1.45, w:11.5, h:0.36, fontFace:F.b, fontSize:13, bold:true, color:'8FE3BE', charSpacing:2 });
  s.addText('약관은 넣어두면 답하지 않습니다.\n고객별로 넣어두면, 그 고객의 보장을 언제든 답합니다.',
    { x:0.9, y:1.95, w:11.5, h:1.9, fontFace:F.h, fontSize:32, bold:true, color:C.white, lineSpacing:48 });
  [['1차에 여는 것','약관 스코프 확정 · 면책 우선 답변 · 약관북 · 확보 요청'],
   ['1차에 안 여는 것','My Data · 보장분석 · 금액 답변 — 전부 2차'],
   ['성공 기준','선배에게 묻는 것보다 나은가. 근거 조항이 그 답을 만듭니다'],
  ].forEach(([t,d],i)=>{
    const x = 0.9 + i*3.95;
    s.addShape(p.ShapeType.line, { x, y:4.4, w:3.6, h:0, line:{color:C.green, width:2} });
    s.addText(t, { x, y:4.55, w:3.6, h:0.3, fontFace:F.h, fontSize:13, bold:true, color:'8FE3BE' });
    s.addText(d, { x, y:4.9, w:3.6, h:0.9, fontFace:F.b, fontSize:11.5, color:'B9C7C1', lineSpacing:17 });
  });
  s.addText('주식회사 아이에프에이 AX팀 · 화면 속 고객명과 대화는 가상이며 상품명은 시드 데이터 기준입니다.',
    { x:0.9, y:6.6, w:11.5, h:0.3, fontFace:F.b, fontSize:10, color:'5F7169' });
}

p.writeFile({ fileName:'/home/user/chacha6377/docs/Insurance_AI_상담설계.pptx' }).then(f=>console.log('저장', f));
