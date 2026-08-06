/* UI wiring for the converter. Everything runs client-side. */
(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };

  var els = {
    source: $('source'),
    preview: $('preview'),
    codeOutput: $('code-output'),
    codeInner: $('code-output').querySelector('code'),
    inputTitle: $('input-title'),
    inputStats: $('input-stats'),
    outputStats: $('output-stats'),
    status: $('status'),
    fileInput: $('file-input'),
    dropHint: $('drop-hint'),
    optBreaks: $('opt-breaks'),
    optRawHtml: $('opt-raw-html')
  };

  var STORAGE_KEY = 'md-converter:state';

  var state = {
    mode: 'md2html',
    view: 'preview',
    theme: 'light',
    text: '',
    breaks: false,
    allowHtml: false
  };

  var result = '';

  var SAMPLE = [
    '# 마크다운 변환기',
    '',
    '브라우저에서 **바로** 동작하고, 입력한 내용은 *어디에도* 전송되지 않습니다.',
    '',
    '## 지원하는 문법',
    '',
    '- 제목, 문단, 인용구',
    '- 목록 (중첩 가능)',
    '  1. 순서 있는 목록',
    '  2. 두 번째',
    '- [x] 체크박스',
    '- [ ] 아직 안 한 일',
    '',
    '> 인용문도 그대로 변환됩니다.',
    '',
    '| 기능 | 지원 |',
    '| --- | :---: |',
    '| 표 | O |',
    '| 코드 블록 | O |',
    '',
    '```js',
    'function hello(name) {',
    '  return `안녕하세요, ${name}!`;',
    '}',
    '```',
    '',
    '자세한 내용은 [README](https://github.com/acathy870928-hash/chacha6377)를 참고하세요.',
    ''
  ].join('\n');

  /* ---------- persistence ---------- */

  function load() {
    try {
      var saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
      Object.keys(saved).forEach(function (key) {
        if (key in state) state[key] = saved[key];
      });
    } catch (err) { /* 저장된 설정이 손상된 경우 기본값 사용 */ }

    if (!state.text) state.text = SAMPLE;
  }

  function save() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch (err) { /* 용량 초과 등은 무시 */ }
  }

  /* ---------- conversion ---------- */

  function convert() {
    var input = els.source.value;
    state.text = input;

    try {
      if (state.mode === 'md2html') {
        result = MarkdownConverter.markdownToHtml(input, {
          breaks: state.breaks,
          allowHtml: state.allowHtml
        });
        els.preview.innerHTML = result;
      } else {
        result = HtmlToMarkdown.htmlToMarkdown(input);
        els.preview.innerHTML = MarkdownConverter.markdownToHtml(result, {});
      }
      els.codeInner.textContent = result;
      setStatus('');
    } catch (err) {
      result = '';
      els.codeInner.textContent = '';
      els.preview.innerHTML = '';
      setStatus('변환 실패: ' + err.message);
    }

    els.inputStats.textContent = input.length.toLocaleString() + '자 · ' +
      (input ? input.split('\n').length : 0).toLocaleString() + '줄';
    els.outputStats.textContent = result.length.toLocaleString() + '자';

    save();
  }

  var convertTimer = null;
  function scheduleConvert() {
    clearTimeout(convertTimer);
    convertTimer = setTimeout(convert, 120);
  }

  var statusTimer = null;
  function setStatus(message) {
    els.status.textContent = message;
    clearTimeout(statusTimer);
    if (message) statusTimer = setTimeout(function () { els.status.textContent = ''; }, 2600);
  }

  /* ---------- view ---------- */

  function applyMode() {
    document.querySelectorAll('.mode-btn').forEach(function (btn) {
      var active = btn.dataset.mode === state.mode;
      btn.classList.toggle('is-active', active);
      btn.setAttribute('aria-selected', String(active));
    });

    var toHtml = state.mode === 'md2html';
    els.inputTitle.textContent = toHtml ? '마크다운 입력' : 'HTML 입력';
    els.source.placeholder = toHtml
      ? '여기에 마크다운을 붙여넣거나, 파일을 끌어다 놓으세요.'
      : '여기에 HTML을 붙여넣거나, 파일을 끌어다 놓으세요.';
    els.optBreaks.parentElement.hidden = !toHtml;
    els.optRawHtml.parentElement.hidden = !toHtml;
  }

  function applyView() {
    document.querySelectorAll('.tab').forEach(function (tab) {
      var active = tab.dataset.view === state.view;
      tab.classList.toggle('is-active', active);
      tab.setAttribute('aria-selected', String(active));
    });
    els.preview.hidden = state.view !== 'preview';
    els.codeOutput.hidden = state.view !== 'code';
  }

  function applyTheme() {
    document.documentElement.setAttribute('data-theme', state.theme);
  }

  /* ---------- file in / out ---------- */

  function readFile(file) {
    if (!file) return;
    var reader = new FileReader();
    reader.onload = function () {
      var text = String(reader.result);
      var isHtml = /\.(html?|xhtml)$/i.test(file.name);
      state.mode = isHtml ? 'html2md' : 'md2html';
      applyMode();
      els.source.value = text;
      convert();
      setStatus(file.name + ' 불러옴');
    };
    reader.onerror = function () { setStatus('파일을 읽지 못했습니다'); };
    reader.readAsText(file);
  }

  function fullHtmlDocument(body) {
    var title = (/<h1[^>]*>([\s\S]*?)<\/h1>/i.exec(body) || [])[1];
    title = title ? title.replace(/<[^>]*>/g, '').trim() : '문서';
    return [
      '<!DOCTYPE html>',
      '<html lang="ko">',
      '<head>',
      '<meta charset="utf-8">',
      '<meta name="viewport" content="width=device-width, initial-scale=1">',
      '<title>' + MarkdownConverter.escapeHtml(title) + '</title>',
      '<style>',
      'body{max-width:820px;margin:40px auto;padding:0 20px;line-height:1.7;',
      'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Apple SD Gothic Neo","Noto Sans KR",sans-serif;color:#1c2024}',
      'pre{background:#f3f4f6;padding:12px 14px;border-radius:8px;overflow-x:auto}',
      'code{background:#f3f4f6;padding:.15em .35em;border-radius:4px;font-size:.9em}',
      'pre code{background:none;padding:0}',
      'blockquote{margin:0 0 1em;padding:.2em 1em;border-left:3px solid #dfe3e8;color:#6b7280}',
      'table{border-collapse:collapse}th,td{border:1px solid #dfe3e8;padding:6px 12px}',
      'img{max-width:100%}',
      '</style>',
      '</head>',
      '<body>',
      body,
      '</body>',
      '</html>',
      ''
    ].join('\n');
  }

  function download() {
    if (!result.trim()) { setStatus('변환할 내용이 없습니다'); return; }

    var toHtml = state.mode === 'md2html';
    var content = toHtml ? fullHtmlDocument(result) : result;
    var name = toHtml ? 'converted.html' : 'converted.md';
    var type = toHtml ? 'text/html;charset=utf-8' : 'text/markdown;charset=utf-8';

    var url = URL.createObjectURL(new Blob([content], { type: type }));
    var link = document.createElement('a');
    link.href = url;
    link.download = name;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
    setStatus(name + ' 저장됨');
  }

  function copy() {
    if (!result) { setStatus('복사할 내용이 없습니다'); return; }
    var done = function () { setStatus('복사했습니다'); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(result).then(done, fallbackCopy);
    } else {
      fallbackCopy();
    }

    function fallbackCopy() {
      var area = document.createElement('textarea');
      area.value = result;
      area.style.position = 'fixed';
      area.style.opacity = '0';
      document.body.appendChild(area);
      area.select();
      try { document.execCommand('copy'); done(); } catch (err) { setStatus('복사하지 못했습니다'); }
      document.body.removeChild(area);
    }
  }

  /* ---------- events ---------- */

  function bind() {
    els.source.addEventListener('input', scheduleConvert);

    document.querySelectorAll('.mode-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        if (state.mode === btn.dataset.mode) return;
        state.mode = btn.dataset.mode;
        applyMode();
        convert();
      });
    });

    document.querySelectorAll('.tab').forEach(function (tab) {
      tab.addEventListener('click', function () {
        state.view = tab.dataset.view;
        applyView();
        save();
      });
    });

    $('theme-toggle').addEventListener('click', function () {
      state.theme = state.theme === 'dark' ? 'light' : 'dark';
      applyTheme();
      save();
    });

    $('copy-btn').addEventListener('click', copy);
    $('download-btn').addEventListener('click', download);

    $('clear-btn').addEventListener('click', function () {
      els.source.value = '';
      convert();
      els.source.focus();
    });

    $('sample-btn').addEventListener('click', function () {
      state.mode = 'md2html';
      applyMode();
      els.source.value = SAMPLE;
      convert();
    });

    els.fileInput.addEventListener('change', function () {
      readFile(this.files && this.files[0]);
      this.value = '';
    });

    els.optBreaks.addEventListener('change', function () {
      state.breaks = this.checked;
      convert();
    });

    els.optRawHtml.addEventListener('change', function () {
      state.allowHtml = this.checked;
      convert();
    });

    var dragDepth = 0;
    window.addEventListener('dragenter', function (event) {
      if (!event.dataTransfer || event.dataTransfer.types.indexOf('Files') === -1) return;
      dragDepth++;
      els.dropHint.hidden = false;
    });
    window.addEventListener('dragover', function (event) { event.preventDefault(); });
    window.addEventListener('dragleave', function () {
      dragDepth = Math.max(0, dragDepth - 1);
      if (!dragDepth) els.dropHint.hidden = true;
    });
    window.addEventListener('drop', function (event) {
      event.preventDefault();
      dragDepth = 0;
      els.dropHint.hidden = true;
      readFile(event.dataTransfer && event.dataTransfer.files[0]);
    });

    document.addEventListener('keydown', function (event) {
      if (!(event.metaKey || event.ctrlKey)) return;
      var key = event.key.toLowerCase();
      if (key === 's') { event.preventDefault(); download(); }
      else if (key === 'enter') { event.preventDefault(); copy(); }
    });
  }

  /* ---------- init ---------- */

  load();
  els.source.value = state.text;
  els.optBreaks.checked = state.breaks;
  els.optRawHtml.checked = state.allowHtml;
  applyMode();
  applyView();
  applyTheme();
  bind();
  convert();
})();
