/* Shell of the clickable demonstration: shows one captured page at a time in a frame. */
/* The data of the page is gzip + base64 text in <script id="..." type="text/plain">; the browser unpacks it (every current browser has DecompressionStream) */
async function readPackedData(id) {
  var text = document.getElementById(id).textContent.trim();
  if (typeof DecompressionStream === 'undefined') {
    document.body.innerHTML = '<p style="font-family:sans-serif;margin:2em">This demonstration needs a current browser (Chrome, Edge, Firefox 113+ or Safari 16.4+).</p>';
    throw new Error('DecompressionStream is not available');
  }
  var bytes = Uint8Array.from(atob(text), function (c) { return c.charCodeAt(0); });
  var stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
  return await new Response(stream).text();
}
(async function () {
  'use strict';
  var DATA = JSON.parse(await readPackedData('site-data'));
  if (/[?&]bare\b/.test(location.search)) {   // ?bare hides the strip on top (for screenshots)
    document.getElementById('ribbon').style.display = 'none';
    document.getElementById('frame').style.height = '100%';
  }
  var frame = document.getElementById('frame'), toast = document.getElementById('toast'), timer = null, current = null;

  function say(text) {
    toast.textContent = text; toast.style.display = 'block';
    clearTimeout(timer); timer = setTimeout(function () { toast.style.display = 'none'; }, 4500);
  }
  function assemble(key) {
    var html = DATA.pages[key];
    html = html.replace(/<!--css:([^>]*?)-->/g, function (m, path) { return '<style>' + (DATA.css[path] || '') + '</style>'; });
    html = html.replace(/<!--js:([^>]*?)-->/g, function (m, path) { return '<script>' + (DATA.js[path] || '').replace(/<\/script/gi, '<\\/script') + '<\/script>'; });
    var tail = '<style>' + DATA.theme_css + '</style>';
    html = html.indexOf('</head>') !== -1 ? html.replace('</head>', function () { return tail + '</head>'; }) : tail + html;
    var bridge = '<script>window.__demoFiles = ' + JSON.stringify(DATA.files || {}).replace(/</g, '\\u003c') + ';' + DATA.bridge + '<\/script>';
    return html.indexOf('</body>') !== -1 ? html.replace('</body>', function () { return bridge + '</body>'; }) : html + bridge;
  }
  function show(key, push) {
    if (!DATA.pages[key]) key = DATA.start;
    current = key;
    frame.srcdoc = assemble(key);
    if (push !== false && location.hash !== '#/' + key) history.pushState(null, '', '#/' + key);
    document.title = 'BacLab demo - ' + key;
  }

  /* What to say when a button of a captured page is pressed: the first rule whose pattern matches the address the form would be sent to
     (and, where it matters, the button's label) wins. Add a rule here when a page gets a new form. [pattern, method or '', button pattern or null, message] */
  var DEMO = 'Demonstration only: ';
  var SUBMIT_RULES = [
    [/\/my-jobs\/email\//, 'post', null, DEMO + 'your notification address is not saved here. On a real installation BacLab sends you an e-mail when a run finishes (the administrator can limit the allowed domains).'],
    [/\/my-jobs\/[^/]+\/label\//, 'post', null, DEMO + 'the name of the run is not saved. On a real installation a named run is easy to find again in "my jobs".'],
    [/\/my-jobs\/[^/]+\/project\//, 'post', null, DEMO + 'the run is not added to a project. On a real installation projects collect related runs and compare their key findings in one table.'],
    [/\/my-jobs\/[^/]+\/private\//, 'post', null, DEMO + 'the visibility of the run is not changed. On a real installation a private run can only be opened by you and the members of your group.'],
    [/\/my-jobs\/[^/]+\/retention\//, 'post', null, DEMO + 'the retention time is not changed. On a real installation you can keep your own results longer than the default.'],
    [/\/my-jobs\/[^/]+\/rerun\//, 'post', null, DEMO + 'no new job is started. On a real installation "Run again" repeats the run with the same input and settings.'],
    [/\/my-jobs\/[^/]+\/send\//, 'post', null, DEMO + 'no job is started. On a real installation the chosen result files become the input of the other tool.'],
    [/\/my-jobs\/api-keys\/[^/]+\/delete\//, 'post', null, DEMO + 'no API key is revoked.'],
    [/\/my-jobs\/api-keys\//, 'post', null, DEMO + 'no API key is created. On a real installation the key is shown once and lets scripts and the baclab-client submit jobs as you.'],
    [/\/accounts\/logout\//, '', null, DEMO + 'you cannot log out here: this file always shows BacLab as a logged-in laboratory member.'],
    [/\/accounts\/login\//, '', null, DEMO + 'logging in is not part of the demonstration: this file shows BacLab as a logged-in laboratory member.'],
    [/\/accounts\//, '', null, DEMO + 'account changes (password, sign-up) are not part of the demonstration.'],
    [/\/projects\/\d+\/delete\//, 'post', null, DEMO + 'the project folder is not deleted (the runs inside would stay in "my jobs" anyway).'],
    [/\/projects\//, '', null, DEMO + 'projects are not changed here.'],
    [/\/admin\/logout\//, '', null, DEMO + 'you cannot log out here: this file always shows the administration pages as an administrator sees them.'],
    [/\/admin\/.*(add|change)\/?$/, 'post', null, DEMO + 'nothing is saved. On a real installation this change would be stored and take effect at once.'],
    [/\/admin\//, 'post', /^(go|delete|yes)/i, DEMO + 'the action is not carried out. On a real installation it would be applied to the selected rows.'],
    [/\/admin\//, 'post', null, DEMO + 'nothing is saved or changed in the administration pages.'],
    [/\/admin\//, 'get', null, DEMO + 'searching and filtering the lists needs the server. The lists are shown as they were captured.'],
    [/\/my-jobs\//, 'get', null, DEMO + 'searching, filtering and grouping need the server. The list is shown as it was captured.'],
    [/\/results\/?$/, 'get', null, DEMO + 'looking up a job by its ID needs the server. Open the example results from a tool page or from "my jobs".'],
    [/\/(custom\/)?[A-Za-z0-9_]+\/$/, 'post', null, 'Static demonstration: nothing can be submitted. Use "View Example Results" on the tool page to see what the tool produces.']
  ];
  var MISSING_RULES = [
    [/\/(example-data|download|report-file)\//, 'Downloads are not part of the static demonstration.'],
    [/\/accounts\//, DEMO + 'account pages (login, password) are not part of the demonstration.'],
    [/\/admin\/.*\/(history|delete)\//, DEMO + 'this page is not part of the demonstration.'],
    [/\/strains\//, DEMO + 'the strain collection needs the data of an installation and is not part of the demonstration.']
  ];

  function messageForSubmit(m) {
    var base = new URL(DATA.urls[current] || '/', 'http://baclab.local');
    var path = new URL(m.action || '', base).pathname;
    for (var i = 0; i < SUBMIT_RULES.length; i++) {
      var rule = SUBMIT_RULES[i];
      if (rule[0].test(path) && (!rule[1] || rule[1] === m.method) && (!rule[2] || rule[2].test(m.button || ''))) return rule[3];
    }
    return 'Static demonstration: nothing can be submitted here.';
  }

  function resolve(href) {
    var base = new URL(DATA.urls[current] || '/', 'http://baclab.local');
    var u;
    try { u = new URL(href, base); } catch (e) { return null; }
    if (u.host !== 'baclab.local') return { external: u.href };
    var candidates = [u.pathname + u.search, u.pathname, u.pathname.replace(/\/$/, ''), u.pathname.replace(/\/?$/, '/')];
    for (var i = 0; i < candidates.length; i++) if (DATA.aliases[candidates[i]]) return { key: DATA.aliases[candidates[i]] };
    return { missing: u.pathname };
  }
  window.addEventListener('message', function (event) {
    var m = event.data || {};
    if (m.baclab === 'download') return say('Downloads are not part of the static demonstration.');
    if (m.baclab === 'say') return say(m.text);
    if (m.baclab === 'submit') return say(messageForSubmit(m));
    if (m.baclab !== 'go') return;
    var target = resolve(m.href);
    if (!target) return;
    if (target.external) return window.open(target.external, '_blank', 'noopener');
    if (target.key) return show(target.key);
    for (var j = 0; j < MISSING_RULES.length; j++) if (MISSING_RULES[j][0].test(target.missing)) return say(MISSING_RULES[j][1]);
    if (m.download) return say('Downloads are not part of the static demonstration.');
    say('This page is not part of the static demonstration (it needs the server or data of an installation).');
  });
  window.addEventListener('popstate', function () { show((location.hash.match(/^#\/(.+)$/) || [])[1] || DATA.start, false); });
  show((location.hash.match(/^#\/(.+)$/) || [])[1] || DATA.start, false);
})();
