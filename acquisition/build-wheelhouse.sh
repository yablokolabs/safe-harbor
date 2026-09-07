#!/usr/bin/env bash
# Safe Harbor — build the jñāpakaṁ offline wheelhouse.
#
#   ./acquisition/build-wheelhouse.sh [--output DIR]
#
# The python-wheels artifact is NOT downloadable from a single URL: it is a
# deterministic assembly of pinned wheels fetched from PyPI's immutable
# file store. This recipe:
#
#   1. downloads each pinned wheel from its immutable files.pythonhosted.org
#      URL (these URLs are stable forever for a given file);
#   2. verifies each wheel's SHA-256 against the pin list below;
#   3. assembles a byte-reproducible tarball (sorted entries, normalized
#      owner/mode/mtime) so the resulting artifact SHA-256 is identical on
#      any machine — which is what manifest/checksums.sha256 pins.
#
# Requires network access to files.pythonhosted.org. Runs on the connected
# acquisition machine only (or CI). Never runs on the air-gapped target.
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

OUT_DIR="${ROOT_DIR}/acquisition/cache/python-wheels"
if [[ "${1:-}" == "--output" ]]; then
    OUT_DIR="$2"
fi
OUT_TARBALL="${OUT_DIR}/jnaapakam-wheels-cp313-amd64.tar.gz"

# --- pinned wheels: filename | immutable URL | sha256 -----------------------
# jnaapakam 0.5.1 (cp313 / manylinux2014 amd64) + its dependency closure.
# Each URL is the immutable files.pythonhosted.org location of the exact
# wheel file (stable forever). Hashes were verified against the wheels
# downloaded at acquisition time.
read -r -d '' WHEELS <<'EOF' || true
aiohappyeyeballs-2.7.1-py3-none-any.whl https://files.pythonhosted.org/packages/71/43/1947f06babed6b3f1d7f38b0c767f52df66bfb2bc10b468c4a7de9eceff2/aiohappyeyeballs-2.7.1-py3-none-any.whl 9243213661e29250eb41368e5daa826fc017156c3b8a11440826b2e3ed376472
aiohttp-3.14.3-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl https://files.pythonhosted.org/packages/ca/1c/7da8d08e74d56f00070822f9638ff3f1c563f8ad87d1efa996c87bfc8644/aiohttp-3.14.3-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl d7d2deec16eeedf55f2c7cf75b521ea3856a5177e123844f8fd0f114ce252cb5
aiosignal-1.4.0-py3-none-any.whl https://files.pythonhosted.org/packages/fb/76/641ae371508676492379f16e2fa48f4e2c11741bd63c48be4b12a6b09cba/aiosignal-1.4.0-py3-none-any.whl 053243f8b92b990551949e63930a839ff0cf0b0ebbe0597b0f3fb19e1a0fe82e
attrs-26.1.0-py3-none-any.whl https://files.pythonhosted.org/packages/64/b4/17d4b0b2a2dc85a6df63d1157e028ed19f90d4cd97c36717afef2bc2f395/attrs-26.1.0-py3-none-any.whl c647aa4a12dfbad9333ca4e71fe62ddc36f4e63b2d260a37a8b83d2f043ac309
frozenlist-1.8.0-cp313-cp313-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl https://files.pythonhosted.org/packages/d5/4e/e4691508f9477ce67da2015d8c00acd751e6287739123113a9fca6f1604e/frozenlist-1.8.0-cp313-cp313-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl fb30f9626572a76dfe4293c7194a09fb1fe93ba94c7d4f720dfae3b646b45027
idna-3.19-py3-none-any.whl https://files.pythonhosted.org/packages/57/b0/0e52c878c53f245edd3a11020f20979b3f490f245af532c7cae3027754b5/idna-3.19-py3-none-any.whl 815e7be7a7806d54abb586dc943addc79e8b2ee16915059658cbeff4b1b43bf4
jnaapakam-0.5.1-py3-none-any.whl https://files.pythonhosted.org/packages/04/c4/2243b58af92e890a618ad747a591e3d82c664c88c274eefdbf43012a6a92/jnaapakam-0.5.1-py3-none-any.whl 63514b7a7adaf7ab6e84e305379baf5ec0f4d6fb2c59aa2d5f9c9ce339a12e86
multidict-6.7.1-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl https://files.pythonhosted.org/packages/b0/73/6e1b01cbeb458807aa0831742232dbdd1fa92bfa33f52a3f176b4ff3dc11/multidict-6.7.1-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl 9d624335fd4fa1c08a53f8b4be7676ebde19cd092b3895c421045ca87895b429
propcache-0.5.2-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl https://files.pythonhosted.org/packages/8b/c6/979176efdaa3d239e36d503d5af63a0a773b36662ed8f52e5b6a6d9fd40e/propcache-0.5.2-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl 4db0ba63d693afd40d249bd93f842b5f144f8fcbb83de05660373bcf30517b1d
yarl-1.24.5-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl https://files.pythonhosted.org/packages/0a/43/8e55ae7538ba5f28ccb3c845c6dd4549cf7016d5992e5326512519107cdd/yarl-1.24.5-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl d46b86567dd4e248c6c159fcbcdcce01e0a5c8a7cd2334a0fff759d0fa075b16
EOF

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

mkdir -p "${OUT_DIR}" "${TMP_DIR}/wheels"

echo "downloading pinned wheels (cp313 amd64) ..."
while read -r filename url sha256; do
    [[ -z "${filename}" ]] && continue
    echo "  ${filename}"
    curl -fsSL --retry 3 --max-time 300 -o "${TMP_DIR}/wheels/${filename}" "${url}"
    echo "${sha256}  ${TMP_DIR}/wheels/${filename}" | sha256sum -c --quiet -
done <<< "${WHEELS}"

echo "assembling deterministic tarball ..."
# Byte-reproducible tar: sorted entries, normalized owner/group/mode/mtime,
# gzip without filename/timestamp (tar -czf embeds an mtime otherwise).
tar -C "${TMP_DIR}/wheels" \
    --sort=name --owner=0 --group=0 --mode=a+rX,u+w --mtime='@0' \
    --numeric-owner -cf - . \
    | gzip -n > "${TMP_DIR}/out.tar.gz"
mv "${TMP_DIR}/out.tar.gz" "${OUT_TARBALL}"

echo "wheelhouse built: ${OUT_TARBALL}"
echo "SHA-256: $(sha256sum "${OUT_TARBALL}" | cut -d' ' -f1)"
echo "files: $(tar tzf "${OUT_TARBALL}" | grep -c '\.whl$') wheels"
