#!/bin/bash
# Test script to verify blue-green deployment works correctly
#
# This script tests:
# 1. Both services are healthy
# 2. Load balancer is working
# 3. Zero-downtime during deployment
# 4. Service switching works correctly

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR/.."

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_test() {
    echo -e "${BLUE}[TEST]${NC} $1"
}

log_pass() {
    echo -e "${GREEN}[PASS]${NC} ✓ $1"
}

log_fail() {
    echo -e "${RED}[FAIL]${NC} ✗ $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Test 1: Check if services are running
test_services_running() {
    log_test "Checking if services are running..."
    
    cd "$PROJECT_ROOT"
    
    if ! docker compose ps | grep -q "recommender_v1"; then
        log_fail "recommender_v1 is not running"
        return 1
    fi
    
    if ! docker compose ps | grep -q "recommender_v2"; then
        log_fail "recommender_v2 is not running"
        return 1
    fi
    
    if ! docker compose ps | grep -q "load_balancer"; then
        log_fail "load_balancer is not running"
        return 1
    fi
    
    log_pass "All services are running"
    return 0
}

# Test 2: Check health endpoints
test_health_endpoints() {
    log_test "Testing health endpoints..."
    
    # Test v1
    if curl -s -f http://localhost:8082/health > /dev/null; then
        log_pass "v1 health check passed"
    else
        log_fail "v1 health check failed"
        return 1
    fi
    
    # Test v2
    if curl -s -f http://localhost:8083/health > /dev/null; then
        log_pass "v2 health check passed"
    else
        log_fail "v2 health check failed"
        return 1
    fi
    
    # Test load balancer
    if curl -s -f http://localhost/lb-health > /dev/null; then
        log_pass "Load balancer health check passed"
    else
        log_fail "Load balancer health check failed"
        return 1
    fi
    
    return 0
}

# Test 3: Check recommendation endpoints
test_recommendation_endpoints() {
    log_test "Testing recommendation endpoints..."
    
    # Test v1
    if curl -s -f http://localhost:8082/recommend/1 | grep -q "+"; then
        log_pass "v1 recommendation endpoint works"
    else
        log_warn "v1 recommendation endpoint returned unexpected response"
    fi
    
    # Test v2
    if curl -s -f http://localhost:8083/recommend/1 | grep -q "+"; then
        log_pass "v2 recommendation endpoint works"
    else
        log_warn "v2 recommendation endpoint returned unexpected response"
    fi
    
    # Test through load balancer
    if curl -s -f http://localhost/recommend/1 | grep -q "+"; then
        log_pass "Load balancer recommendation endpoint works"
    else
        log_fail "Load balancer recommendation endpoint failed"
        return 1
    fi
    
    return 0
}

# Test 4: Check which service is active
test_active_service() {
    log_test "Checking active service configuration..."
    
    cd "$PROJECT_ROOT"
    
    if grep "server recommender_v1:8082" nginx.conf | grep -q -v "^[[:space:]]*#"; then
        log_info "Active service: v1"
        echo "v1"
    elif grep "server recommender_v2:8082" nginx.conf | grep -q -v "^[[:space:]]*#"; then
        log_info "Active service: v2"
        echo "v2"
    else
        log_fail "Could not determine active service"
        return 1
    fi
    
    return 0
}

# Test 5: Monitor service during deployment
test_zero_downtime() {
    log_test "Testing zero-downtime deployment..."
    log_info "This will make continuous requests while deployment runs"
    log_info "Press Ctrl+C to stop monitoring"
    log_info ""
    
    local success_count=0
    local fail_count=0
    local start_time=$(date +%s)
    
    while true; do
        if curl -s -f --max-time 2 http://localhost/recommend/1 > /dev/null 2>&1; then
            success_count=$((success_count + 1))
            echo -ne "\r${GREEN}✓${NC} Requests: $((success_count + fail_count)) | Success: $success_count | Failed: $fail_count | Uptime: $(($(date +%s) - start_time))s"
        else
            fail_count=$((fail_count + 1))
            echo -ne "\r${RED}✗${NC} Requests: $((success_count + fail_count)) | Success: $success_count | Failed: $fail_count | Uptime: $(($(date +%s) - start_time))s"
        fi
        sleep 0.5
    done
}

# Test 6: Compare responses before and after deployment
test_service_consistency() {
    log_test "Testing service consistency..."
    
    # Make 10 requests and check responses
    log_info "Making 10 requests through load balancer..."
    
    local consistent=true
    for i in {1..10}; do
        response=$(curl -s http://localhost/recommend/1)
        if ! echo "$response" | grep -q "+"; then
            log_warn "Request $i returned unexpected response"
            consistent=false
        fi
    done
    
    if [ "$consistent" = true ]; then
        log_pass "All responses are consistent"
    else
        log_fail "Some responses were inconsistent"
        return 1
    fi
    
    return 0
}

# Main menu
show_menu() {
    echo ""
    echo "============================================"
    echo "  Blue-Green Deployment Test Suite"
    echo "============================================"
    echo ""
    echo "1. Quick Test (all basic tests)"
    echo "2. Test Services Status"
    echo "3. Test Health Endpoints"
    echo "4. Test Recommendation Endpoints"
    echo "5. Check Active Service"
    echo "6. Monitor Zero-Downtime (continuous)"
    echo "7. Test Service Consistency"
    echo "8. Full Deployment Test (runs deployment)"
    echo "9. Exit"
    echo ""
    echo -n "Select option: "
}

# Quick test - runs all basic tests
quick_test() {
    log_info "Running quick test suite..."
    echo ""
    
    local failed=0
    
    test_services_running || failed=$((failed + 1))
    echo ""
    
    test_health_endpoints || failed=$((failed + 1))
    echo ""
    
    test_recommendation_endpoints || failed=$((failed + 1))
    echo ""
    
    test_active_service > /dev/null || failed=$((failed + 1))
    echo ""
    
    test_service_consistency || failed=$((failed + 1))
    echo ""
    
    if [ $failed -eq 0 ]; then
        log_pass "All tests passed! ✓"
    else
        log_fail "$failed test(s) failed"
        return 1
    fi
}

# Full deployment test
full_deployment_test() {
    log_info "Running full deployment test..."
    log_warn "This will trigger an actual deployment!"
    echo ""
    
    # Record initial state
    initial_service=$(test_active_service)
    
    # Start monitoring in background
    log_info "Starting background monitor..."
    (
        success_count=0
        fail_count=0
        while true; do
            if curl -s -f --max-time 2 http://localhost/recommend/1 > /dev/null 2>&1; then
                success_count=$((success_count + 1))
            else
                fail_count=$((fail_count + 1))
            fi
            sleep 0.5
        done
    ) &
    MONITOR_PID=$!
    
    # Run deployment
    log_info "Running deployment script..."
    bash "$SCRIPT_DIR/deploy_bluegreen.sh"
    
    # Stop monitoring
    sleep 2
    kill $MONITOR_PID 2>/dev/null || true
    
    # Verify service switched
    final_service=$(test_active_service)
    
    if [ "$initial_service" != "$final_service" ]; then
        log_pass "Service switched from $initial_service to $final_service"
    else
        log_fail "Service did not switch (still $initial_service)"
    fi
    
    # Run final tests
    echo ""
    quick_test
}

# Interactive mode
interactive_mode() {
    while true; do
        show_menu
        read -r choice
        echo ""
        
        case $choice in
            1) quick_test ;;
            2) test_services_running ;;
            3) test_health_endpoints ;;
            4) test_recommendation_endpoints ;;
            5) test_active_service ;;
            6) test_zero_downtime ;;
            7) test_service_consistency ;;
            8) full_deployment_test ;;
            9) log_info "Exiting..."; exit 0 ;;
            *) log_warn "Invalid option" ;;
        esac
        
        echo ""
        echo "Press Enter to continue..."
        read -r
    done
}

# Main
main() {
    cd "$PROJECT_ROOT"
    
    if [ "$1" == "--quick" ] || [ "$1" == "-q" ]; then
        quick_test
    elif [ "$1" == "--monitor" ] || [ "$1" == "-m" ]; then
        test_zero_downtime
    elif [ "$1" == "--full" ] || [ "$1" == "-f" ]; then
        full_deployment_test
    else
        interactive_mode
    fi
}

main "$@"
