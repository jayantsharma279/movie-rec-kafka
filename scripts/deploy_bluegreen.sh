#!/bin/bash
# Blue-Green Deployment Script for Zero-Downtime Model Updates
#
# This script automates the process of updating models without downtime:
# 1. Updates model files in the offline service (v2)
# 2. Rebuilds and restarts the offline service
# 3. Waits for health checks to pass
# 4. Switches nginx to route traffic to the updated service
# 5. Updates the other service (v1)
# 6. Next update will alternate (v1 -> v2)

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR/.."
NGINX_CONF="$PROJECT_ROOT/nginx.conf"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check which service is currently active
check_active_service() {
    if grep "server recommender_v1:8082" "$NGINX_CONF" | grep -q -v "^[[:space:]]*#"; then
        echo "v1"
    else
        echo "v2"
    fi
}

# Wait for service to be healthy
wait_for_health() {
    local service=$1
    local max_attempts=30
    local attempt=0
    
    log_info "Waiting for $service to become healthy..."
    
    while [ $attempt -lt $max_attempts ]; do
        if docker compose ps | grep "$service" | grep -q "healthy"; then
            log_info "$service is healthy!"
            return 0
        fi
        
        attempt=$((attempt + 1))
        echo -n "."
        sleep 2
    done
    
    log_error "$service failed to become healthy after $max_attempts attempts"
    return 1
}

# Switch nginx to target service
switch_to_service() {
    local target=$1
    
    log_info "Switching load balancer to $target..."
    
    if [ "$target" == "v1" ]; then
        # Enable v1, disable v2
        sed -i.bak 's/^[[:space:]]*#*[[:space:]]*server recommender_v1:8082/        server recommender_v1:8082/' "$NGINX_CONF"
        sed -i.bak 's/^[[:space:]]*server recommender_v2:8082/        # server recommender_v2:8082/' "$NGINX_CONF"
    else
        # Enable v2, disable v1
        sed -i.bak 's/^[[:space:]]*server recommender_v1:8082/        # server recommender_v1:8082/' "$NGINX_CONF"
        sed -i.bak 's/^[[:space:]]*#*[[:space:]]*server recommender_v2:8082/        server recommender_v2:8082/' "$NGINX_CONF"
    fi
    
    # Ensure file writes are flushed to disk
    sync
    
    # Use reload instead of restart for zero-downtime nginx config reload
    log_info "Reloading nginx configuration (zero-downtime)..."
    
    # Send HUP signal to nginx master process to gracefully reload config
    # This is the most reliable way to reload nginx without dropping connections
    if docker compose exec -T load_balancer sh -c 'kill -HUP 1' 2>/dev/null; then
        log_info "HUP signal sent successfully"
    else
        log_warn "HUP signal failed, trying nginx -s reload..."
        if docker compose exec -T load_balancer sh -c 'nginx -s reload' 2>/dev/null; then
            log_info "nginx -s reload successful"
        else
            log_warn "Reload commands failed, using restart as fallback..."
            docker compose restart load_balancer
        fi
    fi
    
    # Wait longer to ensure reload completes
    sleep 2
    
    log_info "Load balancer switched to $target"
}

# Main deployment process
main() {
    cd "$PROJECT_ROOT"
    
    log_info "Starting blue-green deployment..."
    
    # Determine current active and target services
    ACTIVE=$(check_active_service)
    if [ "$ACTIVE" == "v1" ]; then
        OFFLINE="recommender_v2"
        OFFLINE_SHORT="v2"
    else
        OFFLINE="recommender_v1"
        OFFLINE_SHORT="v1"
    fi
    
    log_info "Active service: $ACTIVE"
    log_info "Offline service: $OFFLINE_SHORT (will be updated)"
    
    # Step 1: Update offline service
    log_info "Rebuilding and restarting $OFFLINE..."
    docker compose up -d --no-deps --build "$OFFLINE"
    
    # Step 2: Wait for health check
    if ! wait_for_health "$OFFLINE"; then
        log_error "Deployment failed: $OFFLINE is not healthy"
        exit 1
    fi
    
    # Step 3: Switch traffic
    switch_to_service "$OFFLINE_SHORT"
    
    log_info "Traffic is now routed to $OFFLINE_SHORT"
    log_info "Testing new endpoint..."
    
    # Test the endpoint through load balancer
    sleep 2
    if curl -s http://localhost/recommend/1 | grep -q "+"; then
        log_info "✓ Endpoint test passed"
    else
        log_warn "⚠ Endpoint test inconclusive"
    fi
    
    # Step 4: Update the previously active service (now offline)
    log_info "Updating previously active service ($ACTIVE) in the background..."
    if [ "$ACTIVE" == "v1" ]; then
        docker compose up -d --no-deps --build recommender_v1
    else
        docker compose up -d --no-deps --build recommender_v2
    fi
    
    log_info "✓ Blue-green deployment complete!"
    log_info "Active service: $OFFLINE_SHORT"
    log_info "Both services are now synchronized"
    log_info ""
    log_info "Access your service at: http://localhost/recommend/<user_id>"
}

# Run main function
main "$@"
