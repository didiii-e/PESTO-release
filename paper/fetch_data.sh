#!/usr/bin/env bash
# Fetch the data archives of the paper from Zenodo (10.5281/zenodo.23425831) and
# extract them into paper/. Only the upstream scripts need them: every figure and
# table of the manuscript is redrawn from what the repository already holds, and
# files already here are left as they are.
#
#   bash paper/fetch_data.sh          both archives (about 42 MB)
#   bash paper/fetch_data.sh runs     the saved model answers only
#   bash paper/fetch_data.sh tables   the tables of the upstream scripts only
set -euo pipefail

RECORD="https://zenodo.org/records/23425831/files"
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(dirname "$HERE")"

declare -A MD5=(
  [pesto_paper_runs.tar.gz]=97445ab9708721895c6a070e994e0ca6
  [pesto_paper_tables.tar.gz]=d52c592b461423d2f8c674d59835e80e
)

want=("pesto_paper_runs.tar.gz" "pesto_paper_tables.tar.gz")
case "${1:-all}" in
  runs)   want=("pesto_paper_runs.tar.gz") ;;
  tables) want=("pesto_paper_tables.tar.gz") ;;
  all)    ;;
  *) echo "usage: $0 [runs|tables|all]" >&2; exit 2 ;;
esac

mkdir -p "$HERE/downloads"
for name in "${want[@]}"; do
  out="$HERE/downloads/$name"
  if [ ! -f "$out" ]; then
    echo "downloading $name"
    # Zenodo sometimes drops long downloads: resume until complete.
    curl -L --fail --retry 10 --retry-all-errors -C - -o "$out.part" "$RECORD/$name?download=1"
    mv "$out.part" "$out"
  fi
  got=$(md5sum "$out" | cut -d' ' -f1)
  if [ "$got" != "${MD5[$name]}" ]; then
    echo "$name: checksum $got, expected ${MD5[$name]}" >&2
    exit 1
  fi
  echo "extracting $name into paper/"
  tar -xzf "$out" -C "$REPO" --skip-old-files
done
