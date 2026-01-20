# Quick Setup Guide - Cloud Relay Server

## What We're Doing:
Instead of direct connection, we use a cloud relay server:
- Lab → Relay Server → Workshop
- Workshop → Relay Server → Lab

## Step 1: Deploy Relay Server (Choose One Method)

### Method A: Render.com (Easiest - No Git Required)

1. Go to https://dashboard.render.com/
2. Sign up with GitHub (free)
3. Click "New +" → "Web Service"
4. Choose "Public Git repository"
5. Paste: `https://github.com/YOUR_USERNAME/vehicle-control-relay` (you'll create this)
6. Or use Render's "Deploy from GitHub" after pushing code

### Method B: Quick Test Locally First

Before deploying, test the relay server locally:

**Terminal 1 - Relay Server:**
```bash
python relay_server.py
```

**Terminal 2 - Workshop:**
```bash
python workshop_relay_client.py
```
(Update config.py: `WORKSHOP_IP = "127.0.0.1"`, `SERVER_PORT = 8080`)

**Terminal 3 - Lab:**
```bash
python lab_relay_client.py
```
(Update config.py: `WORKSHOP_IP = "127.0.0.1"`, `SERVER_PORT = 8080`)

If this works locally, deploy to cloud!

## Step 2: Deploy to Render.com

**Option 1: Using GitHub**

```bash
cd d:\software-projects-all\cloud

# Initialize git
git init
git add relay_server.py requirements.txt Procfile runtime.txt
git commit -m "Add relay server"

# Create repo on GitHub, then:
git remote add origin https://github.com/YOUR_USERNAME/vehicle-control-relay.git
git push -u origin main
```

Then on Render.com:
- Connect your GitHub repo
- Deploy automatically

**Option 2: Without GitHub (Manual)**

1. Copy `relay_server.py`, `requirements.txt`, `Procfile`, `runtime.txt` to a new folder
2. Zip the folder
3. Use Render's manual deployment option

## Step 3: Get Your Relay URL

After deployment, Render gives you a URL like:
`https://vehicle-control-relay.onrender.com`

## Step 4: Update Config

Update `config.py` on BOTH lab and workshop PCs:

```python
WORKSHOP_IP = "vehicle-control-relay.onrender.com"
SERVER_PORT = 443
```

## Step 5: Run

**Workshop PC:**
```bash
python workshop_relay_client.py
```

**Lab PC:**
```bash
python lab_relay_client.py
```

Both will connect to the relay server, and data will flow through it!

## Expected Latency:
- Local test: 1-5ms
- Cloud relay: 50-150ms (depends on Render server location)

## Troubleshooting:

**If relay server crashes:**
- Check Render logs
- Make sure `requirements.txt` has `websockets`

**If clients can't connect:**
- Make sure relay server is running (check Render dashboard)
- Verify URL is correct (no `https://`, just the domain)
- Check `SERVER_PORT = 443`

## Files You Need:
- `relay_server.py` - Deploy this to Render
- `workshop_relay_client.py` - Run on workshop PC
- `lab_relay_client.py` - Run on lab PC
- `config.py` - Same config on both PCs
- `requirements.txt` - For deployment
- `Procfile` - For deployment
- `runtime.txt` - For deployment
