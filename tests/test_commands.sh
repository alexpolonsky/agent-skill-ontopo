#!/bin/bash
# Integration tests for ontopo-cli.py

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLI="$SCRIPT_DIR/scripts/ontopo-cli.py"
PASS=0
FAIL=0

test_cmd() {
    local name="$1"
    local cmd="$2"
    local expected="$3"

    output=$(python3 "$CLI" $cmd 2>&1)
    if echo "$output" | grep -q "$expected"; then
        echo "✓ $name"
        ((PASS++))
    else
        echo "✗ $name"
        echo "  Expected: $expected"
        echo "  Got: ${output:0:100}..."
        ((FAIL++))
    fi
}

echo "=== Ontopo CLI Integration Tests ==="
echo ""

# Static commands
test_cmd "cities" "cities" "tel-aviv"
test_cmd "categories" "categories" "restaurants"
test_cmd "cities --json" "cities --json" '"command": "cities"'
test_cmd "categories --json" "categories --json" '"command": "categories"'

# Search
test_cmd "search taizu" "search taizu" "Taizu"
test_cmd "search --json" "search taizu --json" '"command": "search"'
test_cmd "search --json venue_id" "search taizu --json" '"venue_id"'
test_cmd "search --json --raw" "search taizu --json --raw" '"venues"'

# Venue info
test_cmd "info" "info 36960535" "Taizu"
test_cmd "info --json" "info 36960535 --json" '"booking_url"'
test_cmd "info --json --raw" "info 36960535 --json --raw" '"document_type"'

# URL
test_cmd "url" "url 36960535" "https://ontopo.com"

# Menu
test_cmd "menu" "menu 36960535" "Menu:"

# Availability (may vary based on actual availability)
test_cmd "check" "check 36960535 tomorrow" "Availability Check"
test_cmd "available" "available tomorrow 19:00" "Available Venues"
test_cmd "range" "range 36960535 tomorrow +1" "Availability Range"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
exit $FAIL
