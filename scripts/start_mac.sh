#!/usr/bin/env bash
# Start FinAlly. Usage: scripts/start_mac.sh [--build] [--open]
set -euo pipefail
cd "$(dirname "$0")/.."
NAME=finally; IMAGE=finally; VOLUME=finally-data
BUILD=0; OPEN=0
for a in "$@"; do case $a in --build) BUILD=1;; --open) OPEN=1;; esac; done

command -v docker >/dev/null 2>&1 || { echo "Docker is not installed or not on PATH."; exit 1; }
docker info >/dev/null 2>&1 || { echo "Docker isn't running. Start Docker Desktop (or the docker daemon), wait until the engine is up, then re-run."; exit 1; }
[ -f .env ] || { [ -f .env.example ] && cp .env.example .env && echo "Created .env from .env.example (edit it to add OPENROUTER_API_KEY)."; }

if [ $BUILD -eq 1 ] || ! docker image inspect $IMAGE >/dev/null 2>&1; then
  docker build -t $IMAGE .
fi
docker rm -f $NAME >/dev/null 2>&1 || true
docker run -d --name $NAME -v $VOLUME:/app/db -p 8000:8000 --env-file .env $IMAGE >/dev/null
URL=http://localhost:8000
echo "FinAlly running at $URL"
if [ $OPEN -eq 1 ]; then
  (command -v open >/dev/null && open $URL) || (command -v xdg-open >/dev/null && xdg-open $URL) || true
fi
