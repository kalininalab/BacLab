#!/bin/bash
# Installs BacLab on a fresh machine and updates an existing installation. Same as ./baclab install / ./baclab update.
# Updating never touches your data (data/, databases/, backups/, the database volumes); see README.md.
cd "$(dirname "${BASH_SOURCE[0]}")" || exit 1
if [ -f .baclab ]; then
    exec ./baclab update "$@"
else
    exec ./baclab install "$@"
fi
