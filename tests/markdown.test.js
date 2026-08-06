/* Node test runner for the Markdown -> HTML converter: `node tests/markdown.test.js` */
'use strict';

const assert = require('assert');
const { markdownToHtml } = require('../assets/markdown.js');

let passed = 0;
const failures = [];

function test(name, fn) {
  try {
    fn();
    passed++;
  } catch (error) {
    failures.push({ name, error });
  }
}

function equal(actual, expected, message) {
  assert.strictEqual(actual, expected, message);
}

test('헤딩', () => {
  equal(markdownToHtml('# 제목'), '<h1 id="제목">제목</h1>');
  equal(markdownToHtml('### 세 번째 ###'), '<h3 id="세-번째">세 번째</h3>');
  equal(markdownToHtml('제목\n===='), '<h1 id="제목">제목</h1>');
});

test('문단과 인라인 강조', () => {
  equal(markdownToHtml('**굵게** *기울임* ~~취소~~'),
    '<p><strong>굵게</strong> <em>기울임</em> <del>취소</del></p>');
  equal(markdownToHtml('a\nb'), '<p>a\nb</p>');
});

test('인라인 코드는 내부 문법을 해석하지 않는다', () => {
  equal(markdownToHtml('`**raw**`'), '<p><code>**raw**</code></p>');
  equal(markdownToHtml('`a < b & c`'), '<p><code>a &lt; b &amp; c</code></p>');
});

test('HTML 이스케이프', () => {
  equal(markdownToHtml('<script>alert(1)</script>'),
    '<p>&lt;script&gt;alert(1)&lt;/script&gt;</p>');
  equal(markdownToHtml('<b>hi</b>', { allowHtml: true }), '<b>hi</b>');
});

test('링크와 이미지', () => {
  equal(markdownToHtml('[구글](https://google.com)'),
    '<p><a href="https://google.com">구글</a></p>');
  equal(markdownToHtml('![로고](/a.png "제목")'),
    '<p><img src="/a.png" alt="로고" title="제목"></p>');
});

test('링크 URL 안의 밑줄은 기울임으로 처리되지 않는다', () => {
  equal(markdownToHtml('[x](http://a.com/a_b_c)'),
    '<p><a href="http://a.com/a_b_c">x</a></p>');
});

test('javascript: URL 차단', () => {
  equal(markdownToHtml('[x](javascript:alert(1))'), '<p><a href="#">x</a></p>');
});

test('참조 링크', () => {
  equal(markdownToHtml('[예시][ref]\n\n[ref]: https://example.com "제목"'),
    '<p><a href="https://example.com" title="제목">예시</a></p>');
});

test('자동 링크', () => {
  equal(markdownToHtml('<https://example.com>'),
    '<p><a href="https://example.com">https://example.com</a></p>');
});

test('펜스 코드 블록', () => {
  equal(markdownToHtml('```js\nconst a = 1 < 2;\n```'),
    '<pre><code class="language-js">const a = 1 &lt; 2;</code></pre>');
  equal(markdownToHtml('```\nplain\n```'), '<pre><code>plain</code></pre>');
});

test('들여쓰기 코드 블록', () => {
  equal(markdownToHtml('    code()'), '<pre><code>code()</code></pre>');
});

test('목록', () => {
  equal(markdownToHtml('- a\n- b'), '<ul>\n<li>a</li>\n<li>b</li>\n</ul>');
  equal(markdownToHtml('1. a\n2. b'), '<ol>\n<li>a</li>\n<li>b</li>\n</ol>');
  equal(markdownToHtml('3. a'), '<ol start="3">\n<li>a</li>\n</ol>');
});

test('중첩 목록', () => {
  equal(markdownToHtml('- a\n  - b'),
    '<ul>\n<li>a<ul>\n<li>b</li>\n</ul></li>\n</ul>');
});

test('느슨한 목록은 문단을 유지한다', () => {
  equal(markdownToHtml('- a\n\n- b'),
    '<ul>\n<li><p>a</p></li>\n<li><p>b</p></li>\n</ul>');
});

test('체크박스 목록', () => {
  equal(markdownToHtml('- [x] 완료'),
    '<ul>\n<li class="task-list-item"><input type="checkbox" disabled checked> 완료</li>\n</ul>');
});

test('인용구', () => {
  equal(markdownToHtml('> 인용'), '<blockquote>\n<p>인용</p>\n</blockquote>');
});

test('수평선', () => {
  equal(markdownToHtml('---'), '<hr>');
  equal(markdownToHtml('- - -'), '<hr>');
});

test('표와 정렬', () => {
  equal(markdownToHtml('| a | b |\n| --- | ---: |\n| 1 | 2 |'),
    '<table>\n<thead>\n<tr><th>a</th><th style="text-align:right">b</th></tr>\n</thead>\n' +
    '<tbody>\n<tr><td>1</td><td style="text-align:right">2</td></tr>\n</tbody>\n</table>');
});

test('백슬래시 이스케이프', () => {
  equal(markdownToHtml('\\*리터럴\\*'), '<p>*리터럴*</p>');
});

test('하드 줄바꿈', () => {
  equal(markdownToHtml('a  \nb'), '<p>a<br>\nb</p>');
  equal(markdownToHtml('a\nb', { breaks: true }), '<p>a<br>\nb</p>');
});

test('빈 입력', () => {
  equal(markdownToHtml(''), '');
  equal(markdownToHtml(null), '');
});

if (failures.length) {
  failures.forEach(({ name, error }) => {
    console.error(`✗ ${name}\n  ${error.message.split('\n').slice(0, 6).join('\n  ')}\n`);
  });
  console.error(`${passed} passed, ${failures.length} failed`);
  process.exit(1);
}

console.log(`${passed} passed`);
