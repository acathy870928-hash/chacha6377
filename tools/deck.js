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
  s.addText(String(PAGE), { x:12.45, y:7.12, w:0.45, h:0.28, fontFace:F.b, fontSize:10, color:C.mute, align:'right' }); }
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

/* 2 플로우 */ {
  const s = p.addSlide(); s.background={color:C.paper};
  head(s, '플로우', '이렇게 진행됩니다', '10월 1일 버전 기준. 화면 순서대로 보시면 됩니다.');
  const steps = [
    ['①','일반 답변','골절되면 보상되나요?','일반지식으로 먼저 답합니다'],
    ['②','약관 등록하기','보험사 → 상품 → 약관 시점','가입한 상품을 짚어냅니다'],
    ['③','답변','면책 먼저 · 근거 조항','어느 약관인지 함께 표시합니다'],
    ['④','약관북','고객 폴더에 쌓임','그 고객 약관 안에서만 답합니다'],
    ['⑤','약관 등록','하나씩 추가','My Data가 열리면 한 번에'],
  ];
  steps.forEach(([n,t,d,e],i)=>{
    const x = 0.6 + i*2.46, w = 2.2;
    s.addShape(p.ShapeType.roundRect, { x, y:2.05, w, h:2.5, rectRadius:0.1,
      fill:{color:C.white}, line:{color:i===0?C.green:C.line, width:i===0?2:1} });
    s.addShape(p.ShapeType.ellipse, { x:x+0.82, y:2.28, w:0.56, h:0.56, fill:{color:C.green}, line:{color:C.green} });
    s.addText(n, { x:x+0.82, y:2.28, w:0.56, h:0.56, fontFace:F.h, fontSize:17, bold:true, color:C.white, align:'center', valign:'middle' });
    s.addText(t, { x:x+0.16, y:3.02, w:w-0.32, h:0.34, fontFace:F.h, fontSize:14, bold:true, color:C.ink, align:'center' });
    s.addText(d, { x:x+0.16, y:3.4, w:w-0.32, h:0.52, fontFace:F.b, fontSize:10.5, color:C.deep, align:'center', lineSpacing:15 });
    s.addText(e, { x:x+0.16, y:3.94, w:w-0.32, h:0.5, fontFace:F.b, fontSize:10, color:C.mute, align:'center', lineSpacing:14 });
    if (i<4) s.addText('▶', { x:x+w+0.02, y:3.15, w:0.24, h:0.3, fontFace:F.b, fontSize:13, color:C.mute, align:'center' });
  });
  card(s, { x:0.6, y:4.86, w:12.1, h:0.92, fill:C.soft, stroke:'CFE9DB' });
  s.addText([
    { text:'①에서 「이 답변으로 충분해요」로 끝낼 수 있습니다. ', options:{bold:true, color:C.deep} },
    { text:'대부분의 상담은 한 건 확인하고 끝납니다.\n더 정확히 봐야 할 때만 「약관 등록하기」로 ②에 들어갑니다 — ', options:{color:C.body} },
    { text:'고객을 만들지 않아도 됩니다.', options:{bold:true, color:C.ink} },
  ], { x:0.9, y:4.98, w:11.5, h:0.7, fontFace:F.b, fontSize:11.5, lineSpacing:17 });

  s.addShape(p.ShapeType.roundRect, { x:0.6, y:5.96, w:12.1, h:1.02, rectRadius:0.09, fill:{color:C.dark}, line:{color:C.dark} });
  s.addText('10/1 버전입니다', { x:0.95, y:6.08, w:3.2, h:0.34, fontFace:F.h, fontSize:14, bold:true, color:'8FE3BE' });
  s.addText('다음 버전에서는 My Data가 붙어 계약이 한 번에 들어오고, 보장분석이 결합되면 「얼마 나와요?」까지 답합니다. 지금 구조를 바꾸지 않고 얹는 방식입니다.',
    { x:4.3, y:6.08, w:8.1, h:0.82, fontFace:F.b, fontSize:11.5, color:'B9C7C1', lineSpacing:17 });
  foot(s);
}

/* 화면 슬라이드 */
// 화면 한 장이 길면 여러 슬라이드로 나눈다. UI가 주인공이므로 폭을 다 쓴다.
function screen(eyebrow, title, sub, shot, notes) {
  const parts = [];
  for (let k = 1; ; k++) {
    if (!fs.existsSync(path.join(HERE, `app_${shot}_p${k}.png`))) break;
    parts.push(`${shot}_p${k}`);
  }
  parts.forEach((name, k) => {
    const s = p.addSlide(); s.background={color:C.paper};
    const label = eyebrow + (parts.length > 1 ? `  ·  ${k+1}/${parts.length}` : '');
    s.addText(label, { x:0.5, y:0.24, w:8.6, h:0.22, fontFace:F.b, fontSize:10.5, color:C.deep, bold:true, charSpacing:1.8 });
    s.addText(k === 0 ? title : title, { x:0.5, y:0.46, w:9.4, h:0.4, fontFace:F.h, fontSize:20, bold:true, color:C.ink });
    if (k === 0) s.addText(sub, { x:0.5, y:0.88, w:12.3, h:0.28, fontFace:F.b, fontSize:11.5, color:C.mute });
    // UI 전면 — 폭 12.3인치
    fit(s, name, { x:0.5, y:k === 0 ? 1.2 : 0.98, w:12.3, h:k === 0 ? 5.36 : 5.58 });
    // 설명은 이 장에 해당하는 것만 한 줄로
    const mine = notes.filter((_, idx) => idx % parts.length === k);
    mine.forEach((t, idx) => {
      const y = 6.62 + idx*0.0;
      s.addShape(p.ShapeType.roundRect, { x:0.5, y:6.6, w:0.06, h:0.5, rectRadius:0.03, fill:{color:C.green}, line:{color:C.green} });
      s.addText(t, { x:0.72, y:6.6, w:11.6, h:0.5, fontFace:F.b, fontSize:11.5, color:C.body, valign:'middle' });
    });
    foot(s);
  });
}

