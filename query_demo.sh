#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/scripts/common.sh"
[[ $# -le 1 ]] || fail 'Usage: ./query_demo.sh ["CYPHER QUERY"]'
require_engine
acquire_demo_lock shared
assert_demo_resources
if [[ $# == 1 ]]; then
  compose exec -T neo4j cypher-shell -u neo4j -p demo-only-password -d neo4j "$1"
else
  printf '%s\n' 'Opening the dedicated demo database. Use :exit to leave cypher-shell.'
  compose exec neo4j cypher-shell -u neo4j -p demo-only-password -d neo4j
fi
