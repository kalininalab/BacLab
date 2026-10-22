function initMultiFileUpload(options) {
    var input = document.getElementById(options.inputId);
    var container = document.getElementById(options.listId);
    var extensions = (options.extensions || []).map(function (ext) { return ext.toLowerCase(); });
    var minFiles = options.minFiles || 0;
    var maxFiles = options.maxFiles || Infinity;
    var store = new DataTransfer();

    function hasAllowedExtension(file) {
        var name = file.name.toLowerCase();
        return !extensions.length || extensions.some(function (ext) { return name.endsWith(ext); });
    }

    function formatSize(bytes) {
        if (bytes >= 1e6) { return (bytes / 1e6).toFixed(1) + ' MB'; }
        if (bytes >= 1e3) { return Math.round(bytes / 1e3) + ' kB'; }
        return bytes + ' B';
    }

    function element(tag, className, text) {
        var node = document.createElement(tag);
        if (className) { node.className = className; }
        if (text !== undefined) { node.textContent = text; }  // textContent: file names are user-controlled
        return node;
    }

    function sync() {
        input.files = store.files;
        render();
    }

    function removeAt(index) {
        store.items.remove(index);
        sync();
    }

    function clearAll() {
        store.items.clear();
        sync();
    }

    function render(notice) {
        container.textContent = '';
        var count = store.files.length;
        if (count) {
            var table = element('table', 'multi-file-table');
            var headRow = element('tr');
            ['File', 'Size', ''].forEach(function (title, column) {
                var cell = element('th', column === 1 ? 'multi-file-size' : '', title);
                headRow.appendChild(cell);
            });
            table.appendChild(element('thead')).appendChild(headRow);

            var body = element('tbody');
            Array.from(store.files).forEach(function (file, index) {
                var row = element('tr');
                var nameCell = element('td', 'multi-file-name', file.name);
                nameCell.title = file.name;  // full name on hover when it is truncated
                row.appendChild(nameCell);
                row.appendChild(element('td', 'multi-file-size', formatSize(file.size)));
                var actionCell = element('td', 'multi-file-action');
                var remove = element('button', 'btn btn-small multi-file-remove', 'Remove');
                remove.type = 'button';
                remove.title = 'Remove ' + file.name;
                remove.addEventListener('click', function () { removeAt(index); });
                actionCell.appendChild(remove);
                row.appendChild(actionCell);
                body.appendChild(row);
            });
            table.appendChild(body);

            // Footer row: how many files, and "Remove all" in the same column as the Remove buttons
            var text = count + (count === 1 ? ' file' : ' files') + ' selected';
            if (count < minFiles) {
                text += ' \u2013 add at least ' + (minFiles - count) + ' more';
            }
            var footRow = element('tr');
            var countCell = element('td', 'multi-file-count', text);
            countCell.colSpan = 2;
            footRow.appendChild(countCell);
            var clearCell = element('td', 'multi-file-action');
            if (count > 1) {
                var clear = element('button', 'btn btn-small multi-file-clear', 'Remove all');
                clear.type = 'button';
                clear.addEventListener('click', clearAll);
                clearCell.appendChild(clear);
            }
            footRow.appendChild(clearCell);
            table.appendChild(element('tfoot')).appendChild(footRow);
            container.appendChild(table);
        }
        if (notice) {
            container.appendChild(element('div', 'multi-file-notice', notice));
        }
    }

    input.addEventListener('change', function () {
        var known = {};
        Array.from(store.files).forEach(function (file) { known[file.name] = true; });
        var wrongType = [], duplicates = [], tooMany = [];

        // input.files now holds only what was just picked; everything earlier lives in `store`
        Array.from(input.files).forEach(function (file) {
            if (!hasAllowedExtension(file)) {
                wrongType.push(file.name);
            } else if (known[file.name]) {
                duplicates.push(file.name);
            } else if (store.files.length >= maxFiles) {
                tooMany.push(file.name);
            } else {
                known[file.name] = true;
                store.items.add(file);
            }
        });

        var notices = [];
        if (wrongType.length) {
            notices.push('Not added (allowed: ' + extensions.join(', ') + '): ' + wrongType.join(', '));
        }
        if (duplicates.length) {
            notices.push('Already added (a file with this name is in the list): ' + duplicates.join(', '));
        }
        if (tooMany.length) {
            notices.push('Not added (limit of ' + maxFiles + ' files reached): ' + tooMany.join(', '));
        }
        input.files = store.files;
        render(notices.join(' • '));
    });

    render();
}
