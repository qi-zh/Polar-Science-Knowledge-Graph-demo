#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/scripts/common.sh"
[[ $# == 0 ]] || fail 'Usage: ./stop_demo.sh'
require_engine
acquire_demo_lock exclusive
assert_demo_resources
compose down
printf '%s\n' 'Stopped this demo. Its dedicated graph volume and outputs were retained.'
