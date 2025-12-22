#!/bin/bash
# =============================================================================
# CAQH Data Summary Review - VM Setup Script
# =============================================================================
#
# This script sets up the CAQH reviewer on a fresh Linux VM (PBSAAJWN01)
#
# Prerequisites:
#   - SSH access to the VM
#   - sudo privileges
#
# Usage:
#   1. Copy this script to the VM
#   2. Run: chmod +x setup_vm.sh && ./setup_vm.sh
#
# =============================================================================

set -e  # Exit on error

echo "=============================================="
echo "CAQH Data Summary Review - VM Setup"
echo "=============================================="
echo ""

# Configuration
INSTALL_DIR="/opt/caqh-reviewer"
LOG_DIR="${INSTALL_DIR}/logs"
TEMP_DIR="${INSTALL_DIR}/temp"
CONFIG_DIR="${INSTALL_DIR}/config"
VENV_DIR="${INSTALL_DIR}/venv"
REPO_URL="https://github.com/your-org/pbs-caqh-local.git"  # Update this

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
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

# =============================================================================
# Step 1: Check prerequisites
# =============================================================================
echo ""
log_info "Step 1: Checking prerequisites..."

# Check if running as root or with sudo
if [ "$EUID" -ne 0 ]; then
    log_warn "Not running as root. Some commands may require sudo."
fi

# Check Python version
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
    log_info "Python version: $PYTHON_VERSION"
else
    log_error "Python3 not found. Installing..."
    sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-venv
fi

# =============================================================================
# Step 2: Install system dependencies
# =============================================================================
echo ""
log_info "Step 2: Installing system dependencies..."

# Detect package manager
if command -v apt-get &> /dev/null; then
    PKG_MANAGER="apt-get"
    log_info "Detected Debian/Ubuntu system"
    sudo apt-get update
    sudo apt-get install -y \
        tesseract-ocr \
        poppler-utils \
        python3-pip \
        python3-venv \
        git
elif command -v yum &> /dev/null; then
    PKG_MANAGER="yum"
    log_info "Detected RHEL/CentOS system"
    sudo yum install -y \
        tesseract \
        poppler-utils \
        python3-pip \
        git
else
    log_error "Unsupported package manager. Please install dependencies manually."
    exit 1
fi

# Verify Tesseract installation
if command -v tesseract &> /dev/null; then
    TESSERACT_VERSION=$(tesseract --version 2>&1 | head -n1)
    log_info "Tesseract: $TESSERACT_VERSION"
else
    log_error "Tesseract not installed correctly"
    exit 1
fi

# =============================================================================
# Step 3: Create directory structure
# =============================================================================
echo ""
log_info "Step 3: Creating directory structure..."

sudo mkdir -p "$INSTALL_DIR"
sudo mkdir -p "$LOG_DIR"
sudo mkdir -p "$TEMP_DIR"
sudo mkdir -p "$CONFIG_DIR"

# Set ownership (adjust username as needed)
CURRENT_USER=$(whoami)
sudo chown -R "$CURRENT_USER:$CURRENT_USER" "$INSTALL_DIR"

log_info "Created directories:"
log_info "  - $INSTALL_DIR"
log_info "  - $LOG_DIR"
log_info "  - $TEMP_DIR"
log_info "  - $CONFIG_DIR"

# =============================================================================
# Step 4: Set up Python virtual environment
# =============================================================================
echo ""
log_info "Step 4: Setting up Python virtual environment..."

python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

pip install --upgrade pip
log_info "Virtual environment created at $VENV_DIR"

# =============================================================================
# Step 5: Clone or copy application code
# =============================================================================
echo ""
log_info "Step 5: Setting up application code..."

# Option 1: Clone from git (if available)
# git clone $REPO_URL $INSTALL_DIR/app

# Option 2: Assume code is already copied
if [ -f "requirements-vm.txt" ]; then
    log_info "Installing dependencies from requirements-vm.txt..."
    pip install -r requirements-vm.txt
