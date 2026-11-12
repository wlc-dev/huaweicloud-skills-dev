#!/usr/bin/env bash
# test-cli-commands.sh — functional smoke test for huawei-cloud-obs-dir-count
set -uo pipefail

SKILL_PATH="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
REGION="${HUAWEI_CLOUD_REGION:-cn-north-4}"
BUCKET="${TEST_OBS_BUCKET:-obs-hd-dev-static}"

pass=0
fail=0
skip=0

SCRIPT="$SKILL_PATH/scripts/count_obs_directories.py"

# run_test — execute a single smoke-test case and tally its result.
#   $1 id   — test case identifier (e.g. TC-01)
#   $2 name — human-readable test case name
#   $3 cmd  — shell command to run for this case
run_test() {
    local id="$1" name="$2" cmd="$3"
    echo -n "  [$id] $name ... "
    # Run the case in a subshell, capturing both stdout and stderr into
    # `output`; the exit status decides whether the case passed.
    if output=$(bash -c "$cmd" 2>&1); then
        # Success: print PASS and bump the pass counter.
        echo "PASS"
        pass=$((pass + 1))
    else
        # Failure: print FAIL plus the captured output for diagnosis, then
        # bump the fail counter. Both counters feed the "Results" summary at
        # the end of the script, which exits 1 when fail > 0.
        echo "FAIL"
        echo "    Error: $output"
        fail=$((fail + 1))
    fi
}

echo "=== OBS Directory Count Skill Tests (region: $REGION, bucket: $BUCKET) ==="
echo

# Prerequisite check
if ! command -v python3 &>/dev/null; then
    echo "SKIP: python3 not available"
    skip=$((skip + 4))
    exit 0
fi

run_test "TC-01" "Help output" "python3 $SCRIPT --help"
run_test "TC-02" "Immediate count (CLI auto)" "python3 $SCRIPT --bucket $BUCKET"
run_test "TC-03" "Immediate count (SDK)" "python3 $SCRIPT --bucket $BUCKET --executor sdk"
run_test "TC-04" "Recursive count (SDK)" "python3 $SCRIPT --bucket $BUCKET --recursive"

echo
echo "=== Results: $pass passed, $fail failed, $skip skipped ==="
if [ "$fail" -gt 0 ]; then
    exit 1
fi
exit 0
