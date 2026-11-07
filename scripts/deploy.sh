#!/bin/bash
# WIC 2026 Trading Agent - Deployment Script

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$PROJECT_ROOT/docker/docker-compose.yml"
ENV_FILE="$PROJECT_ROOT/.env"

# Functions
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

check_requirements() {
    log_info "Checking requirements..."

    if ! command -v docker &> /dev/null; then
        log_error "Docker not found. Please install Docker."
        exit 1
    fi

    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        log_error "Docker Compose not found. Please install Docker Compose."
        exit 1
    fi

    if [[ ! -f "$ENV_FILE" ]]; then
        log_warning ".env file not found. Creating from template..."
        cp "$PROJECT_ROOT/.env.example" "$ENV_FILE"
        log_warning "Please edit .env with your configuration before continuing."
        exit 1
    fi

    log_success "Requirements check passed"
}

build_images() {
    log_info "Building Docker images..."
    docker-compose -f "$COMPOSE_FILE" build --no-cache
    log_success "Images built"
}

start_services() {
    log_info "Starting services..."
    docker-compose -f "$COMPOSE_FILE" up -d
    log_success "Services started"
}

stop_services() {
    log_info "Stopping services..."
    docker-compose -f "$COMPOSE_FILE" down
    log_success "Services stopped"
}

restart_services() {
    log_info "Restarting services..."
    docker-compose -f "$COMPOSE_FILE" restart
    log_success "Services restarted"
}

show_logs() {
    local service="${1:-}"
    if [[ -n "$service" ]]; then
        docker-compose -f "$COMPOSE_FILE" logs -f "$service"
    else
        docker-compose -f "$COMPOSE_FILE" logs -f
    fi
}

check_status() {
    log_info "Service status:"
    docker-compose -f "$COMPOSE_FILE" ps
}

health_check() {
    log_info "Running health checks..."

    # Check IB Gateway
    if docker-compose -f "$COMPOSE_FILE" exec -T ib-gateway nc -z localhost 4002 &> /dev/null; then
        log_success "IB Gateway: Healthy (port 4002)"
    else
        log_error "IB Gateway: Unhealthy"
    fi

    # Check Trading Agent
    if curl -sf http://localhost:8080/api/status &> /dev/null; then
        log_success "Trading Agent: Healthy (dashboard responding)"
    else
        log_error "Trading Agent: Unhealthy"
    fi
}

deploy_production() {
    log_warning "Deploying to PRODUCTION environment!"
    read -p "Are you sure? Type 'yes' to continue: " confirm
    if [[ "$confirm" != "yes" ]]; then
        log_info "Deployment cancelled"
        exit 0
    fi

    # Set production mode
    sed -i 's/MODE=.*/MODE=live/' "$ENV_FILE"
    sed -i 's/IB_TRADING_MODE=.*/IB_TRADING_MODE=live/' "$ENV_FILE"
    sed -i 's/IB_PORT=.*/IB_PORT=4001/' "$ENV_FILE"

    log_info "Deploying to production..."
    build_images
    start_services

    log_success "Production deployment complete"
    log_warning "Monitor the system closely during competition hours!"
}

backup_data() {
    local backup_dir="$PROJECT_ROOT/backups/$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$backup_dir"

    log_info "Backing up data to $backup_dir..."
    cp -r "$PROJECT_ROOT/logs" "$backup_dir/" 2>/dev/null || true
    cp -r "$PROJECT_ROOT/reports" "$backup_dir/" 2>/dev/null || true
    cp "$ENV_FILE" "$backup_dir/" 2>/dev/null || true

    log_success "Backup complete: $backup_dir"
}

# Main
case "${1:-}" in
    build)
        check_requirements
        build_images
        ;;
    up|start)
        check_requirements
        start_services
        ;;
    down|stop)
        stop_services
        ;;
    restart)
        check_requirements
        restart_services
        ;;
    logs)
        show_logs "${2:-}"
        ;;
    status)
        check_status
        ;;
    health)
        health_check
        ;;
    prod|production)
        deploy_production
        ;;
    backup)
        backup_data
        ;;
    *)
        echo "WIC 2026 Trading Agent - Deployment Script"
        echo ""
        echo "Usage: $0 <command>"
        echo ""
        echo "Commands:"
        echo "  build       - Build Docker images"
        echo "  up|start    - Start all services"
        echo "  down|stop   - Stop all services"
        echo "  restart     - Restart all services"
        echo "  logs [svc]  - Show logs (optional service name)"
        echo "  status      - Show service status"
        echo "  health      - Run health checks"
        echo "  prod        - Deploy to production (live mode)"
        echo "  backup      - Backup logs and reports"
        echo ""
        echo "Environment: Edit .env file before starting"
        exit 1
        ;;
esac