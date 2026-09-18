#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/scripts/common.sh"
[[ $# == 0 ]] || fail 'Usage: ./run_demo.sh'
require_engine
acquire_demo_lock exclusive
assert_demo_resources
mkdir -p -- "$PSKG_DEMO_DIRECTORY/outputs"
[[ -w "$PSKG_DEMO_DIRECTORY/outputs" ]] || fail 'The demo outputs directory must be writable by the current user.'

printf '%s\n' 'Building the standalone demonstration image...'
compose build app
printf '%s\n' 'Starting the dedicated demo Neo4j and waiting for readiness...'
compose up --detach --wait --wait-timeout 180 neo4j
printf '%s\n' 'Preparing and importing the Figure 3 example...'
compose run --rm --no-deps -T app build --import-neo4j
printf '%s\n' 'Done. Use ./query_demo.sh to inspect the graph, or ./stop_demo.sh to stop this demo without deleting its graph.'