else
    log_warn "requirements-vm.txt not found in current directory"
    log_warn "Please copy the application code to $INSTALL_DIR and run:"
    log_warn "  pip install -r deploy/requirements-vm.txt"
fi

# =============================================================================
# Step 6: Create environment file template
# =============================================================================
echo ""
log_info "Step 6: Creating environment file template..."

ENV_FILE="$CONFIG_DIR/.env"

if [ ! -f "$ENV_FILE" ]; then
    cat > "$ENV_FILE" << 'EOF'
# CAQH Data Summary Review - Environment Configuration
# Fill in these values before running the cron job

# PBS Enterprise API Configuration
PBS_API_BASE_URL=https://api.teampbs.com          # Get from Hasan
PBS_API_ACCESS_TOKEN=your-azure-ad-token-here     # Get from Hasan
PBS_SHAREPOINT_SITE_URL=https://sharepoint.teampbs.com/CAQH%20Data%20Summary
PBS_CAQH_LIBRARY_NAME=CAQH library Test

# Logging
LOG_LEVEL=INFO
EOF

    chmod 600 "$ENV_FILE"  # Restrict permissions
    log_info "Created environment template at $ENV_FILE"
    log_warn "IMPORTANT: Edit $ENV_FILE with actual API credentials"
else
    log_info "Environment file already exists at $ENV_FILE"
fi

# =============================================================================
# Step 7: Set up cron job
# =============================================================================
echo ""
log_info "Step 7: Setting up cron job..."

CRON_SCRIPT="$INSTALL_DIR/run_cron.sh"

cat > "$CRON_SCRIPT" << EOF
#!/bin/bash
# CAQH Cron Runner Wrapper
# This script is called by cron every 5 minutes

# Load environment
source $CONFIG_DIR/.env
export PBS_API_BASE_URL PBS_API_ACCESS_TOKEN PBS_SHAREPOINT_SITE_URL PBS_CAQH_LIBRARY_NAME

# Activate virtual environment
source $VENV_DIR/bin/activate

# Change to app directory
cd $INSTALL_DIR

# Run the cron runner
python3 cron_runner.py --log-file $LOG_DIR/cron.log

# Deactivate virtual environment
deactivate
EOF

chmod +x "$CRON_SCRIPT"
log_info "Created cron wrapper script at $CRON_SCRIPT"

# Add to crontab (commented out by default - uncomment when ready)
CRON_LINE="*/5 * * * * $CRON_SCRIPT >> $LOG_DIR/cron_wrapper.log 2>&1"
log_info ""
log_info "To enable the cron job, run:"
log_info "  crontab -e"
log_info "Then add this line:"
log_info "  $CRON_LINE"

# =============================================================================
# Step 8: Create log rotation config
# =============================================================================
echo ""
log_info "Step 8: Setting up log rotation..."

LOGROTATE_CONF="/etc/logrotate.d/caqh-reviewer"

sudo tee "$LOGROTATE_CONF" > /dev/null << EOF
$LOG_DIR/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 644 $CURRENT_USER $CURRENT_USER
}
EOF

log_info "Created log rotation config at $LOGROTATE_CONF"

# =============================================================================
# Summary
# =============================================================================
echo ""
echo "=============================================="
echo "Setup Complete!"
echo "=============================================="
echo ""
log_info "Installation directory: $INSTALL_DIR"
log_info "Log directory: $LOG_DIR"
log_info "Config directory: $CONFIG_DIR"
log_info "Virtual environment: $VENV_DIR"
echo ""
log_warn "NEXT STEPS:"
echo "  1. Edit $CONFIG_DIR/.env with actual API credentials"
echo "  2. Copy application code to $INSTALL_DIR"
echo "  3. Test with: python3 cron_runner.py --dry-run"
echo "  4. Enable cron job when ready"
echo ""
log_info "To test the installation:"
echo "  source $VENV_DIR/bin/activate"
echo "  python3 -c 'from src.sharepoint import PBSEnterpriseClient; print(\"OK\")'"
echo ""
