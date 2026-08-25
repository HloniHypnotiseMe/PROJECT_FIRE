#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Push PROJECT FIRE to GitHub.
#
# Run from the PROJECT_FIRE root on the machine that owns the GitHub account.
# Requires EITHER the GitHub CLI (`gh`) with auth, OR a Personal Access Token.
# This sandbox has neither, so the script detects and explains exactly what
# is missing instead of failing silently.
# ---------------------------------------------------------------------------
set -euo pipefail

REPO_NAME="PROJECT_FIRE"
GH_USER="HloniHypnotiseMe"

echo "==[1/4] Preflight =="
if command -v gh >/dev/null 2>&1; then
  if gh auth status >/dev/null 2>&1; then
    echo "  gh CLI present and authenticated."
    MODE="gh"
  else
    echo "  gh CLI present but NOT authenticated -> run: gh auth login"
    echo "  (or provide a GITHUB_TOKEN below)"
    MODE="token"
  fi
elif [ -n "${GITHUB_TOKEN:-}" ] || [ -n "${GH_TOKEN:-}" ]; then
  echo "  No gh CLI, but a token env var is set."
  MODE="token"
else
  echo "  NO gh CLI and NO GITHUB_TOKEN/GH_TOKEN found."
  echo "  -> Do one of:"
  echo "       1) install GitHub CLI and run: gh auth login"
  echo "       2) create a PAT at https://github.com/settings/tokens"
  echo "          (scope: repo) and export GITHUB_TOKEN=ghp_xxx"
  echo "  Nothing was pushed. The repo is fully ready to push once auth exists."
  exit 1
fi

echo "==[2/4] Create remote repository =="
if [ "$MODE" = "gh" ]; then
  gh repo create "$GH_USER/$REPO_NAME" --public --source=. --remote=origin --push \
    --description "PROJECT FIRE - AI business operating system" 2>/dev/null \
    || echo "  (repo may already exist; will push below)"
else
  echo "  (creating via API requires curl + token; skipping automatic create)"
fi

echo "==[3/4] Commit (if anything is uncommitted) =="
git add -A
if git diff --cached --quiet; then
  echo "  nothing to commit."
else
  git commit -m "FIRE v0.1.0: registry, kernel, opportunity engine, reality gate, memory, revenue, control room" || true
fi

echo "==[4/4] Push =="
if [ "$MODE" = "gh" ]; then
  git push -u origin main || git push -u origin master
else
  git remote remove origin 2>/dev/null || true
  git remote add origin "https://x-access-token:${GITHUB_TOKEN:-${GH_TOKEN}}@github.com/$GH_USER/$REPO_NAME.git"
  git push -u origin HEAD:main || git push -u origin HEAD:master
  git remote set-url origin "https://github.com/$GH_USER/$REPO_NAME.git"
fi

echo "Done -> https://github.com/$GH_USER/$REPO_NAME"
