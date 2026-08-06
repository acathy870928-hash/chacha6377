/**
 * HTML -> Markdown converter.
 *
 * Uses the browser DOM parser; a compatible parser (e.g. jsdom) can be
 * injected through options.parseHtml when running outside a browser.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.HtmlToMarkdown = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var BLOCK_TAGS = /^(ADDRESS|ARTICLE|ASIDE|BLOCKQUOTE|DIV|DL|FIELDSET|FIGURE|FOOTER|FORM|H[1-6]|HEADER|HR|LI|MAIN|NAV|OL|P|PRE|SECTION|TABLE|UL)$/;
  var SKIP_TAGS = /^(SCRIPT|STYLE|NOSCRIPT|TEMPLATE|IFRAME|OBJECT|EMBED)$/;

  function escapeText(text) {
    return text
      .replace(/([\\`*_\[\]])/g, '\\$1')
      .replace(/^(\s*)(#{1,6})(\s)/gm, '$1\\$2$3')
      .replace(/^(\s*)([-+])(\s)/gm, '$1\\$2$3')
      .replace(/^(\s*)(\d+)\.(\s)/gm, '$1$2\\.$3')
      .replace(/^(\s*)>/gm, '$1\\>');
  }

  function collapse(text) {
    return text.replace(/\s+/g, ' ');
  }

  function indentLines(text, prefix, firstPrefix) {
    var lines = text.split('\n');
    return lines.map(function (line, index) {
      if (index === 0) return (firstPrefix == null ? prefix : firstPrefix) + line;
      return line.trim() ? prefix + line : '';
    }).join('\n');
  }

  function attr(node, name) {
    var value = node.getAttribute && node.getAttribute(name);
    return value == null ? '' : value;
  }

  function convertNode(node, ctx) {
    // Text node
    if (node.nodeType === 3) {
      return escapeText(collapse(node.nodeValue));
    }

    if (node.nodeType !== 1) return '';

    var tag = node.nodeName.toUpperCase();
    if (SKIP_TAGS.test(tag)) return '';

    switch (tag) {
      case 'BR':
        return '  \n';
      case 'HR':
        return '\n\n---\n\n';
      case 'IMG': {
        var alt = collapse(attr(node, 'alt'));
        var src = attr(node, 'src');
        var imgTitle = attr(node, 'title');
        return '![' + alt + '](' + src + (imgTitle ? ' "' + imgTitle + '"' : '') + ')';
      }
      case 'H1': case 'H2': case 'H3': case 'H4': case 'H5': case 'H6': {
        var level = Number(tag.charAt(1));
        var heading = children(node, ctx).trim().replace(/\n+/g, ' ');
        return '\n\n' + new Array(level + 1).join('#') + ' ' + heading + '\n\n';
      }
      case 'P': case 'DIV': case 'SECTION': case 'ARTICLE': case 'HEADER':
      case 'FOOTER': case 'MAIN': case 'ASIDE': case 'NAV': case 'FIGURE': {
        var block = children(node, ctx).trim();
        return block ? '\n\n' + block + '\n\n' : '';
      }
      case 'STRONG': case 'B': {
        var strong = children(node, ctx).trim();
        return strong ? '**' + strong + '**' : '';
      }
      case 'EM': case 'I': {
        var em = children(node, ctx).trim();
        return em ? '*' + em + '*' : '';
      }
      case 'DEL': case 'S': case 'STRIKE': {
        var del = children(node, ctx).trim();
        return del ? '~~' + del + '~~' : '';
      }
      case 'CODE': case 'KBD': case 'SAMP': {
        var code = node.textContent.replace(/\n/g, ' ');
        var ticks = '`';
        while (code.indexOf(ticks) !== -1) ticks += '`';
        var pad = /^`|`$/.test(code) ? ' ' : '';
        return ticks + pad + code + pad + ticks;
      }
      case 'PRE': {
        var raw = node.textContent.replace(/\n$/, '');
        var lang = '';
        var codeChild = node.querySelector ? node.querySelector('code') : null;
        if (codeChild) {
          var cls = attr(codeChild, 'class');
          var langMatch = /(?:language|lang)-([\w+#.-]+)/.exec(cls);
          if (langMatch) lang = langMatch[1];
        }
        var fence = '```';
        while (raw.indexOf(fence) !== -1) fence += '`';
        return '\n\n' + fence + lang + '\n' + raw + '\n' + fence + '\n\n';
      }
      case 'A': {
        var label = children(node, ctx).trim();
        var href = attr(node, 'href');
        var linkTitle = attr(node, 'title');
        if (!href) return label;
        if (!label) return '';
        return '[' + label + '](' + href + (linkTitle ? ' "' + linkTitle + '"' : '') + ')';
      }
      case 'BLOCKQUOTE': {
        var quote = children(node, ctx).trim();
        if (!quote) return '';
        return '\n\n' + quote.split('\n').map(function (line) {
          return line.trim() ? '> ' + line : '>';
        }).join('\n') + '\n\n';
      }
      case 'UL': case 'OL':
        return '\n\n' + convertList(node, ctx) + '\n\n';
      case 'TABLE':
        return '\n\n' + convertTable(node, ctx) + '\n\n';
      case 'INPUT':
        if (attr(node, 'type').toLowerCase() === 'checkbox') {
          return node.checked || node.hasAttribute('checked') ? '[x] ' : '[ ] ';
        }
        return '';
      default:
        return children(node, ctx);
    }
  }

  function children(node, ctx) {
    var out = '';
    for (var i = 0; i < node.childNodes.length; i++) {
      out += convertNode(node.childNodes[i], ctx);
    }
    return out;
  }

  function convertList(node, ctx) {
    var ordered = node.nodeName.toUpperCase() === 'OL';
    var start = parseInt(attr(node, 'start'), 10);
    var index = isNaN(start) ? 1 : start;
    var lines = [];

    for (var i = 0; i < node.children.length; i++) {
      var li = node.children[i];
      if (li.nodeName.toUpperCase() !== 'LI') continue;
      var marker = ordered ? index++ + '. ' : '- ';
      var content = children(li, ctx)
        .replace(/^\n+/, '')
        .replace(/\n+$/, '')
        // A nested list stays tight instead of turning the parent into a loose list.
        .replace(/\n{2,}(?=[ \t]*(?:[-*+]|\d+\.)\s)/g, '\n');
      var pad = new Array(marker.length + 1).join(' ');
      lines.push(indentLines(content, pad, marker));
    }

    return lines.join('\n');
  }

  function cellText(cell, ctx) {
    return children(cell, ctx).trim().replace(/\n+/g, ' ').replace(/\|/g, '\\|');
  }

  function convertTable(node, ctx) {
    var rows = node.querySelectorAll ? node.querySelectorAll('tr') : [];
    if (!rows.length) return '';

    var matrix = [];
    for (var i = 0; i < rows.length; i++) {
      var cells = rows[i].children;
      var row = [];
      for (var j = 0; j < cells.length; j++) {
        var name = cells[j].nodeName.toUpperCase();
        if (name === 'TD' || name === 'TH') row.push(cellText(cells[j], ctx));
      }
      if (row.length) matrix.push(row);
    }
    if (!matrix.length) return '';

    var width = matrix.reduce(function (max, row) { return Math.max(max, row.length); }, 0);
    var normalise = function (row) {
      var copy = row.slice();
      while (copy.length < width) copy.push('');
      return '| ' + copy.join(' | ') + ' |';
    };

    var header = normalise(matrix[0]);
    var divider = '|' + new Array(width + 1).join(' --- |');
    var body = matrix.slice(1).map(normalise);

    return [header, divider].concat(body).join('\n');
  }

  function htmlToMarkdown(html, options) {
    options = options || {};

    var parse = options.parseHtml || function (input) {
      if (typeof DOMParser === 'undefined') {
        throw new Error('HTML 파서를 사용할 수 없습니다. options.parseHtml 을 지정하세요.');
      }
      return new DOMParser().parseFromString(input, 'text/html').body;
    };

    var body = parse(String(html == null ? '' : html));
    if (!body) return '';

    var out = children(body, {});

    return out
      .replace(/\u00a0/g, ' ')
      // Keep intentional two-space hard breaks, drop other trailing whitespace.
      .replace(/[ \t]+\n/g, function (match) { return /  \n$/.test(match) ? '  \n' : '\n'; })
      .replace(/\n{3,}/g, '\n\n')
      .trim() + '\n';
  }

  return {
    htmlToMarkdown: htmlToMarkdown,
    escapeText: escapeText
  };
});