screen('화면 ① 일반 답변', '먼저 일반으로 답하고, 개인화는 고르게 합니다',
  '「골절되면 보상되나요?」는 일반지식만으로 답이 나옵니다. 여기서 「이 답변으로 충분해요」로 끝내거나 「약관 등록하기」로 넘어갑니다.', 'branch',
  ['걸릴 수 있는 담보를 넓게 열거합니다 — 좁게 잡으면 청구를 놓칩니다.',
   '「이 답변으로 충분해요」를 같은 무게로 둡니다. 일반 답변은 실패가 아닙니다.']);

screen('화면 ② 약관 짚어내기', '대화하면서 정확한 상품을 짚어냅니다',
  '별도 화면으로 빠지지 않습니다. 챗봇이므로 AI가 묻고 FA가 고르는 것이 곧 대화입니다.', 'scope',
  ['AI가 보험사를 묻고 칩으로 고릅니다. 고른 값은 사용자 말풍선으로 남습니다.',
   '보종은 묻지 않습니다. 상품명을 치면 매칭되고, 겹치는 상품을 나란히 놓습니다.',
   '「보상은 가입 시점의 약관을 따릅니다」 — 왜 묻는지를 함께 말합니다.']);

screen('화면 ③ 답변', '면책을 먼저 판정하고 조항으로 근거를 답니다',
  '고객을 만들지 않고 그냥 묻는 경로입니다. 대부분의 상담이 여기서 끝납니다.', 'ask',
  ['확정 전에는 되물어 좁힙니다 — 보험사 → 상품 → 가입 시점.',
   '면책을 맨 위에 놓고 조항 위치까지 답니다. 어느 약관인지 하단에 항상 표시합니다.']);

screen('화면 ④ 약관북', '고객 폴더를 열면 질문 범위가 그 고객으로 잠깁니다',
  '이 화면이 차별점의 실체입니다. 상담할수록 고객별 약관이 쌓입니다.', 'entry',
  ['그 고객 약관 안에서만 찾습니다. 담보가 여러 계약에 걸치면 모두 보여줍니다.']);

screen('화면 ⑤ 약관 등록', '지금은 하나씩. My Data가 열리면 한 번에 들어옵니다',
  '안 열린 경로도 화면에 두되 잠급니다 — 곧 열릴 길이 있다는 사실 자체가 안내입니다.', 'register',
  ['「최근 등록한 상품」은 뺐습니다 — 다른 고객 계약을 끌어오게 됩니다.']);

screen('화면 ⑥ 보장맵', '약관이 담보로 펼쳐지되, 가입 여부는 따로입니다',
  '약관은 가입 「가능한」 담보의 목록일 뿐입니다. 기본값은 「확인 필요」입니다.', 'coverage',
  ['「미가입」은 확인된 사실이고 「확인 필요」는 아직 모르는 것입니다.',
   '면책 · 미가입 · 확인 필요 건도 숨기지 않고 사유와 함께 남깁니다.']);

/* 닫는 장 */ {
  const s = p.addSlide(); s.background={color:C.dark};
  s.addText('앞으로', { x:0.9, y:1.4, w:11.5, h:0.36, fontFace:F.b, fontSize:13, bold:true, color:'8FE3BE', charSpacing:2 });
  s.addText('10월 1일은 시작입니다.\n지금 구조 위에 계속 얹습니다.',
    { x:0.9, y:1.9, w:11.5, h:1.7, fontFace:F.h, fontSize:32, bold:true, color:C.white, lineSpacing:46 });
  [['지금 · 10월 1일','약관을 직접 짚어 답합니다','보험사 → 상품 → 약관 시점을 고르고, 그 약관 안에서만 답합니다. 고객 폴더에 쌓입니다.', C.green],
   ['다음 · My Data','고르지 않아도 됩니다','계약이 한 번에 들어와 약관이 자동으로 정해집니다. 클릭이 사라집니다.', '4E8FF0'],
   ['그다음 · 보장분석','「얼마 나와요?」에 답합니다','가입 담보와 금액이 붙어 보장공백 · 비교까지 갑니다.', 'C9A567'],
  ].forEach(([tag,t,d,col],i)=>{
    const x = 0.9 + i*3.95;
    s.addShape(p.ShapeType.line, { x, y:4.3, w:3.6, h:0, line:{color:col, width:2.5} });
    s.addText(tag, { x, y:4.44, w:3.6, h:0.28, fontFace:F.b, fontSize:11, bold:true, color:col, charSpacing:1 });
    s.addText(t, { x, y:4.74, w:3.6, h:0.34, fontFace:F.h, fontSize:14, bold:true, color:C.white });
    s.addText(d, { x, y:5.12, w:3.6, h:1.0, fontFace:F.b, fontSize:11, color:'A9BAB2', lineSpacing:16 });
  });
  s.addText('주식회사 아이에프에이 AX팀 · 화면 속 고객명과 대화는 가상입니다.',
    { x:0.9, y:6.7, w:11.5, h:0.3, fontFace:F.b, fontSize:10, color:'5F7169' });
}

p.writeFile({ fileName:'/home/user/chacha6377/docs/Insurance_AI_상담설계.pptx' }).then(f=>console.log('저장', f));
