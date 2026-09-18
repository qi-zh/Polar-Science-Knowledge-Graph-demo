#!/usr/bin/env bash
# Shared helpers for this standalone demo, never for a production database.
set -euo pipefail

PSKG_DEMO_DIRECTORY="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly PSKG_DEMO_DIRECTORY
readonly PSKG_DEMO_PROJECT='pskg-paper-demo'
readonly PSKG_DEMO_VOLUME='pskg-paper-demo-data'
readonly PSKG_DEMO_NETWORK='pskg-paper-demo-network'
PSKG_DEMO_UID="$(id -u)"
PSKG_DEMO_GID="$(id -g)"
readonly PSKG_DEMO_UID PSKG_DEMO_GID
export PSKG_DEMO_DIRECTORY PSKG_DEMO_UID PSKG_DEMO_GID

fail() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

require_supported_environment() {
  local variable
  for variable in COMPOSE_FILE COMPOSE_PROJECT_NAME COMPOSE_PROFILES COMPOSE_ENV_FILES \
      DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS_VERIFY DOCKER_CERT_PATH; do
    if [[ -n "${!variable-}" ]]; then
      fail "Unset ${variable}; these scripts support only their fixed local demo configuration."
    fi
  done
  command -v docker >/dev/null 2>&1 || fail 'Docker is not installed.'
  docker compose version >/dev/null 2>&1 || fail 'Docker Compose v2 is required.'
  command -v flock >/dev/null 2>&1 || fail 'flock from Linux util-linux is required.'
  [[ "$PSKG_DEMO_UID" != 0 ]] || fail 'Run as a non-root user with Docker access, so generated files remain user-owned.'
}

acquire_demo_lock() {
  local mode="${1:-exclusive}" lock_file="$PSKG_DEMO_DIRECTORY/.demo.lock"
  [[ "$mode" == exclusive || "$mode" == shared ]] || fail 'Invalid demo lock mode.'
  [[ ! -L "$lock_file" ]] || fail 'The demo lock path must not be a symbolic link.'
  [[ ! -e "$lock_file" || -f "$lock_file" ]] || fail 'The demo lock path must be a regular file.'
  # Keep the descriptor open until this shell exits. Never delete the lock file:
  # replacing its inode could allow two commands to acquire different locks.
  exec {PSKG_DEMO_LOCK_FD}>>"$lock_file" || fail 'Cannot open the demo lock file.'
  flock "--$mode" --nonblock "$PSKG_DEMO_LOCK_FD" \
    || fail 'Another demo command is active. Close query sessions or wait for it to finish, then retry.'
}

compose() {
  docker compose --env-file /dev/null --project-name "$PSKG_DEMO_PROJECT" \
    --project-directory "$PSKG_DEMO_DIRECTORY" \
    --file "$PSKG_DEMO_DIRECTORY/compose.yaml" "$@"
}

require_engine() {
  local endpoint
  endpoint="$(docker context inspect --format '{{.Endpoints.docker.Host}}')" \
    || fail 'Unable to inspect the selected Docker context.'
  [[ "$endpoint" == unix://* ]] || fail 'Only a local Unix-socket Docker context is supported.'
  docker info --format '{{.ID}}' >/dev/null 2>&1 \
    || fail 'Docker is unavailable to this user. Ask the host administrator for access; these scripts do not change permissions or start Docker.'
}

assert_owned_resource() {
  local kind="$1" identifier="$2" labels
  local label_template='{{index .Labels "org.pskg.paper-demo.managed"}}|{{index .Labels "org.pskg.paper-demo.owner"}}|{{index .Labels "org.pskg.paper-demo.directory"}}|{{index .Labels "com.docker.compose.project"}}'
  if [[ "$kind" == container ]]; then
    label_template='{{index .Config.Labels "org.pskg.paper-demo.managed"}}|{{index .Config.Labels "org.pskg.paper-demo.owner"}}|{{index .Config.Labels "org.pskg.paper-demo.directory"}}|{{index .Config.Labels "com.docker.compose.project"}}'
  fi
  labels="$(docker "$kind" inspect --format "$label_template" "$identifier")" \
    || fail "Cannot inspect ${kind} ${identifier}; no changes were made by this check."
  [[ "$labels" == "true|$PSKG_DEMO_PROJECT|$PSKG_DEMO_DIRECTORY|$PSKG_DEMO_PROJECT" ]] \
    || fail "Refusing to touch ${kind} ${identifier}: ownership labels do not match this demo directory."
}

assert_demo_resources() {
  local containers identifier
  containers="$(docker container ls --all --quiet --filter "label=com.docker.compose.project=$PSKG_DEMO_PROJECT")" \
    || fail 'Cannot list containers belonging to the demo project.'
  while IFS= read -r identifier; do
    [[ -z "$identifier" ]] || assert_owned_resource container "$identifier"
  done <<< "$containers"
  if docker volume inspect "$PSKG_DEMO_VOLUME" >/dev/null 2>&1; then
    assert_owned_resource volume "$PSKG_DEMO_VOLUME"
  fi
  if docker network inspect "$PSKG_DEMO_NETWORK" >/dev/null 2>&1; then
    assert_owned_resource network "$PSKG_DEMO_NETWORK"
  fi
}

require_supported_environment
