#!/usr/bin/env bash
set -euo pipefail
integration_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$integration_root/../.."
mkdir -p "$integration_root/.runs"
results_dir="$(mktemp -d "$integration_root/.runs/run.XXXXXX")"
export AEGIS_OPENCODE_RESULTS="$results_dir"
node_status=0
python_status=0
node --test --test-reporter=junit "$integration_root/tests/plugin.test.mjs" > "$results_dir/plugin.xml" || node_status=$?
"${AEGIS_TEST_PYTHON:-python3}" -m pytest "$integration_root/tests/test_process.py" -q --junitxml="$results_dir/process.xml" --basetemp="$results_dir/workspaces" "$@" || python_status=$?
"${AEGIS_TEST_PYTHON:-python3}" "$integration_root/scripts/report.py" "$results_dir"
echo "Evidence: $results_dir/report.json"
test "$node_status" -eq 0 && test "$python_status" -eq 0
