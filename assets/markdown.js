/**
 * Markdown -> HTML converter.
 *
 * Dependency-free so the page can be served as a plain static site.
 * Supports: ATX/setext headings, fenced & indented code, blockquotes,
 * ordered/unordered/nested/task lists, tables, horizontal rules,
 * reference links, images, emphasis, strikethrough, inline code.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.MarkdownConverter = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var HTML_ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

  function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, function (c) { return HTML_ESCAPES[c]; });
  }

  // Blocks anything that would execute on click; everything else passes through.
  function safeUrl(url) {
    var trimmed = String(url).trim();
    if (/^javascript:/i.test(trimmed)) return '#';
    if (/^vbscript:/i.test(trimmed)) return '#';
    if (/^data:/i.test(trimmed) && !/^data:image\//i.test(trimmed)) return '#';
    return trimmed;
  }

  var ITEM_RE = /^( {0,3})([-*+]|\d{1,9}[.)])(\s+)(.*)$/;
  var HR_RE = /^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$/;
  var FENCE_RE = /^( {0,3})(`{3,}|~{3,})[ \t]*([^`]*)$/;

  /* ------------------------------------------------------------------ *
   * Inline
   * ------------------------------------------------------------------ */

  function inline(text, ctx) {
    var codes = [];
    var tokens = [];
    var escapes = [];

    var s = String(text);

    // 1. Code spans are literal: pull them out before anything else runs.
    s = s.replace(/(`+)([\s\S]*?[^`])\1(?!`)/g, function (_, ticks, code) {
      codes.push(code.replace(/^ ([\s\S]*) $/, '$1'));
      return '\u0000C' + (codes.length - 1) + '\u0000';
    });

    // 2. Backslash escapes.
    s = s.replace(/\\([\\`*_{}\[\]()#+\-.!>~|])/g, function (_, ch) {
      escapes.push(ch);
      return '\u0000E' + (escapes.length - 1) + '\u0000';
    });

    if (!ctx.allowHtml) s = escapeHtml(s);

    function token(html) {
      tokens.push(html);
      return '\u0000T' + (tokens.length - 1) + '\u0000';
    }

    function attr(value) {
      return escapeHtml(value).replace(/&amp;(#?\w+;)/g, '&$1');
    }

    var TITLE = '(?:\\s+(?:&quot;|"|\')([\\s\\S]*?)(?:&quot;|"|\'))?';
    var IMAGE_RE = new RegExp('!\\[([^\\]]*)\\]\\(\\s*(<[^>]*>|(?:[^\\s()]|\\([^\\s()]*\\))*)' + TITLE + '\\s*\\)', 'g');
    var LINK_RE = new RegExp('\\[([^\\]]*)\\]\\(\\s*(<[^>]*>|(?:[^\\s()]|\\([^\\s()]*\\))*)' + TITLE + '\\s*\\)', 'g');

    function stripAngles(url) {
      return url.replace(/^&lt;([\s\S]*)&gt;$/, '$1').replace(/^<([\s\S]*)>$/, '$1');
    }

    // 3. Images, then inline links, then reference links.
    s = s.replace(IMAGE_RE, function (_, alt, url, title) {
      return token('<img src="' + attr(safeUrl(stripAngles(url))) + '" alt="' + attr(alt) + '"' +
        (title ? ' title="' + attr(title) + '"' : '') + '>');
    });

    s = s.replace(LINK_RE, function (_, label, url, title) {
      return token('<a href="' + attr(safeUrl(stripAngles(url))) + '"' +
        (title ? ' title="' + attr(title) + '"' : '') + '>') + label + '</a>';
    });

    s = s.replace(/!?\[([^\]]*)\](?:\[([^\]]*)\])?/g, function (whole, label, id) {
      var key = (id || label).trim().toLowerCase();
      var ref = ctx.refs[key];
      if (!ref) return whole;
      var isImage = whole.charAt(0) === '!';
      var titleAttr = ref.title ? ' title="' + attr(ref.title) + '"' : '';
      if (isImage) {
        return token('<img src="' + attr(safeUrl(ref.url)) + '" alt="' + attr(label) + '"' + titleAttr + '>');
      }
      return token('<a href="' + attr(safeUrl(ref.url)) + '"' + titleAttr + '>') + label + '</a>';
    });

    // 4. Autolinks.
    s = s.replace(/(?:&lt;|<)((?:https?|ftp|mailto):[^\s<>]+)(?:&gt;|>)/g, function (_, url) {
      return token('<a href="' + attr(safeUrl(url)) + '">') + escapeHtml(url) + '</a>';
    });

    // 5. Emphasis. Tokenised URLs are already out of reach of these.
    s = s.replace(/\*\*\*([^\s*][\s\S]*?)\*\*\*/g, '<strong><em>$1</em></strong>');
    s = s.replace(/\*\*([^\s*][\s\S]*?)\*\*(?!\*)/g, '<strong>$1</strong>');
    s = s.replace(/(^|[^\w_])__([^\s_][\s\S]*?)__(?![\w_])/g, '$1<strong>$2</strong>');
    s = s.replace(/(^|[^*])\*([^\s*][\s\S]*?)\*(?!\*)/g, '$1<em>$2</em>');
    s = s.replace(/(^|[^\w_])_([^\s_][\s\S]*?)_(?![\w_])/g, '$1<em>$2</em>');
    s = s.replace(/~~([\s\S]+?)~~/g, '<del>$1</del>');

    // 6. Hard line breaks.
    s = s.replace(/ {2,}\n/g, '<br>\n');
    if (ctx.breaks) s = s.replace(/([^>\n])\n(?!$)/g, '$1<br>\n');

    // 7. Put the protected pieces back.
    s = s.replace(/\u0000T(\d+)\u0000/g, function (_, n) { return tokens[+n]; });
    s = s.replace(/\u0000E(\d+)\u0000/g, function (_, n) { return escapeHtml(escapes[+n]); });
    s = s.replace(/\u0000C(\d+)\u0000/g, function (_, n) {
      return '<code>' + escapeHtml(codes[+n]) + '</code>';
    });

    return s;
  }

  /* ------------------------------------------------------------------ *
   * Blocks
   * ------------------------------------------------------------------ */

  function slugify(text) {
    return text
      .replace(/<[^>]*>/g, '')
      .trim()
      .toLowerCase()
      .replace(/[^\w가-힣\- ]+/g, '')
      .replace(/\s+/g, '-') || 'section';
  }

  function parseBlocks(lines, ctx) {
    var out = [];
    var i = 0;

    while (i < lines.length) {
      var line = lines[i];

      if (!line.trim()) { i++; continue; }

      // Fenced code
      var fence = FENCE_RE.exec(line);
      if (fence) {
        var marker = fence[2];
        var info = (fence[3] || '').trim().split(/\s+/)[0];
        var indent = fence[1].length;
        var body = [];
        i++;
        while (i < lines.length && !new RegExp('^ {0,3}' + marker[0] + '{' + marker.length + ',}[ \t]*$').test(lines[i])) {
          body.push(lines[i].slice(indent));
          i++;
        }
        i++; // closing fence
        out.push('<pre><code' + (info ? ' class="language-' + escapeHtml(info) + '"' : '') + '>' +
          escapeHtml(body.join('\n')) + '</code></pre>');
        continue;
      }

      // Horizontal rule (checked before lists so `- - -` is not an item)
      if (HR_RE.test(line)) { out.push('<hr>'); i++; continue; }

      // ATX heading
      var atx = /^ {0,3}(#{1,6})(?:\s+(.*?))?\s*(?:\s#+)?\s*$/.exec(line);
      if (atx) {
        var level = atx[1].length;
        var content = inline((atx[2] || '').replace(/\s+#+\s*$/, ''), ctx);
        out.push('<h' + level + ' id="' + escapeHtml(slugify(content)) + '">' + content + '</h' + level + '>');
        i++;
        continue;
      }

      // Blockquote
      if (/^ {0,3}>/.test(line)) {
        var quoted = [];
        while (i < lines.length && lines[i].trim() && !HR_RE.test(lines[i])) {
          quoted.push(lines[i].replace(/^ {0,3}>[ \t]?/, ''));
          i++;
        }
        out.push('<blockquote>\n' + parseBlocks(quoted, ctx) + '\n</blockquote>');
        continue;
      }

      // Table
      if (line.indexOf('|') !== -1 && i + 1 < lines.length &&
          /^ {0,3}\|?[ \t]*:?-{1,}:?[ \t]*(\|[ \t]*:?-{1,}:?[ \t]*)*\|?[ \t]*$/.test(lines[i + 1])) {
        var consumed = parseTable(lines, i, ctx);
        if (consumed) { out.push(consumed.html); i = consumed.next; continue; }
      }

      // List
      if (ITEM_RE.test(line)) {
        var list = parseList(lines, i, ctx);
        out.push(list.html);
        i = list.next;
        continue;
      }

      // Indented code block
      if (/^ {4}/.test(line)) {
        var codeLines = [];
        while (i < lines.length && (/^ {4}/.test(lines[i]) || !lines[i].trim())) {
          codeLines.push(lines[i].replace(/^ {4}/, ''));
          i++;
        }
        while (codeLines.length && !codeLines[codeLines.length - 1].trim()) codeLines.pop();
        out.push('<pre><code>' + escapeHtml(codeLines.join('\n')) + '</code></pre>');
        continue;
      }

      // Setext heading
      if (i + 1 < lines.length && /^ {0,3}(=+|-+)\s*$/.test(lines[i + 1]) && line.trim()) {
        var setextLevel = lines[i + 1].trim()[0] === '=' ? 1 : 2;
        var setextContent = inline(line.trim(), ctx);
        out.push('<h' + setextLevel + ' id="' + escapeHtml(slugify(setextContent)) + '">' +
          setextContent + '</h' + setextLevel + '>');
        i += 2;
        continue;
      }

      // Raw HTML block
      if (ctx.allowHtml && /^ {0,3}<(\/?)([a-zA-Z][\w-]*)/.test(line)) {
        var htmlBlock = [];
        while (i < lines.length && lines[i].trim()) { htmlBlock.push(lines[i]); i++; }
        out.push(htmlBlock.join('\n'));
        continue;
      }

      // Paragraph
      var para = [];
      while (i < lines.length && lines[i].trim() &&
             !HR_RE.test(lines[i]) &&
             !FENCE_RE.test(lines[i]) &&
             !/^ {0,3}#{1,6}(\s|$)/.test(lines[i]) &&
             !/^ {0,3}>/.test(lines[i]) &&
             !ITEM_RE.test(lines[i]) &&
             !(i > 0 && /^ {0,3}(=+|-+)\s*$/.test(lines[i]))) {
        para.push(lines[i]);
        i++;
      }
      if (!para.length) { para.push(lines[i]); i++; }
      out.push('<p>' + inline(para.join('\n').trim(), ctx) + '</p>');
    }

    return out.join('\n');
  }

  function parseTable(lines, start, ctx) {
    function cells(row) {
      return row.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(function (c) { return c.trim(); });
    }

    var header = cells(lines[start]);
    var aligns = cells(lines[start + 1]).map(function (spec) {
      if (/^:-+:$/.test(spec)) return 'center';
      if (/^:-+$/.test(spec)) return 'left';
      if (/^-+:$/.test(spec)) return 'right';
      return '';
    });
    if (header.length !== aligns.length) return null;

    var i = start + 2;
    var rows = [];
    while (i < lines.length && lines[i].trim() && lines[i].indexOf('|') !== -1) {
      rows.push(cells(lines[i]));
      i++;
    }

    function cellHtml(tag, value, index) {
      var align = aligns[index] ? ' style="text-align:' + aligns[index] + '"' : '';
      return '<' + tag + align + '>' + inline(value == null ? '' : value, ctx) + '</' + tag + '>';
    }

    var html = '<table>\n<thead>\n<tr>' +
      header.map(function (h, n) { return cellHtml('th', h, n); }).join('') +
      '</tr>\n</thead>\n';

    if (rows.length) {
      html += '<tbody>\n' + rows.map(function (row) {
        return '<tr>' + header.map(function (_, n) { return cellHtml('td', row[n], n); }).join('') + '</tr>';
      }).join('\n') + '\n</tbody>\n';
    }

    return { html: html + '</table>', next: i };
  }

  function parseList(lines, start, ctx) {
    var first = ITEM_RE.exec(lines[start]);
    var ordered = /^\d/.test(first[2]);
    var startNumber = ordered ? parseInt(first[2], 10) : 1;
    var items = [];
    var current = null;
    var loose = false;
    var blanks = 0;
    var i = start;

    while (i < lines.length) {
      var line = lines[i];

      if (!line.trim()) { blanks++; i++; continue; }

      var indent = line.match(/^ */)[0].length;
      var match = ITEM_RE.exec(line);

      // Deeper indentation continues the current item (nested lists land here).
      if (current && indent >= current.indent) {
        if (blanks) { loose = true; while (blanks--) current.lines.push(''); blanks = 0; }
        current.lines.push(line.slice(current.indent));
        i++;
        continue;
      }

      if (match && !(blanks > 1)) {
        if (/^\d/.test(match[2]) !== ordered) break;
        if (blanks && items.length) loose = true;
        blanks = 0;
        current = { lines: [match[4]], indent: match[1].length + match[2].length + match[3].length };
        items.push(current);
        i++;
        continue;
      }

      // Lazy continuation of a paragraph inside the item.
      if (current && !blanks && !HR_RE.test(line)) { current.lines.push(line); i++; continue; }

      break;
    }

    var html = items.map(function (item) {
      var body = item.lines;
      var task = /^\[([ xX])\]\s+/.exec(body[0] || '');
      var checkbox = '';
      if (task) {
        checkbox = '<input type="checkbox" disabled' + (task[1] === ' ' ? '' : ' checked') + '> ';
        body = body.slice();
        body[0] = body[0].replace(/^\[([ xX])\]\s+/, '');
      }
      var inner = parseBlocks(body, ctx);
      if (!loose) inner = inner.replace(/^<p>([\s\S]*?)<\/p>\n?/, '$1');
      return '<li' + (task ? ' class="task-list-item"' : '') + '>' + checkbox + inner + '</li>';
    }).join('\n');

    var tag = ordered ? 'ol' : 'ul';
    var openTag = ordered && startNumber !== 1 ? '<ol start="' + startNumber + '">' : '<' + tag + '>';

    return { html: openTag + '\n' + html + '\n</' + tag + '>', next: i };
  }

  /* ------------------------------------------------------------------ *
   * Entry point
   * ------------------------------------------------------------------ */

  function markdownToHtml(source, options) {
    options = options || {};
    var ctx = {
      refs: {},
      breaks: !!options.breaks,
      allowHtml: !!options.allowHtml
    };

    var text = String(source == null ? '' : source)
      .replace(/\u0000/g, '')
      .replace(/\r\n?/g, '\n')
      .replace(/\t/g, '    ');

    // Pull out link reference definitions first so they never render.
    var lines = text.split('\n').filter(function (line) {
      var def = /^ {0,3}\[([^\]]+)\]:\s*(\S+)(?:\s+["'(](.*)["')])?\s*$/.exec(line);
      if (!def) return true;
      ctx.refs[def[1].trim().toLowerCase()] = { url: def[2], title: def[3] || '' };
      return false;
    });

    return parseBlocks(lines, ctx);
  }

  return {
    markdownToHtml: markdownToHtml,
    escapeHtml: escapeHtml
  };
});
