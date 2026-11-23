#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -f .env ]]; then
  set -a
  source ./.env
  set +a
fi
export TZ=Asia/Tokyo PYTHONUNBUFFERED=1 GIT_TERMINAL_PROMPT=0
python=.venv/bin/python

# Arguments are for local inspection. Only the no-argument cron run publishes.
if (( $# )); then
  exec "$python" -m pipeline.run "$@"
fi

exec 9>"${PIPELINE_LOCK_FILE:-/tmp/survey-app-daily.lock}"
if ! flock -n 9; then
  echo "Another daily run is active"
  exit 0
fi

if [[ "$(git branch --show-current)" != main || -n "$(git status --porcelain)" ]]; then
  echo "Daily publication requires a clean main checkout" >&2
  exit 1
fi

# First retry any previously committed results, then synchronize with main.
if [[ -n "$(git rev-list origin/main..HEAD)" ]]; then
  git push origin HEAD:main
fi
baseline="$(git rev-parse HEAD)"
git pull --ff-only origin main
if [[ "$baseline" != "$(git rev-parse HEAD)" ]]; then
  flock -u 9
  exec /bin/bash deploy/run-daily.sh
fi

artifact="$(mktemp -d)"
trap 'rm -r -- "$artifact"' EXIT
day="$(date +%F)"
for attempt in 1 2 3; do
  status=0
  if "$python" -c 'from pipeline.local_llm import LocalLLM; LocalLLM().check_article_model()'; then
    "$python" -m pipeline.run || status=$?

    # Persist successes before retrying so the next attempt only fills vacancies.
    "$python" -m pipeline.publish stage "$artifact/$attempt"
    "$python" -m pipeline.publish push "$artifact/$attempt"
  else
    status=2
  fi
  if (( status != 2 || attempt == 3 )); then
    exit "$status"
  fi
  echo "Daily target incomplete (attempt $attempt/3); retrying in 10 minutes"
  sleep 600
  [[ "$(date +%F)" == "$day" ]] || exit "$status"
done
