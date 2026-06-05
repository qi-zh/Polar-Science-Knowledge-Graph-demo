#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_DIR=$(cd -- "${SCRIPT_DIR}/.." && pwd)

if [ -f "${PROJECT_DIR}/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "${PROJECT_DIR}/.env"
  set +a
fi

PASSWORD="${NEO4J_PASSWORD:-demo-password}"

cd "${PROJECT_DIR}"

if [ "$#" -gt 0 ]; then
  docker compose exec -T neo4j cypher-shell -u neo4j -p "${PASSWORD}" "$@"
else
  docker compose exec neo4j cypher-shell -u neo4j -p "${PASSWORD}"
fi
