# NetStream — Setup Guide

## First Time Setup

### Step 1 — Run the Windows script (PowerShell as Administrator)

Right-click PowerShell → **Run as administrator**, then:

```powershell
cd C:\Users\<you>\Desktop\Projects\CN_Finalpj\setup
.\setup.ps1
```

This installs WSL2 and Ubuntu automatically. If a restart is required, restart and continue from Step 2.

### Step 2 — Complete Ubuntu first-time setup

After restart, Ubuntu opens and asks for a username and password. Set these. The password will not be visible as you type — this is normal.

### Step 3 — Run the Linux setup script

Inside the Ubuntu terminal:

```bash
bash /mnt/c/Users/<you>/Desktop/Projects/CN_Finalpj/setup/setup.sh
```

This installs Node.js, FFmpeg, copies the project to `~/netstream`, and runs `npm install`. Wait for it to finish.

### Step 4 — Verify

```bash
node --version     # should show v20 or higher
ffmpeg -version    # should show any version output
```

---

## Starting the Server (Every Session)

Each time you restart your computer, open WSL2 and run:

```bash
cd ~/netstream
node server.js
```

You should see: `Server listening on http://localhost:3000`

Open Chrome and go to `http://localhost:3000` to confirm it is working.

---

## Running a Network Experiment

You need two WSL2 terminals open at the same time.

**Terminal 1** — keep the server running the entire time:
```bash
cd ~/netstream
node server.js
```

**Terminal 2** — apply and clear network profiles between runs:
```bash
cd ~/netstream
sudo ./network/netem.sh baseline    # no impairment
sudo ./network/netem.sh latency     # 150ms delay
sudo ./network/netem.sh loss        # 3% packet loss
sudo ./network/netem.sh congested   # 1.5 Mbps cap + 200ms delay + 2% loss
sudo ./network/netem.sh clear       # remove all rules when done
```

---

## Syncing Changes from Windows to WSL2

If you edit any project file on the Windows side, sync it to WSL2 before running:

```bash
cp -r /mnt/c/Users/<you>/Desktop/Projects/CN_Finalpj/* ~/netstream/
```

---

## Regenerating Charts

After collecting new CSV files, move them to the `data/` folder then run:

```bash
cd /mnt/c/Users/<you>/Desktop/Projects/CN_Finalpj/data
python3 charts.py
```

This reads the 4 CSV files and saves a new `charts.png`.
