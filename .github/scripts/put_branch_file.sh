#!/usr/bin/env bash
# Create/update one file on a dedicated state branch through the GitHub API.
set -euo pipefail

if (($# != 4)); then
	printf 'Usage: %s BRANCH REPOSITORY_PATH LOCAL_FILE COMMIT_MESSAGE\n' "$0" >&2
	exit 2
fi
: "${GH_TOKEN:?GH_TOKEN is required}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"

branch="$1"
repository_path="$2"
local_file="$3"
message="$4"

[[ -f "${local_file}" ]] || { printf 'Missing local file: %s\n' "${local_file}" >&2; exit 2; }
[[ "${branch}" =~ ^[A-Za-z0-9._/-]+$ && "${repository_path}" != /* && "${repository_path}" != *..* ]] || {
	printf 'Unsafe branch or repository path.\n' >&2
	exit 2
}

if ! gh api "repos/${GITHUB_REPOSITORY}/git/ref/heads/${branch}" >/dev/null 2>&1; then
	default_branch="$(gh api "repos/${GITHUB_REPOSITORY}" --jq .default_branch)"
	base_sha="$(gh api "repos/${GITHUB_REPOSITORY}/git/ref/heads/${default_branch}" --jq .object.sha)"
	gh api --method POST "repos/${GITHUB_REPOSITORY}/git/refs" \
		-f ref="refs/heads/${branch}" \
		-f sha="${base_sha}" >/dev/null
fi

existing_sha="$(gh api "repos/${GITHUB_REPOSITORY}/contents/${repository_path}?ref=${branch}" --jq .sha 2>/dev/null || true)"
local_blob_sha="$(git hash-object "${local_file}")"
if [[ -n "${existing_sha}" && "${existing_sha}" == "${local_blob_sha}" ]]; then
	printf '%s on %s is already current.\n' "${repository_path}" "${branch}"
	exit 0
fi
content="$(base64 -w 0 "${local_file}")"
declare -a api_args=(
	--method PUT
	"repos/${GITHUB_REPOSITORY}/contents/${repository_path}"
	-f message="${message}"
	-f content="${content}"
	-f branch="${branch}"
)
if [[ -n "${existing_sha}" ]]; then
	api_args+=(-f sha="${existing_sha}")
fi
gh api "${api_args[@]}" >/dev/null
printf 'Updated %s on %s.\n' "${repository_path}" "${branch}"
