const { chromium } = require('playwright-core');
(async () => {
  const b = await chromium.launch({ executablePath:'/opt/pw-browsers/chromium', args:['--no-sandbox'] });
  const pg = await b.newPage({ viewport:{ width:1240, height:920 }, deviceScaleFactor:2 });
  const errs = []; pg.on('pageerror', e => errs.push('ERR ' + e.message));
  await pg.goto('file:///home/user/chacha6377/docs/mockups/insurance-ai-demo.html');
  const click = async t => { const e = pg.locator(`button:has-text("${t}")`).first();
    await e.waitFor({timeout:3000}); await e.click(); await pg.waitForTimeout(160); };

  // A. 용어 질문 → 약관 안 물어봄
  await click('골절진단비가 뭔가요?');
  const branch = await pg.locator('button:has-text("약관 등록하기")').count();
  console.log('A 용어질문 분기 안뜸:', branch === 0 ? 'OK' : '실패');

  // B. 2018.03 약관 → 음주 (구판 문구)
  await pg.fill('#input','음주운전 사고인데 보험금 나오나요?'); await pg.click('#btnSend'); await pg.waitForTimeout(200);
  await click('약관 등록하기'); await click('손해보험'); await pg.waitForTimeout(180);
  await pg.locator('.gcell:has-text("DB손해보험")').first().click(); await pg.waitForTimeout(180);
  await pg.locator('.plist .row:has-text("참좋은동행보험")').first().click(); await pg.waitForTimeout(180);
  await click('2018.03'); await pg.waitForTimeout(200);
  await click('이어서 질문하기'); await pg.waitForTimeout(250);
  const oldTxt = await pg.locator('.verdict').last().innerText();
  console.log('B 구판 문구 반영:', oldTxt.includes('2021년 개정에서 추가') ? 'OK' : '실패');
  console.log('  판 표기:', oldTxt.includes('2018.03') ? 'OK' : '실패');

  // C. 스코프에 없는 질문 → 해당 조항 없음
  await pg.fill('#input','치아 임플란트 보상되나요?'); await pg.click('#btnSend'); await pg.waitForTimeout(250);
  const none = await pg.locator('.verdict').last().innerText();
  console.log('C 해당 조항 없음:', none.includes('해당 조항 없음') ? 'OK' : '실패 → ' + none.slice(0,40));

  // D. 고객 저장 → 폴더 스코프
  await pg.locator('button:has-text("고객 저장")').first().click(); await pg.waitForTimeout(200);
  await pg.fill('#cName','차승희');
  await pg.fill('#cTag','92년생'); await pg.press('#cTag','Enter');
  await pg.fill('#cTag','강남지점'); await pg.press('#cTag','Enter');
  await click('만들기'); await pg.waitForTimeout(250);
  const folder = await pg.locator('.folder').first().innerText();
  console.log('D 폴더 생성:', folder.includes('차승희') && folder.includes('92년생') ? 'OK' : '실패 → ' + folder);
  await pg.locator('.folder').first().click(); await pg.waitForTimeout(250);
  await pg.fill('#input','골절되면 보상되나요?'); await pg.click('#btnSend'); await pg.waitForTimeout(250);
  const cust = await pg.locator('.verdict').last().innerText();
  console.log('E 고객 스코프 답변:', cust.includes('차승희 고객 약관') ? 'OK' : '실패 → ' + cust.slice(-60));
  await pg.screenshot({ path:'d6.png', fullPage:false });
  console.log(errs.length ? errs.join('\n') : '오류 없음');
  await b.close();
})();
