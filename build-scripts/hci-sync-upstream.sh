#!/usr/bin/env bash
# Propose upstream changes without overwriting fork-owned HCI configuration.
set -euo pipefail

: "${SYNC_BASE_BRANCH:=main}"
: "${SYNC_DRY_RUN:=0}"
: "${GH_REPO:=highwaytoit/zirconium-hci}"
upstream_url='https://github.com/zirconium-dev/zirconium.git'

git remote get-url upstream >/dev/null 2>&1 || git remote add upstream "$upstream_url"
git fetch origin "+refs/heads/${SYNC_BASE_BRANCH}:refs/remotes/origin/${SYNC_BASE_BRANCH}"
git fetch upstream '+refs/heads/main:refs/remotes/upstream/main'
base_ref="refs/remotes/origin/${SYNC_BASE_BRANCH}"
upstream_sha=$(git rev-parse refs/remotes/upstream/main)

last_synced=''
if marker=$(git show "${base_ref}:.github/upstream-sync.sha" 2>/dev/null); then
  if [[ "$marker" =~ ^[0-9a-fA-F]{40}$ ]] &&
      git cat-file -e "${marker}^{commit}" 2>/dev/null &&
      git merge-base --is-ancestor "$marker" "$upstream_sha"; then
    last_synced=$(git rev-parse "${marker}^{commit}")
  else
    echo 'Invalid or stale upstream marker; using common merge base.'
  fi
fi
if [ -z "$last_synced" ]; then
  last_synced=$(git merge-base "$base_ref" refs/remotes/upstream/main)
fi

# Do not read or touch the shared production sync branch during dry runs.
previous_branch_sha=''
if [ "$SYNC_DRY_RUN" != 1 ]; then
  if [ "$SYNC_BASE_BRANCH" != main ]; then
    echo '::error::Publishing upstream sync is allowed only from main.' >&2
    exit 1
  fi
  previous_branch_sha=$(git ls-remote --heads origin refs/heads/upstream-sync | cut -f1)
fi

git switch --force-create upstream-sync "$base_ref"

if [ "$last_synced" != "$upstream_sha" ]; then
  patch_file=$(mktemp "${RUNNER_TEMP:-/tmp}/hci-upstream-patch.XXXXXX")
  trap 'rm -f "$patch_file"' EXIT

  # HCI owns CI, signing identity and custom configurations; upstream owns
  # other source files. Never copy upstream signing keys or CI automation.
  git diff --binary --full-index --no-renames "$last_synced" "$upstream_sha" -- . \
    ':(top,exclude)README.md' \
    ':(top,glob,exclude).github/**' \
    ':(top,exclude)renovate.json' \
    ':(top,exclude)cosign.pub' \
    ':(top,glob,exclude)build-scripts/hci-*' \
    ':(top,glob,exclude)**/hci-*.conf' \
    ':(top,glob,exclude)**/99-hci*.conf' > "$patch_file"

  if [ -s "$patch_file" ]; then
    if ! git apply --3way --index "$patch_file"; then
      # Handle only strictly identical mkosi documents whose ONLY
      # divergent data is a Packages= list. Anything else is unsafe.
      if ! python3 build-scripts/hci-merge-packages.py; then
        echo '::error::Upstream contains a genuine HCI conflict. No push or PR was performed.' >&2
        exit 1
      fi
    fi
  fi
  mkdir -p .github
  printf '%s\n' "$upstream_sha" > .github/upstream-sync.sha
  git add -- .github/upstream-sync.sha
fi

# Preserve existing submodule update policy, matching configured branches.
for path in assets mkosi.extra/usr/share/zirconium/zdots; do
  url=$(git config -f .gitmodules --get "submodule.$path.url")
  branch=$(git config -f .gitmodules --get "submodule.$path.branch" || :)
  ref=HEAD
  if [ -n "$branch" ]; then
    ref="refs/heads/$branch"
  fi
  remote_ref=$(git ls-remote --exit-code "$url" "$ref")
  read -r sha resolved_ref <<< "$remote_ref"
  if [[ ! "$sha" =~ ^[0-9a-f]{40}$ ]] || [ "$resolved_ref" != "$ref" ]; then
    echo "::error::Could not resolve submodule $path at $ref." >&2
    exit 1
  fi
  entry=$(git ls-files --stage -- "$path")
  read -r mode old_sha stage entry_path <<< "$entry"
  if [ "$mode" != 160000 ] || [ "$stage" != 0 ]; then
    echo "::error::Expected an existing, unconflicted gitlink at $path." >&2
    exit 1
  fi
  if [ "$old_sha" != "$sha" ]; then
    git update-index --cacheinfo 160000 "$sha" "$path"
  fi
done

if [ -n "$(git ls-files -u)" ]; then
  echo '::error::Unresolved Git conflicts remain; stopping.' >&2
  exit 1
fi
git diff --cached --check
git diff --cached --stat
if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  {
    echo '## Zirconium HCI upstream synchronization'
    echo "- Source: zirconium-dev/zirconium"
    echo "- Accepted upstream: $last_synced"
    echo "- Proposed upstream: $upstream_sha"
    echo "- Base branch: $SYNC_BASE_BRANCH"
    echo "- Dry run: $SYNC_DRY_RUN"
    echo '### Staged changes'
    echo '```'
    git diff --cached --stat
    echo '```'
  } >> "$GITHUB_STEP_SUMMARY"
fi
if git diff --cached --quiet; then
  echo 'No upstream or submodule changes.'
  exit 0
fi
if [ "$SYNC_DRY_RUN" = 1 ]; then
  echo 'DRY RUN SUCCESS: clean staged upstream sync; no commit, push or PR.'
  exit 0
fi

git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git commit -m 'chore: sync Zirconium upstream and submodules'
git push --force-with-lease="refs/heads/upstream-sync:$previous_branch_sha" \
  origin refs/heads/upstream-sync:refs/heads/upstream-sync

body_file=$(mktemp "${RUNNER_TEMP:-/tmp}/hci-upstream-body.XXXXXX")
trap 'rm -f "$patch_file" "$body_file"' EXIT
cat > "$body_file" <<EOF
Source: zirconium-dev/zirconium:main
Previous accepted upstream SHA: $last_synced
Proposed upstream SHA: $upstream_sha

HCI-owned and excluded: .github/, README.md, renovate.json,
cosign.pub (fork signing identity), build-scripts/hci-*, and hci-*/99-hci*
mkosi configuration snippets. See docs/HCI-UPSTREAM-SYNC.md.

Package-only text conflicts may be combined automatically with local additions
and removals preserved. All non-package conflicts stop for manual review.
This same PR may contain assets/zdots submodule updates.

This PR is NOT auto-merged. Merging into main triggers the HCI image build.
EOF
existing_pr=$(gh pr list --state open --base main --head upstream-sync \
  --json number --jq '.[0].number // empty')
if [ -n "$existing_pr" ]; then
  gh pr edit "$existing_pr" --body-file "$body_file"
else
  gh pr create --base main --head upstream-sync \
    --title 'chore: sync Zirconium upstream' --body-file "$body_file"
fi