#!/usr/bin/env bash
# Regenerate src/guardiano3_generated/ from openapi/v1.json.
#
# openapi/v1.json is a copy of the GuardianO3 API contract. It is updated by a
# pull request opened from the API repository whenever the contract changes;
# this script turns it into code. The generated package is never edited by
# hand: CI regenerates it and fails if the result differs from what is
# committed.
#
# Runs the generator in Docker, so no JVM is needed.
#
# Usage: ./scripts/generate.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="openapitools/openapi-generator-cli:v7.15.0"
VERSION="$(sed -n 's/^version = "\(.*\)"$/\1/p' "${ROOT}/pyproject.toml" | head -1)"

MOUNT="$ROOT"
if command -v cygpath >/dev/null 2>&1; then
  # Git Bash on Windows: Docker wants a Windows path, and MSYS must not rewrite it.
  MOUNT="$(cygpath -m "$ROOT")"
  export MSYS_NO_PATHCONV=1
fi

OUT=".generate-tmp"
rm -rf "${ROOT:?}/${OUT}"
mkdir -p "${ROOT}/${OUT}"
trap 'rm -rf "${ROOT:?}/${OUT}"' EXIT

docker run --rm \
  -v "${MOUNT}:/work" \
  -u "$(id -u):$(id -g)" \
  "$IMAGE" generate \
    -i /work/openapi/v1.json \
    -g python \
    -o "/work/${OUT}" \
    --skip-validate-spec \
    --additional-properties="packageName=guardiano3_generated,projectName=guardiano3,packageVersion=${VERSION},library=urllib3" \
    >/dev/null

# Keep the package; drop the project scaffold the generator emits around it
# (its own pyproject, setup.py, README, docs and test stubs). The distribution
# is defined once, by this repository's pyproject.toml.
rm -rf "${ROOT}/src/guardiano3_generated"
mv "${ROOT}/${OUT}/guardiano3_generated" "${ROOT}/src/guardiano3_generated"

echo "Regenerated src/guardiano3_generated (version ${VERSION})."
