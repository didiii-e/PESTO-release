#!/usr/bin/env bash
# Fetch the data archives deposited on Zenodo and extract them into paper/.
# The archive is being renewed: RECORD and the checksums are filled in once the
# new version has its DOI, and until then the script stops with a message. Only the upstream scripts need them: every figure
# and table of the manuscript is redrawn from what the repository already holds.
#
#   bash paper/fetch_data.sh          both archives (about 105 MB)
#   bash paper/fetch_data.sh runs     the saved model answers only
#   bash paper/fetch_data.sh inputs   the upstream inputs only
set -euo pipefail

echo "The Zenodo archive of the paper is being renewed; its new DOI will be given in paper/README.md." >&2
exit 1

RECORD=""   # https://zenodo.org/records/<new record>/files
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(dirname "$HERE")"

declare -A MD5=(
  [pesto_paper_runs.tar.gz]=
  [pesto_paper_inputs.tar.gz]=
)

want=("pesto_paper_runs.tar.gz" "pesto_paper_inputs.tar.gz")
case "${1:-all}" in
  runs)   want=("pesto_paper_runs.tar.gz") ;;
  inputs) want=("pesto_paper_inputs.tar.gz") ;;
  all)    ;;
  *) echo "usage: $0 [runs|inputs|all]" >&2; exit 2 ;;
esac

mkdir -p "$HERE/downloads"
for name in "${want[@]}"; do
  out="$HERE/downloads/$name"
  if [ ! -f "$out" ]; then
    echo "downloading $name"
    curl -L --fail -o "$out" "$RECORD/$name?download=1"
  fi
  got=$(md5sum "$out" | cut -d' ' -f1)
  if [ "$got" != "${MD5[$name]}" ]; then
    echo "$name: checksum $got, expected ${MD5[$name]}" >&2
    exit 1
  fi
  echo "extracting $name into paper/"
  tar -xzf "$out" -C "$REPO"
done
