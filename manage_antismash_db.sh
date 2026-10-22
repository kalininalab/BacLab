#!/bin/bash
# Kept for old habits: the database installers are part of ./baclab now (see ./baclab db --help).
cd "$(dirname "${BASH_SOURCE[0]}")" && exec ./baclab db install antismash "$@"
