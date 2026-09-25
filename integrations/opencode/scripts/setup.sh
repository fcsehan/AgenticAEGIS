#!/usr/bin/env bash
set -euo pipefail
integration_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec "${AEGIS_TEST_PYTHON:-python3}" "$integration_root/scripts/setup.py" "$@"
