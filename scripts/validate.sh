#!/usr/bin/env bash
# Run every offline check available on this machine. Missing tools are reported, not faked.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STATUS=0
run() { echo; echo "== $1"; shift; if "$@"; then echo "-> OK"; else echo "-> FAILED"; STATUS=1; fi; }
have() { command -v "$1" >/dev/null 2>&1; }

cd "$ROOT/backend"
if have pytest; then run "backend unit tests" pytest -o addopts=""; else echo "!! pytest missing (pip install -r backend/requirements-dev.txt)"; STATUS=1; fi
have ruff && run "ruff lint" ruff check src local tests && run "ruff format" ruff format --check src local tests
have mypy && run "mypy" mypy src/order_system

cd "$ROOT"
run "terraform static check" python3 scripts/tf_static_check.py
if have terraform; then
  cd "$ROOT/terraform"
  run "terraform fmt" terraform fmt -check -recursive
  run "terraform init (no backend)" terraform init -backend=false -input=false
  run "terraform validate" terraform validate
  cd "$ROOT"
else
  echo "!! terraform not installed: terraform fmt/validate NOT run"
fi

if have npm && [[ -d "$ROOT/frontend/node_modules" ]]; then
  cd "$ROOT/frontend"
  run "frontend typecheck" npm run --silent typecheck
  run "frontend tests" npm test --silent
  run "frontend build" npm run --silent build
else
  echo "!! frontend dependencies not installed (cd frontend && npm install): frontend checks NOT run"
fi
echo
[[ $STATUS -eq 0 ]] && echo "All available checks passed." || echo "Some checks failed or were skipped."
exit $STATUS
