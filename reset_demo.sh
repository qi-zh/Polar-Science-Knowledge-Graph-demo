#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/scripts/common.sh"
if [[ $# != 1 || "$1" != --confirm ]]; then
  printf '%s\n' 'This stops the demo and permanently deletes ONLY its labelled graph volume.' \
    'Generated CSV files under outputs/ are retained.' \
    'Usage: ./reset_demo.sh --confirm' >&2
  exit 2
fi
require_engine
acquire_demo_lock exclusive
assert_demo_resources
if ! docker volume inspect "$PSKG_DEMO_VOLUME" >/dev/null 2>&1; then
  printf '%s\n' 'No demo graph volume exists. Nothing was deleted.'
  exit 0
fi
assert_owned_resource volume "$PSKG_DEMO_VOLUME"
compose down
# Check the exact target again immediately before the destructive operation.
assert_owned_resource volume "$PSKG_DEMO_VOLUME"
docker volume rm "$PSKG_DEMO_VOLUME"
printf '%s\n' 'Deleted the dedicated demo graph volume. This deletion is not reversible.' \
  'Generated CSV outputs remain available. ./run_demo.sh rebuilds the supplied sample graph.'
