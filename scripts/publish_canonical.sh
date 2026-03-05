#!/usr/bin/env bash
set -euo pipefail

OWNER="shakti-saraswati"
REPO="dharma_swarm"
REPO_FULL="${OWNER}/${REPO}"
REPO_URL="https://github.com/${REPO_FULL}.git"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "${ROOT_DIR}"

if ! command -v gh >/dev/null 2>&1; then
  echo "ERROR: GitHub CLI (gh) is not installed."
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo "ERROR: git is not installed."
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  cat <<'EOF'
ERROR: GitHub auth is not valid in this shell.
Run:
  env -u GITHUB_TOKEN -u GH_TOKEN gh auth login --hostname github.com --git-protocol https --web
EOF
  exit 1
fi

AUTH_STATUS="$(gh auth status 2>&1 || true)"
if ! printf "%s" "${AUTH_STATUS}" | grep -q "account ${OWNER}"; then
  echo "WARNING: Active gh account is not ${OWNER}."
  echo "Current auth status:"
  echo "${AUTH_STATUS}"
fi

if gh repo view "${REPO_FULL}" >/dev/null 2>&1; then
  echo "Repo exists: ${REPO_FULL}"
else
  echo "Creating private repo: ${REPO_FULL}"
  gh repo create "${REPO_FULL}" --private --description "Canonical dharma_swarm runtime repository"
fi

if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "${REPO_URL}"
else
  git remote add origin "${REPO_URL}"
fi

echo "Pushing main to origin..."
git push -u origin main
echo "Done: ${REPO_URL}"
