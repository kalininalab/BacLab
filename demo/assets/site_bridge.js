/* Runs inside every captured page: sends link clicks and form submits to the shell instead of the (missing) server. */
(function () {
  document.addEventListener('click', function (event) {
    var a = event.target.closest && event.target.closest('a[href]');
    if (!a) return;
    var href = a.getAttribute('href');
    if (href && href.indexOf('javascript:') === 0) return;
    event.preventDefault();   // the base address of a framed page is the shell's own: following "#!", "#" or "" would load the shell inside the frame
    if (!href) return;
    if (href.charAt(0) === '#') {   // in-page link: scroll to the target, "#!" and "#" do nothing
      var id = href.slice(1), target = id && id !== '!' ? (document.getElementById(id) || document.getElementsByName(id)[0]) : null;
      if (target) target.scrollIntoView();
      return;
    }
    parent.postMessage({ baclab: 'go', href: href, download: a.hasAttribute('download') }, '*');
  }, true);
  document.addEventListener('submit', function (event) {
    event.preventDefault();
    var form = event.target, submitter = event.submitter;
    parent.postMessage({
      baclab: 'submit', action: form.getAttribute('action') || '', method: (form.getAttribute('method') || 'get').toLowerCase(),
      button: submitter ? (submitter.value || submitter.textContent || '').trim() : '', formId: form.id || ''
    }, '*');
  }, true);
  // The "Download results" button reads the job id from the address bar: there is none here, and nothing to download
  document.addEventListener('click', function (event) {
    var button = event.target.closest && event.target.closest('#downloadResults, [onclick*="downloadResults"]');
    if (!button) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    parent.postMessage({ baclab: 'download' }, '*');
  }, true);
  // Messages the page would show in a browser dialog appear in the same red banner as the shell's own
  window.confirm = function () { return true; };   // the question is answered by the demonstration's own message that follows
  window.alert = function (text) { parent.postMessage({ baclab: 'say', text: String(text) }, '*'); };
  // Data the live page would fetch from the server (the admin monitor): the snapshot taken when the pages were captured
  var realFetch = window.fetch;
  window.fetch = function (url, options) {
    var path = String(url).split('?')[0].replace(/^https?:\/\/[^/]+/, '');
    var files = window.__demoFiles || {};
    if (files[path] !== undefined) return Promise.resolve(new Response(files[path], { status: 200, headers: { 'Content-Type': 'application/json' } }));
    return realFetch ? realFetch.apply(window, arguments) : Promise.reject(new Error('no network'));
  };
  window.open = function (href) { parent.postMessage({ baclab: 'go', href: String(href) }, '*'); return null; };
})();
