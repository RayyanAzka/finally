#!/usr/bin/env bash
# Stop and remove the container; the finally-data volume is kept.
command -v docker >/dev/null 2>&1 || { echo "Docker is not installed or not on PATH."; exit 1; }
docker info >/dev/null 2>&1 || { echo "Docker isn't running. Start Docker Desktop (or the docker daemon), wait until the engine is up, then re-run."; exit 1; }
docker rm -f finally >/dev/null 2>&1 || true
echo "FinAlly stopped (volume finally-data preserved)."
