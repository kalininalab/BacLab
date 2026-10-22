(function () {
    function attachPreview(row) {
        var textarea = row.querySelector('textarea');
        var previewEl = row.querySelector('.section-live-preview');
        if (!textarea || !previewEl) return;

        function waitForEditor(attemptsLeft) {
            var instance = window.CKEDITOR && window.CKEDITOR.instances[textarea.id];
            if (!instance) {
                if (attemptsLeft > 0) setTimeout(function () { waitForEditor(attemptsLeft - 1); }, 300);
                return;
            }
            var update = function () { previewEl.innerHTML = instance.getData(); };
            if (instance.status === 'ready') {
                update();
            } else {
                instance.on('instanceReady', update);
            }
            instance.on('change', update);
        }
        waitForEditor(30);
    }

    function attachAll() {
        document.querySelectorAll('.inline-related').forEach(attachPreview);
    }

    document.addEventListener('DOMContentLoaded', attachAll);

    if (window.django && window.django.jQuery) {
        window.django.jQuery(document).on('formset:added', function (event, row) {
            var el = row && row[0] ? row[0] : row;
            if (el) setTimeout(function () { attachPreview(el); }, 300);
        });
    }
})();
