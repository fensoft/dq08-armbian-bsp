#!/usr/bin/env bash
# Open one deduplicated automation issue, or append the latest run to it.
set -euo pipefail

if (($# != 4)); then
	printf 'Usage: %s KEY TITLE LABEL BODY_FILE\n' "$0" >&2
	exit 2
fi
: "${GH_TOKEN:?GH_TOKEN is required}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"

key="$1"
title="$2"
label="$3"
body_file="$4"
[[ "${key}" =~ ^[a-z0-9._:-]+$ && "${label}" =~ ^[a-z0-9._-]+$ ]] || {
	printf 'Unsafe issue key or label.\n' >&2
	exit 2
}
[[ -f "${body_file}" ]] || { printf 'Missing issue body: %s\n' "${body_file}" >&2; exit 2; }

marker="<!-- dq08-automation:${key} -->"
body="${marker}"$'\n'"$(<"${body_file}")"

if ! gh api "repos/${GITHUB_REPOSITORY}/labels/${label}" >/dev/null 2>&1; then
	gh api --method POST "repos/${GITHUB_REPOSITORY}/labels" \
		-f name="${label}" -f color="B60205" \
		-f description="Created by the DQ08 release pipeline" >/dev/null
fi

issue_number="$(
	gh api --paginate --slurp "repos/${GITHUB_REPOSITORY}/issues?state=open&per_page=100" |
		jq -r --arg marker "${marker}" \
			'add | map(select(.pull_request == null and ((.body // "") | contains($marker)))) | first | .number // empty'
)"

if [[ -n "${issue_number}" ]]; then
	jq -n --arg body "${body}" '{body: $body}' |
		gh api --method POST "repos/${GITHUB_REPOSITORY}/issues/${issue_number}/comments" --input - >/dev/null
	printf 'Updated issue #%s for %s.\n' "${issue_number}" "${key}"
else
	jq -n --arg title "${title}" --arg body "${body}" --arg label "${label}" \
		'{title: $title, body: $body, labels: [$label]}' |
		gh api --method POST "repos/${GITHUB_REPOSITORY}/issues" --input - >/dev/null
	printf 'Opened issue for %s.\n' "${key}"
fi
