#!/bin/bash
set -e

echo "Running post-install configurations for all tools for the monolithic image"

if [ -f "/app/tools/cblaster/configure_cblaster.sh" ]; then
    echo "Configuring cblaster..."
    bash /app/tools/cblaster/configure_cblaster.sh < /dev/null
fi

# NOTE: reference databases for amrfinderplus, checkm2, mobsuite, and kraken2
# are NOT downloaded at image-build time (consistent with bakta/antiSMASH/
# GTDB-Tk/cblaster/PlasmidFinder) - they are fetched on demand, after the
# containers are up, via manage_amrfinderplus_db.sh / manage_checkm2_db.sh /
# manage_mobsuite_db.sh / manage_kraken2_db.sh (invoked from update.sh).
