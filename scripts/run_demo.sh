#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_DIR=$(cd -- "${SCRIPT_DIR}/.." && pwd)

cd "${PROJECT_DIR}"

echo "Starting Neo4j inside Docker..."
docker compose up -d neo4j

echo "Building demo application image..."
docker compose build app

echo "Running the KG public demo pipeline..."
docker compose run --rm app python main.py --mode frozen --reset-db

echo
echo "Demo run complete."
echo "Query Neo4j with: ./scripts/query_neo4j.sh"
echo "Stop containers with: ./scripts/stop_demo.sh"
