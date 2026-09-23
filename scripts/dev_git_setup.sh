#!/usr/bin/env bash
# One-time git setup for ONE teammate on the shared `hp18` login.
# Each person gets their own SSH key and their own working copy; commits and pushes are theirs.
#
#   scripts/dev_git_setup.sh <handle> "<Full Name>" <github-email>            # clone into ~/work/<handle>/herald-ems
#   scripts/dev_git_setup.sh <handle> "<Full Name>" <github-email> --here    # configure the repo you're standing in
#
# Nothing is set globally, so five people can share this login without signing as each other.
set -euo pipefail
H="${1:?handle}"; NAME="${2:?full name}"; EMAIL="${3:?github email}"; MODE="${4:-clone}"
REPO_SSH="git@github.com:projects-hacks/herald-ems.git"
KEY="$HOME/.ssh/id_ed25519_$H"
SSHCMD="ssh -i $KEY -o IdentitiesOnly=yes"

if [ ! -f "$KEY" ]; then
  ssh-keygen -t ed25519 -C "$EMAIL (zgx hp18)" -f "$KEY" -N ""
fi
echo
echo "1) Add this PUBLIC key to YOUR GitHub account: https://github.com/settings/ssh/new"
echo "   (title: zgx-hp18)"
echo
cat "$KEY.pub"
echo
[ -t 0 ] && read -rp "2) Press Enter after adding it... "
# `ssh -T git@github.com` always exits 1 (no shell access), so check its message, not its exit code.
AUTH_MSG="$(ssh -i "$KEY" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -T git@github.com 2>&1 || true)"
echo "$AUTH_MSG" | grep -qi "successfully authenticated" \
  || { echo "GitHub did not accept the key yet ($AUTH_MSG). Re-run after adding it."; exit 1; }
echo "$AUTH_MSG" | head -1

if [ "$MODE" = "--here" ]; then
  DIR="$(git rev-parse --show-toplevel)"
else
  DIR="$HOME/work/$H/herald-ems"
  mkdir -p "$(dirname "$DIR")"
  [ -d "$DIR/.git" ] || GIT_SSH_COMMAND="$SSHCMD" git clone "$REPO_SSH" "$DIR"
fi
cd "$DIR"
git remote set-url origin "$REPO_SSH"
git config core.sshCommand "$SSHCMD"     # repo-local: only this working copy uses this key
git config user.name "$NAME"
git config user.email "$EMAIL"
echo
echo "Done. $DIR commits as: $(git config user.name) <$(git config user.email)>, pushes with $KEY"
echo "Run your own server on your own port, e.g.: PORT=8101 scripts/run_dev.sh"
