#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [ -f "${PROJECT_ROOT}/.env" ]; then
  set -a
  . "${PROJECT_ROOT}/.env"
  set +a
fi

: "${TELEOP_ROBOT_PORT:=5175}"
: "${TELEOP_CONDA_ENV:=teleop}"
: "${TELEOP_BACKEND_START_DELAY:=5}"

PIDS="$(lsof -ti:"${TELEOP_ROBOT_PORT}" || true)"
if [ -n "${PIDS}" ]; then
  kill ${PIDS}
fi

tmux new-session -d -s pc
tmux send-keys -t pc "cd ${PROJECT_ROOT}/frontend; npm run dev" C-m
tmux split-window -v
tmux send-keys -t pc "cd ${PROJECT_ROOT}/backend; conda activate ${TELEOP_CONDA_ENV}; while ! lsof -ti:${TELEOP_ROBOT_PORT}; do sleep 1; done; sleep ${TELEOP_BACKEND_START_DELAY}; python control.py" C-m
tmux attach-session -t pc
