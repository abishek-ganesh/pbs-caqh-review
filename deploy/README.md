# CAQH Data Summary Review - VM Deployment

This directory contains everything needed to deploy the CAQH reviewer to the production VM (PBSAAJWN01).

## Quick Start

```bash
# 1. SSH into the VM
ssh username@PBSAAJWN01.teampbs.com

# 2. Copy this deploy folder to the VM
scp -r deploy/ username@PBSAAJWN01:/tmp/

# 3. Run the setup script
cd /tmp/deploy
chmod +x setup_vm.sh
./setup_vm.sh

# 4. Copy the application code
# (See detailed steps below)
```

## VM Details

| Property | Value |
|----------|-------|
| **Hostname** | PBSAAJWN01 |
| **Credentials** | Stored in PBS 1password |
| **OS** | Linux (TBD - check after first connection) |
| **Purpose** | Run CAQH document processor on cron schedule |

## Directory Structure (on VM)

```
/opt/caqh-reviewer/
├── src/                      # Application source code
│   ├── extraction/           # PDF extraction logic
│   ├── validation/           # Field validation
│   ├── sharepoint/           # PBS API client
│   └── utils/                # Utilities, HTML generator
├── config/
│   └── .env                  # API credentials (not in git!)
├── logs/
│   ├── cron.log              # Application logs
│   └── cron_wrapper.log      # Cron execution logs
├── temp/                     # Temporary PDF downloads
├── venv/                     # Python virtual environment
├── cron_runner.py            # Main entry point
└── run_cron.sh               # Cron wrapper script
```

## Files in This Directory

| File | Purpose |
|------|---------|
| `setup_vm.sh` | Automated VM setup script |
| `requirements-vm.txt` | Minimal Python dependencies for production |
| `README.md` | This file |

## Environment Variables

Create `/opt/caqh-reviewer/config/.env` with:

```bash
# PBS Enterprise API Configuration
PBS_API_BASE_URL=https://???              # Get from Hasan
PBS_API_ACCESS_TOKEN=your-token-here      # Get from Hasan
PBS_SHAREPOINT_SITE_URL=https://sharepoint.teampbs.com/CAQH%20Data%20Summary
PBS_CAQH_LIBRARY_NAME=CAQH library Test
```

## System Dependencies

The setup script installs these automatically:

- **Python 3.9+** - Runtime
- **Tesseract OCR** - For scanned PDF text extraction
- **Poppler** - For PDF to image conversion

## Cron Schedule

The cron job runs every 5 minutes:

```cron
*/5 * * * * /opt/caqh-reviewer/run_cron.sh >> /opt/caqh-reviewer/logs/cron_wrapper.log 2>&1
```

## Testing

Before enabling the cron job:

```bash
# Activate virtual environment
source /opt/caqh-reviewer/venv/bin/activate

# Load environment variables
source /opt/caqh-reviewer/config/.env
export PBS_API_BASE_URL PBS_API_ACCESS_TOKEN PBS_SHAREPOINT_SITE_URL PBS_CAQH_LIBRARY_NAME

# Test connection (dry run)
cd /opt/caqh-reviewer
python3 cron_runner.py --dry-run --verbose

# Process a single item (dry run)
python3 cron_runner.py --item-id 123 --dry-run
```

## Troubleshooting

### Check logs
```bash
tail -f /opt/caqh-reviewer/logs/cron.log
tail -f /opt/caqh-reviewer/logs/cron_wrapper.log
```

### Check cron is running
```bash
crontab -l
grep caqh /var/log/syslog  # or /var/log/cron
```

### Test API connection
```bash
source /opt/caqh-reviewer/venv/bin/activate
python3 -c "
from src.sharepoint import create_client_from_env
client = create_client_from_env()
items = client.get_unprocessed_items()
print(f'Found {len(items)} unprocessed items')
"
```

### Common Issues

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError` | Activate venv: `source venv/bin/activate` |
| `AuthenticationError` | Check `PBS_API_ACCESS_TOKEN` in .env |
| `Connection refused` | Check `PBS_API_BASE_URL` and VPN connection |
| `Tesseract not found` | Run `sudo apt-get install tesseract-ocr` |

## Deployment Checklist

- [ ] VM credentials obtained from 1password
- [ ] SSH access verified
- [ ] `setup_vm.sh` executed successfully
- [ ] Application code copied to `/opt/caqh-reviewer`
- [ ] `.env` file configured with real credentials
- [ ] Dry run test passed
- [ ] Cron job enabled
- [ ] Log rotation configured

## Rollback

If something goes wrong:

```bash
# Stop cron job
crontab -e  # Remove/comment the caqh line

# Check logs for errors
tail -100 /opt/caqh-reviewer/logs/cron.log

# Restore from backup (if applicable)
```

## Contact

- **Project Lead:** Abishek
- **API Support:** Hasan Naqvi (PBS Enterprise API)
- **VM Support:** Lyndrae (IT Infrastructure)
- **Business Owner:** Christian Helenius
