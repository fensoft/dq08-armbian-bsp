#!/usr/bin/env bash
# Download the assets described by one trusted GitHub release API response.
set -euo pipefail

if (($# != 2)); then
	printf 'Usage: %s RELEASE_JSON DESTINATION\n' "$0" >&2
	exit 2
fi
: "${GH_TOKEN:?GH_TOKEN is required}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"

release_json="$1"
destination="$2"
[[ -f "${release_json}" && ! -L "${release_json}" ]] || {
	printf 'Release JSON is not a regular file: %s\n' "${release_json}" >&2
	exit 2
}
[[ ! -L "${destination}" ]] || {
	printf 'Destination must not be a symlink: %s\n' "${destination}" >&2
	exit 2
}
install -d -m 0700 "${destination}"
if find "${destination}" -mindepth 1 -maxdepth 1 -print -quit | grep -q .; then
	printf 'Destination is not empty: %s\n' "${destination}" >&2
	exit 2
fi

if ! jq -e '
  (.assets | type == "array") and
  (.assets | length <= 4) and
  ([.assets[].name] | length == (unique | length)) and
  all(.assets[];
    (.id | type == "number") and
    (.id | floor == .) and
    (.id > 0) and
    (.name | type == "string") and
    (.name | test("^[A-Za-z0-9][A-Za-z0-9._+-]*$")) and
    (.state == "uploaded") and
    (.size | type == "number") and
    (.size | floor == .) and
    (.size > 0) and
    (if (.name | endswith(".img.xz")) then
       .size < 2147483648
     else
       .size < 16777216
     end))
' "${release_json}" >/dev/null; then
	printf 'Release JSON contains an unsafe or malformed asset list.\n' >&2
	exit 2
fi

while IFS=$'\t' read -r asset_id asset_name expected_size; do
	temporary="${destination}/.${asset_name}.part"
	downloaded=false
	for attempt in 1 2 3; do
		if gh api --method GET -H 'Accept: application/octet-stream' \
			"repos/${GITHUB_REPOSITORY}/releases/assets/${asset_id}" > "${temporary}"; then
			downloaded=true
			break
		fi
		((attempt == 3)) || sleep $((attempt * 5))
	done
	[[ "${downloaded}" == true ]]
	[[ "$(stat -c %s "${temporary}")" == "${expected_size}" ]]
	mv "${temporary}" "${destination}/${asset_name}"
done < <(jq -r '.assets[] | [.id, .name, .size] | @tsv' "${release_json}")

printf 'Downloaded %s release asset(s) into %s.\n' \
	"$(jq -r '.assets | length' "${release_json}")" "${destination}"
