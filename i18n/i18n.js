/*
 * Drop-in translation runtime for the Star Citizen Blueprint Finder.
 *
 * Design constraint that produced this file: the tool's UI strings live inside
 * 84KB of inline JavaScript, and no regex can reliably tell UI copy from code
 * there (a first attempt produced "candidates" like `|| q === ` and
 * `Ammo', type: 'item`). So nothing ever rewrites the JS. Instead this runtime
 * translates *rendered text nodes* against an exact-match dictionary.
 *
 * Consequences, all deliberate:
 *   - The source repo needs ONE line added (<script src="i18n.js"></script>)
 *     and is never touched again.
 *   - A string the dictionary doesn't know renders in English. Graceful
 *     degradation, never corruption.
 *   - Exact whole-text-node matching means a dictionary entry can never
 *     partially match code or a substring of an unrelated word.
 *
 * Language selection: ?lang=de, or the LANG global baked in by the build.
 */
(function () {
  "use strict";

  var DICT = window.SC_I18N_DICT || {};
  var ATTR_DICT = window.SC_I18N_ATTRS || {};
  // Ordered [{re, out}] for strings composed at runtime with numbers, e.g.
  // "Requires Sr. Contractor (5,800 rep). Earns 300 rep/run". One render
  // produced 61 distinct combinations of that single sentence; enumerating
  // them as exact entries would be endless and would silently miss new ones.
  var PATTERNS = (window.SC_I18N_PATTERNS || []).map(function (p) {
    return { re: new RegExp(p.regex), out: p.out };
  });
  // Attributes whose values are user-visible and safe to translate.
  var ATTRS = ["placeholder", "title", "aria-label", "alt"];

  if (Object.keys(DICT).length === 0 && PATTERNS.length === 0) return;

  function applyPatterns(core, depth) {
    depth = depth || 0;
    for (var i = 0; i < PATTERNS.length; i++) {
      var m = PATTERNS[i].re.exec(core);
      if (!m) continue;
      return PATTERNS[i].out.replace(/\$(\d)/g, function (_, d) {
        var v = m[Number(d)];
        if (v === undefined) return "";
        // Resolve the capture itself, so a nested phrase such as
        // "Antium Helmet Jet Obtained From:" translates the item name too
        // rather than leaving it stranded in English. Depth-limited: patterns
        // can match their own output shape and would otherwise recurse.
        if (depth < 2) {
          var t = v.trim();
          if (t) {
            var lead = v.slice(0, v.indexOf(t));
            var tail = v.slice(v.indexOf(t) + t.length);
            var sub = DICT[t];
            if (sub === undefined) sub = applyPatterns(t, depth + 1);
            if (sub !== undefined && sub !== null) return lead + sub + tail;
          }
        }
        return v;
      });
    }
    return null;
  }

  // Collected untranslated strings, so the build can report real gaps rather
  // than us guessing what the UI says. Read via window.SC_I18N_MISSING.
  var missing = Object.create(null);
  window.SC_I18N_MISSING = missing;

  // Every string we can *emit*. Without this, a node we just translated gets
  // re-read on a later mutation pass, isn't found in the EN->target dictionary,
  // and is logged as "missing" -- which poisoned the report with already-German
  // entries like "ABONNIEREN" and made the CI gap list useless.
  var OUTPUTS = Object.create(null);
  for (var k in DICT) {
    if (Object.prototype.hasOwnProperty.call(DICT, k)) OUTPUTS[DICT[k]] = true;
  }

  function translateText(raw) {
    // Preserve surrounding whitespace exactly; only the trimmed core is looked
    // up. Layout in this tool depends on some of that spacing.
    var m = /^(\s*)([\s\S]*?)(\s*)$/.exec(raw);
    var lead = m[1], core = m[2], trail = m[3];
    if (!core) return null;
    var hit = DICT[core];
    if (hit === undefined) hit = applyPatterns(core);
    if (hit === undefined || hit === null) {
      // Only report as missing if it is not something we already produced,
      // and it still looks like untranslated Latin-script source text.
      if (/[A-Za-z]{2}/.test(core) && OUTPUTS[core] === undefined) {
        missing[core] = (missing[core] || 0) + 1;
      }
      return null;
    }
    return lead + hit + trail;
  }

  function walkTextNodes(root) {
    // SHOW_TEXT only: element structure, attributes and event handlers are
    // never touched, so no amount of dictionary content can break the tool.
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: function (node) {
        var p = node.parentNode;
        if (!p) return NodeFilter.FILTER_REJECT;
        var tag = p.nodeName;
        // Never translate inside code-bearing elements.
        if (tag === "SCRIPT" || tag === "STYLE" || tag === "TEXTAREA") {
          return NodeFilter.FILTER_REJECT;
        }
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    var node;
    while ((node = walker.nextNode())) {
      var out = translateText(node.nodeValue);
      if (out !== null && out !== node.nodeValue) node.nodeValue = out;
    }
  }

  function walkAttributes(root) {
    // querySelectorAll("*") excludes `root` itself, so an added node carrying
    // its own title/placeholder would be skipped. Include it explicitly.
    var els = root.querySelectorAll ? [root].concat([].slice.call(
      root.querySelectorAll("*"))) : [];
    for (var i = 0; i < els.length; i++) {
      if (!els[i] || els[i].nodeType !== 1 || !els[i].hasAttribute) continue;
      for (var a = 0; a < ATTRS.length; a++) {
        var name = ATTRS[a];
        if (!els[i].hasAttribute(name)) continue;
        var val = els[i].getAttribute(name);
        var hit = ATTR_DICT[val] !== undefined ? ATTR_DICT[val] : DICT[val];
        // The rep-requirement tooltips are title attributes, so patterns have
        // to run here too, not only on text nodes.
        if (hit === undefined) hit = applyPatterns(val.trim());
        if (hit !== undefined && hit !== null && hit !== val) {
          els[i].setAttribute(name, hit);
        }
      }
    }
  }

  function apply(root) {
    if (!root) return;
    if (root.nodeType === Node.TEXT_NODE) {
      var out = translateText(root.nodeValue);
      if (out !== null && out !== root.nodeValue) root.nodeValue = out;
      return;
    }
    walkTextNodes(root);
    walkAttributes(root);
  }

  // Re-applying on every mutation would fight the tool's own re-renders and
  // burn CPU on a 1,500-item list. Batch through one animation frame instead.
  var pending = [];
  var scheduled = false;
  function flush() {
    scheduled = false;
    var batch = pending;
    pending = [];
    observer.disconnect();
    try {
      for (var i = 0; i < batch.length; i++) apply(batch[i]);
    } finally {
      observe();
    }
  }

  var observer = new MutationObserver(function (records) {
    for (var i = 0; i < records.length; i++) {
      var r = records[i];
      if (r.type === "characterData") {
        pending.push(r.target);
      } else {
        for (var j = 0; j < r.addedNodes.length; j++) pending.push(r.addedNodes[j]);
      }
    }
    if (pending.length && !scheduled) {
      scheduled = true;
      requestAnimationFrame(flush);
    }
  });

  function observe() {
    observer.observe(document.documentElement, {
      childList: true,
      subtree: true,
      characterData: true
    });
  }

  function start() {
    apply(document.body || document.documentElement);
    observe();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
    // Start observing immediately so content rendered before DOMContentLoaded
    // is still caught.
    observe();
  } else {
    start();
  }

  if (window.SC_I18N_LANG) {
    document.documentElement.setAttribute("lang", window.SC_I18N_LANG);
  }
})();
