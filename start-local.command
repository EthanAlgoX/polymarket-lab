#!/bin/zsh
set -eu
cd "$(dirname "$0")"
if [[ "${PM_SHELL_ENV_LOADED:-0}" != "1" && -z "${DEEPSEEK_API_KEY:-}${DEEPSEEK_KEY:-}${PMS_DEEPSEEK_API_KEY:-}" ]]; then
  export PM_SHELL_ENV_LOADED=1
  exec /bin/zsh -ilc 'exec "$1"' polymarket-env "$PWD/start-local.command"
fi
PM_RUNTIME="$PWD/.venv/bin/python"
if [[ ! -x "$PM_RUNTIME" ]]; then
  if [[ -z "${PM_PYTHON:-}" ]]; then
    for PM_CANDIDATE in python3.12 python3.13 python3.11 python3; do
      if command -v "$PM_CANDIDATE" >/dev/null 2>&1 && "$PM_CANDIDATE" -c 'import sys; sys.exit(sys.version_info < (3, 11))' >/dev/null 2>&1; then
        PM_PYTHON="$PM_CANDIDATE"
        break
      fi
    done
  fi
  if [[ -z "${PM_PYTHON:-}" ]] || ! "$PM_PYTHON" -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
    print -u2 '需要 Python >=3.11。安装后重试，或通过 PM_PYTHON 指定解释器。'
    exit 1
  fi
  "$PM_PYTHON" -m venv .venv
  PM_REQUIREMENTS="requirements.txt"
  if [[ -f requirements-lock.txt ]]; then
    PM_REQUIREMENTS="requirements-lock.txt"
  fi
  "$PM_RUNTIME" -m pip install -r "$PM_REQUIREMENTS"
fi
exec "$PM_RUNTIME" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
