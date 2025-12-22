# VM Connection Guide - PBSAAJWN01

**Quick Reference:** How to connect to the CAQH Review VM and work with it.

---

## Quick Start (TL;DR)

```bash
# 1. Connect to VPN (GlobalProtect)
# 2. SSH in:
ssh administrator@10.1.11.128
# Password: PenguinBaconStatus@PBSAAJWN01

# 3. Activate environment:
source /opt/caqh-reviewer/venv/bin/activate
cd /opt/caqh-reviewer
```

---

## Step 1: Connect to VPN

1. Open **GlobalProtect** (menu bar icon on Mac)
2. Enter portal address if prompted
3. Enter your PBS credentials
4. Click **Connect**
5. Wait for "Connected" status

**Verify VPN is working:**
```bash
ping 10.1.11.128
```

---

## Step 2: SSH into the VM

```bash
ssh administrator@10.1.11.128
```

**Credentials:**
- **Username:** `administrator` (lowercase!)
- **Password:** `PenguinBaconStatus@PBSAAJWN01`

**Troubleshooting:**
- If "Permission denied" → Check username is lowercase
- If "Connection refused" → Check VPN is connected
- If "Could not resolve hostname" → Use IP address, not hostname

---

## Step 3: Navigate to the Application

```bash
# Go to the app directory
cd /opt/caqh-reviewer

# Activate the Python virtual environment
source venv/bin/activate

# You should see (venv) in your prompt:
# (venv) administrator@PBSAAJWN01:/opt/caqh-reviewer$
```

---

## Common Tasks

### Check if everything is working
```bash
source /opt/caqh-reviewer/venv/bin/activate
cd /opt/caqh-reviewer
python3 -c "from cron_runner import CronRunner; print('OK')"
```

### View logs
```bash
# Cron job logs
tail -f /opt/caqh-reviewer/logs/cron.log

# Cron wrapper logs
tail -f /opt/caqh-reviewer/logs/cron_wrapper.log
```

### Test the cron runner (dry run)
```bash
source /opt/caqh-reviewer/venv/bin/activate
cd /opt/caqh-reviewer
python3 cron_runner.py --dry-run --verbose
```

### Run on a specific item
```bash
python3 cron_runner.py --item-id 123 --dry-run
```

### Update the code from GitHub
```bash
cd /opt/caqh-reviewer
git pull origin main
```

### Edit environment variables
```bash
nano /opt/caqh-reviewer/config/.env
```

### Check cron job status
```bash
crontab -l
```

### Enable/disable cron job
```bash
# Edit crontab
crontab -e

# Add this line to enable (runs every 5 minutes):
*/5 * * * * /opt/caqh-reviewer/run_cron.sh >> /opt/caqh-reviewer/logs/cron_wrapper.log 2>&1

# Comment it out with # to disable
```

### Check system status
```bash
# Disk space
df -h

# Memory
free -h

# Python version
python3 --version

# Tesseract version
tesseract --version
```

---

## VM Details

| Property | Value |
|----------|-------|
| **Hostname** | PBSAAJWN01 |
| **IP Address** | 10.1.11.128 |
| **OS** | Ubuntu 24.04.3 LTS |
| **Python** | 3.12.3 |
| **Tesseract** | 5.3.4 |
| **App Directory** | `/opt/caqh-reviewer` |
| **Virtual Env** | `/opt/caqh-reviewer/venv` |
| **Logs** | `/opt/caqh-reviewer/logs/` |
| **Config** | `/opt/caqh-reviewer/config/.env` |

---

## Directory Structure on VM

```
/opt/caqh-reviewer/
├── venv/                    # Python virtual environment
├── logs/                    # Application logs
│   ├── cron.log            # Main cron job output
│   └── cron_wrapper.log    # Cron wrapper output
├── config/
│   └── .env                # Environment variables (API keys, etc.)
├── temp/                   # Temporary files
├── src/                    # Application source code
├── cron_runner.py          # Main entry point
├── run_cron.sh            # Cron wrapper script
└── deploy/                 # Deployment scripts
```

---

## Environment Variables (.env)

Located at `/opt/caqh-reviewer/config/.env`:

```bash
# PBS Enterprise API
PBS_API_BASE_URL=https://???  # Get from Hasan
PBS_API_ACCESS_TOKEN=???      # Get from Hasan
PBS_SITE_URL=https://sharepoint.teampbs.com/CAQH%20Data%20Summary
PBS_LIBRARY_NAME=CAQH library Test

# Logging
LOG_LEVEL=INFO
```

---

## Troubleshooting

### Can't connect via SSH
1. Check VPN is connected (GlobalProtect shows "Connected")
2. Try pinging: `ping 10.1.11.128`
3. Use IP address instead of hostname
4. Make sure username is lowercase: `administrator`

### Import errors
```bash
# Make sure you activated the venv
source /opt/caqh-reviewer/venv/bin/activate

# Reinstall dependencies if needed
pip install -r deploy/requirements-vm.txt
```

### Cron job not running
```bash
# Check if cron is enabled
crontab -l

# Check cron service status
systemctl status cron

# Check logs for errors
tail -50 /opt/caqh-reviewer/logs/cron_wrapper.log
```

### Need to update code
```bash
cd /opt/caqh-reviewer
git pull origin main
# Dependencies are already installed, but if new ones added:
source venv/bin/activate
pip install -r deploy/requirements-vm.txt
```

---

## Who to Contact

| Issue | Contact |
|-------|---------|
| VM access/credentials | Christian or Lyndrae |
| API endpoints/tokens | Hasan |
| VPN issues | PBS IT |
| Application bugs | Check docs/BUGS_TRACKING.md |

---

*Last Updated: December 22, 2025*
