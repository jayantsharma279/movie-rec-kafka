#!/bin/bash
# Quick test to verify zero-downtime deployment
# Run this script in one terminal, then run deploy_bluegreen.sh in another

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}Starting zero-downtime monitoring...${NC}"
echo "Make requests every 0.5 seconds. Run deploy_bluegreen.sh in another terminal."
echo "Press Ctrl+C to stop."
echo ""

success_count=0
fail_count=0
start_time=$(date +%s)

while true; do
    if curl -s -f --max-time 2 http://localhost/recommend/1 > /dev/null 2>&1; then
        success_count=$((success_count + 1))
        printf "\r${GREEN}✓${NC} Requests: %d | Success: %d | Failed: %d | Uptime: %ds" \
            $((success_count + fail_count)) $success_count $fail_count $(($(date +%s) - start_time))
    else
        fail_count=$((fail_count + 1))
        printf "\r${RED}✗${NC} Requests: %d | Success: %d | ${RED}Failed: %d${NC} | Uptime: %ds" \
            $((success_count + fail_count)) $success_count $fail_count $(($(date +%s) - start_time))
        echo ""  # New line on failure to make it visible
    fi
    sleep 0.5
done
