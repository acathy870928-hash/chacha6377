/*
 * Browser tests for the HTML -> Markdown direction and the page wiring.
 * Requires playwright: `npm install` then `node tests/browser.test.js`.
 */
'use strict';

const path = require('path');
const assert = require('assert');

let chromium;
try {
  ({ chromium } = require('playwright'));
} catch (error) {
  console.log('playwright 미설치 — 브라우저 테스트를 건너뜁니다 (npm install 후 실행하세요)');
  process.exit(0);
}

const PAGE_URL = 'file://' + path.join(__dirname, '..', 'index.html');

let passed = 0;
const failures = [];

async function test(name, fn) {
  try {
    await fn();
    passed++;
  } catch (error) {
    failures.push({ name, error });
  }
}

(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || undefined
  });
  const page = await browser.newPage();
  const pageErrors = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));
  await page.goto(PAGE_URL);

  const toMarkdown = (html) =>
    page.evaluate((input) => HtmlToMarkdown.htmlToMarkdown(input), html);

  await test('제목과 문단', async () => {
    assert.strictEqual(await toMarkdown('<h1>제목</h1><p>본문</p>'), '# 제목\n\n본문\n');
  });

  await test('강조', async () => {
    assert.strictEqual(
      await toMarkdown('<p><strong>굵게</strong> <em>기울임</em> <del>취소</del></p>'),
      '**굵게** *기울임* ~~취소~~\n'
    );
  });

  await test('링크와 이미지', async () => {
    assert.strictEqual(await toMarkdown('<p><a href="https://a.com">링크</a></p>'), '[링크](https://a.com)\n');
    assert.strictEqual(await toMarkdown('<p><img src="/a.png" alt="로고"></p>'), '![로고](/a.png)\n');
  });

  await test('코드', async () => {
    assert.strictEqual(await toMarkdown('<p><code>x = 1</code></p>'), '`x = 1`\n');
    assert.strictEqual(
      await toMarkdown('<pre><code class="language-js">const a = 1;\nconst b = 2;</code></pre>'),
      '```js\nconst a = 1;\nconst b = 2;\n```\n'
    );
  });

  await test('목록', async () => {
    assert.strictEqual(await toMarkdown('<ul><li>a</li><li>b</li></ul>'), '- a\n- b\n');
    assert.strictEqual(await toMarkdown('<ol><li>a</li><li>b</li></ol>'), '1. a\n2. b\n');
    assert.strictEqual(
      await toMarkdown('<ul><li>a<ul><li>b</li></ul></li></ul>'),
      '- a\n  - b\n'
    );
  });

  await test('인용구와 수평선', async () => {
    assert.strictEqual(await toMarkdown('<blockquote><p>인용</p></blockquote>'), '> 인용\n');
    assert.strictEqual(await toMarkdown('<p>a</p><hr><p>b</p>'), 'a\n\n---\n\nb\n');
  });

  await test('표', async () => {
    assert.strictEqual(
      await toMarkdown('<table><tr><th>a</th><th>b</th></tr><tr><td>1</td><td>2</td></tr></table>'),
      '| a | b |\n| --- | --- |\n| 1 | 2 |\n'
    );
  });

  await test('script/style 은 제거된다', async () => {
    assert.strictEqual(await toMarkdown('<p>본문</p><script>alert(1)</script>'), '본문\n');
  });

  await test('마크다운 특수문자는 이스케이프된다', async () => {
    assert.strictEqual(await toMarkdown('<p>a * b _ c</p>'), 'a \\* b \\_ c\n');
  });

  await test('왕복 변환이 내용을 보존한다', async () => {
    const source = '# 제목\n\n**굵게** 그리고 [링크](https://a.com)\n\n- 하나\n- 둘\n';
    const roundTrip = await page.evaluate((md) => {
      const html = MarkdownConverter.markdownToHtml(md, {});
      return HtmlToMarkdown.htmlToMarkdown(html);
    }, source);
    assert.strictEqual(roundTrip, source);
  });

  await test('페이지가 마크다운을 렌더링한다', async () => {
    await page.fill('#source', '# 안녕\n\n- 하나');
    await page.waitForFunction(() => {
      var heading = document.querySelector('#preview h1');
      return heading && heading.textContent === '안녕';
    });
    assert.strictEqual(await page.textContent('#preview h1'), '안녕');
    assert.strictEqual(await page.textContent('#preview li'), '하나');
  });

  await test('모드를 바꾸면 HTML을 마크다운으로 변환한다', async () => {
    await page.click('.mode-btn[data-mode="html2md"]');
    await page.fill('#source', '<h2>제목</h2><p><b>굵게</b></p>');
    await page.click('.tab[data-view="code"]');
    await page.waitForFunction(() => document.querySelector('#code-output code').textContent.includes('##'));
    const output = await page.textContent('#code-output code');
    assert.strictEqual(output.trim(), '## 제목\n\n**굵게**');
  });

  await test('콘솔 오류가 없다', async () => {
    assert.deepStrictEqual(pageErrors, []);
  });

  await browser.close();

  if (failures.length) {
    failures.forEach(({ name, error }) => {
      console.error(`✗ ${name}\n  ${error.message.split('\n').slice(0, 8).join('\n  ')}\n`);
    });
    console.error(`${passed} passed, ${failures.length} failed`);
    process.exit(1);
  }

  console.log(`${passed} passed`);
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
