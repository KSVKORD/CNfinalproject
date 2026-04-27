# NetStream — Project Roadmap
**Goal:** Build a video streaming web app, then use tc netem to simulate degraded network conditions and observe how the stream responds.  
**Stack:** Node.js, Express, plain HTML/CSS/JS, FFmpeg, hls.js  
**Frontend:** Minimal — functional only, no styling frameworks  
**Environment:** Windows 11, AMD GPU. Node.js and tc run inside Ubuntu WSL2. Playback tested in Windows Chrome.

---

## Phases

```
Phase 1 — Infrastructure       (environment + server scaffold)
Phase 2 — Streaming Pipeline   (FFmpeg + HLS + job system)
Phase 3 — Client Interface     (frontend + stats panel)
Phase 4 — Network Experiment   (tc netem + data collection + analysis + presentation)
```

Each phase has a gate. Do not start the next phase until the gate passes.

---

## Phase 1 — Infrastructure

**Goal:** Working HTTP server that accepts a file upload and saves it. Nothing streaming yet.

### 1.1 WSL2 environment

- Confirm WSL2 is VERSION 2: `wsl --list --verbose`
  - If it shows VERSION 1, run `wsl --set-version Ubuntu 2` before continuing
  - WSL1 has no real Linux kernel — tc netem will not work on WSL1
- Install Node.js via nvm (not apt — apt ships an outdated v12):
  - Install nvm from the nvm GitHub install script
  - `nvm install --lts`
  - Verify: `node --version` → v20 or higher
- Install FFmpeg: `sudo apt update && sudo apt install ffmpeg`
  - Verify: `ffmpeg -version`
  - This installs the CPU build — correct for WSL2 (see Phase 2 for the AMD GPU note)

### 1.2 Project scaffold

Create the project inside the WSL2 filesystem at `~/netstream`. Do not use `/mnt/c/` — WSL2 I/O through the Windows mount is significantly slower and will affect FFmpeg encoding speed.

```
~/netstream/
  server.js
  public/       ← static frontend files served here
  uploads/      ← raw uploaded videos saved here (temporary staging)
  hls/          ← processed HLS output served from here
```

```bash
npm init -y
npm install express multer
```

### 1.3 Express server

Configure `server.js`:

- `express.static('public')` mounted at `/`
- `express.static('hls')` mounted at `/hls` — this is how the browser fetches HLS segments
- Multer with `diskStorage`:
  - `destination`: must be set explicitly to `uploads/`. If destination is omitted, multer saves to the system temp directory and the file will not be where the processing function expects it.
  - `filename`: preserve the original filename
  - `limits.fileSize`: `500 * 1024 * 1024` (500 MB) — the default limit rejects most video files
  - `fileFilter`: accept mp4, mov, avi, mkv only
- `POST /upload`: apply multer middleware, respond `{ jobId: req.file.filename }`
- Listen on port 3000

WSL2 automatically forwards port 3000 to Windows — Chrome can reach `localhost:3000` without manual configuration. If Chrome cannot connect, check Windows Defender Firewall → Allow an app → confirm Node.js is listed and allowed.

### Gate — Phase 1

- `POST /upload` with a test `.mp4` → HTTP 200, file appears in `uploads/`
- `GET /` serves a test HTML page in Chrome at `localhost:3000`
- Server restarts cleanly with no errors

---

## Phase 2 — Streaming Pipeline

**Goal:** Upload triggers FFmpeg, produces two HLS renditions (360p and 720p), generates `master.m3u8`, propagates job status and errors to the client through a job map.

### AMD GPU — why it is not used

AMD GPU hardware encoding (`h264_amf`) is a Windows-native API. WSL2 runs a Linux kernel and cannot access Windows-native APIs. Running FFmpeg with `-c:v h264_amf` inside WSL2 fails immediately with "Encoder h264_amf not found." The correct encoder inside WSL2 is `-c:v libx264` (CPU software encoding). With a Ryzen 9800X3D, libx264 encodes a 5-minute video in roughly 30–60 seconds — fast enough that GPU encoding provides no practical benefit here.

### Why two tiers, not three

The congested profile in Phase 4 caps bandwidth at 1.5 Mbps. 720p requires 2500 kbps and 360p requires 500 kbps. A 1080p tier at 5000 kbps would never be selected under any test condition. Two tiers fully demonstrate ABR switching.

### 2.1 Job map

Add an in-memory map at module scope in `server.js`:

```js
const jobs = {};
// jobId → { status: 'pending' | 'processing' | 'ready' | 'error', message?, masterUrl? }
```

Upgrade `POST /upload`:
- Assign `jobId` from the saved filename (without extension)
- Set `jobs[jobId] = { status: 'pending' }`
- Push the job onto the queue and call `startNextJob()`
- Respond `{ jobId }`

Add `GET /status/:jobId`:
- Return `jobs[req.params.jobId]` as JSON
- This is the only way the client learns about async FFmpeg errors — the upload response is already gone by the time FFmpeg finishes. Errors must travel through `/status`, not the upload response.

Add `GET /videos`:
- Return a JSON array of all jobIds where `jobs[id].status === 'ready'`

### 2.2 Job queue

Process one FFmpeg job at a time:

```js
const queue = [];

function startNextJob() {
  const running = Object.values(jobs).some(j => j.status === 'processing');
  if (running || queue.length === 0) return;
  const { jobId, inputPath } = queue.shift();
  processVideo(jobId, inputPath);
}
```

On upload, push `{ jobId, inputPath }` onto `queue` and call `startNextJob()`. Without serialization, two simultaneous uploads spawn two FFmpeg processes that may write to overlapping paths.

### 2.3 Output directories

Before spawning FFmpeg, create both output directories:

```js
fs.mkdirSync(`hls/${jobId}/360p`, { recursive: true });
fs.mkdirSync(`hls/${jobId}/720p`, { recursive: true });
```

FFmpeg does not create missing directories — it fails with "no such file or directory" if they do not exist before encoding starts.

### 2.4 FFmpeg spawn — exact arguments

Use `child_process.spawn()`, never `exec()`. `exec()` buffers all FFmpeg stderr output in Node.js memory. A 5-minute video produces enough output to overflow the default buffer and crash the server. `spawn()` streams the output without buffering.

```js
const { spawn } = require('child_process');

let activeFfmpeg = null;

function processVideo(jobId, inputPath) {
  jobs[jobId].status = 'processing';
  let stderrBuffer = '';

  const ffmpeg = spawn('ffmpeg', [
    '-i', inputPath,

    // 360p rendition
    '-map', '0:v:0', '-map', '0:a:0',
    '-c:v', 'libx264', '-b:v', '500k', '-s', '640x360',
    '-c:a', 'aac', '-b:a', '96k',
    '-f', 'hls', '-hls_time', '4',
    '-hls_playlist_type', 'vod',
    '-hls_segment_filename', `hls/${jobId}/360p/seg%03d.ts`,
    `hls/${jobId}/360p/index.m3u8`,

    // 720p rendition
    '-map', '0:v:0', '-map', '0:a:0',
    '-c:v', 'libx264', '-b:v', '2500k', '-s', '1280x720',
    '-c:a', 'aac', '-b:a', '128k',
    '-f', 'hls', '-hls_time', '4',
    '-hls_playlist_type', 'vod',
    '-hls_segment_filename', `hls/${jobId}/720p/seg%03d.ts`,
    `hls/${jobId}/720p/index.m3u8`,
  ]);

  activeFfmpeg = ffmpeg;
  ffmpeg.stderr.on('data', d => { stderrBuffer += d.toString(); });

  ffmpeg.on('close', (code) => {
    activeFfmpeg = null;
    if (code === 0) {
      fs.writeFileSync(`hls/${jobId}/master.m3u8`, [
        '#EXTM3U',
        '#EXT-X-VERSION:3',
        '#EXT-X-STREAM-INF:BANDWIDTH=500000,RESOLUTION=640x360',
        '360p/index.m3u8',
        '#EXT-X-STREAM-INF:BANDWIDTH=2500000,RESOLUTION=1280x720',
        '720p/index.m3u8',
      ].join('\n') + '\n');
      jobs[jobId] = { status: 'ready', masterUrl: `/hls/${jobId}/master.m3u8` };
    } else {
      jobs[jobId] = { status: 'error', message: stderrBuffer.slice(-500) };
    }
    fs.unlink(inputPath, () => {});  // delete raw upload regardless of outcome
    startNextJob();
  });
}

// Kill any active FFmpeg process if the server shuts down
process.on('exit', () => { if (activeFfmpeg) activeFfmpeg.kill(); });
```

`master.m3u8` is written inside the `close` callback — the segments do not exist until FFmpeg exits, so the write cannot happen earlier.

### Gate — Phase 2

- Upload a `.mp4`, poll `GET /status/:jobId` until `ready`, open `hls/${jobId}/master.m3u8` — confirm it contains both rendition entries
- Upload a zero-byte or corrupt file — `GET /status/:jobId` returns `{ status: 'error' }` within ~10s
- After processing, `uploads/` is empty (raw file was deleted)
- Start two uploads back-to-back — second job remains `pending` until first completes

---

## Phase 3 — Client Interface

**Goal:** Two-page frontend. Upload page with bounded polling and error display. Player page with hls.js and a live stats panel.

### 3.1 index.html — upload form

- `<input type="file" accept="video/*">` and an upload button
- On click: `fetch('/upload', { method: 'POST', body: new FormData(form) })` → extract `jobId` from response
- Status div shows current state: `uploading` → `processing` → `ready` (or error text)
- Library list: each ready video is a link to `player.html?jobId=<jobId>`

### 3.2 index.html — bounded polling

```js
const MAX_POLLS = 40;  // 40 × 3 s = 2-minute maximum wait
let pollCount = 0;

function poll(jobId) {
  if (pollCount++ >= MAX_POLLS) {
    statusDiv.textContent = 'Processing timed out. Please retry.';
    return;
  }
  fetch(`/status/${jobId}`)
    .then(r => r.json())
    .then(({ status, message }) => {
      if (status === 'ready') {
        statusDiv.textContent = 'Ready';
        addToLibrary(jobId);
      } else if (status === 'error') {
        statusDiv.textContent = `Error: ${message}`;
      } else {
        setTimeout(() => poll(jobId), 3000);
      }
    });
}
```

Without `MAX_POLLS`, a failed job leaves the status div spinning indefinitely. The error branch surfaces the message stored in the job map by Phase 2's error handler.

### 3.3 player.html — hls.js player

- Load hls.js: `<script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>`
- Read `jobId` from `new URLSearchParams(location.search).get('jobId')`
- Construct `masterUrl = /hls/${jobId}/master.m3u8`

```js
if (Hls.isSupported()) {
  const hls = new Hls();
  hls.loadSource(masterUrl);
  hls.attachMedia(video);
} else if (video.canPlayType('application/vnd.apple.mpegurl')) {
  video.src = masterUrl;  // Safari native HLS
}
```

### 3.4 player.html — stats panel

A `<div>` updated every 1 second via `setInterval`:

| Stat | Source |
|---|---|
| Current quality | `hls.currentLevel` mapped to `360p` / `720p` |
| Bandwidth estimate | `hls.bandwidthEstimate / 1000` kbps |
| Buffer length | `video.buffered.end(0) - video.currentTime` seconds |
| Total quality switches | counter incremented on `Hls.Events.LEVEL_SWITCHED` |
| Total buffer stalls | counter incremented on `Hls.Events.ERROR` with buffer stall type |
| Elapsed playback time | `video.currentTime` seconds |

### Gate — Phase 3

- Upload → status div transitions through `processing` → `ready` → library link appears
- Click library link → `player.html` plays the video in Chrome
- Kill the server mid-processing → polling stops within 2 minutes with a timeout message
- Stats panel updates every second during playback; quality label changes when hls.js switches renditions

---

## Phase 4 — Network Experiment

**Goal:** Apply tc netem profiles to port 3000 on WSL2 eth0, collect stats across 4 profiles, produce comparison charts, and prepare the presentation.

### Background

tc netem is a Linux kernel tool that injects delay, loss, and bandwidth caps into a real network interface at the kernel level. TCP sees these as real — retransmissions, backoff, and congestion responses all behave as they would on an actual degraded network.

WSL2 runs on its own virtual adapter. Windows Chrome connects to the WSL2 server through WSL's `eth0` interface (the one with a `172.x.x.x` IP address). Applying tc rules to `lo` (loopback) has no effect on Chrome traffic. The target interface is always `eth0`.

Applying a global cap to `eth0` without a port filter also throttles npm and apt. Always filter to port 3000 only.

### Network profiles

| Profile | Delay | Packet Loss | Bandwidth Cap |
|---|---|---|---|
| Baseline | 0 ms | 0% | none |
| High Latency | 150 ms | 0% | none |
| Packet Loss | 0 ms | 3% | none |
| Congested | 200 ms ±30 ms jitter | 2% | 1.5 Mbps |

### 4.1 Verify tc and netem

```bash
tc qdisc show            # any output → tc is working; if not found: sudo apt install iproute2
sudo modprobe sch_netem  # must complete without error
# If modprobe fails: run 'wsl --update' from Windows PowerShell, then retry
```

### 4.2 Identify the correct interface

```bash
ip addr  # find the adapter with 172.x.x.x IP — this is eth0
```

### 4.3 netem.sh

```bash
#!/bin/bash
IFACE=eth0
PORT=3000
tc qdisc del dev $IFACE root 2>/dev/null  # clear any existing qdisc

case "$1" in
  baseline|clear)
    echo "Baseline: no impairment applied" ;;

  latency)
    tc qdisc add dev $IFACE root handle 1: prio priomap 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
    tc qdisc add dev $IFACE parent 1:3 handle 30: netem delay 150ms
    tc filter add dev $IFACE protocol ip parent 1:0 prio 3 u32 \
      match ip dport $PORT 0xffff flowid 1:3
    echo "High Latency: 150ms delay on port $PORT" ;;

  loss)
    tc qdisc add dev $IFACE root handle 1: prio priomap 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
    tc qdisc add dev $IFACE parent 1:3 handle 30: netem loss 3%
    tc filter add dev $IFACE protocol ip parent 1:0 prio 3 u32 \
      match ip dport $PORT 0xffff flowid 1:3
    echo "Packet Loss: 3% loss on port $PORT" ;;

  congested)
    # HTB enforces the bandwidth cap; netem adds delay and loss on top
    tc qdisc add dev $IFACE root handle 1: htb default 20
    tc class add dev $IFACE parent 1: classid 1:10 htb rate 1500kbit ceil 1500kbit
    tc class add dev $IFACE parent 1: classid 1:20 htb rate 100mbit
    tc qdisc add dev $IFACE parent 1:10 handle 10: netem delay 200ms 30ms loss 2%
    tc filter add dev $IFACE protocol ip parent 1:0 prio 1 u32 \
      match ip dport $PORT 0xffff flowid 1:10
    tc filter add dev $IFACE protocol ip parent 1:0 prio 2 u32 \
      match ip dst 0.0.0.0/0 flowid 1:20
    echo "Congested: 1.5 Mbps cap + 200ms delay (±30ms jitter) + 2% loss on port $PORT" ;;

  *) echo "Usage: $0 {baseline|latency|loss|congested|clear}"; exit 1 ;;
esac
```

The `congested` profile requires two layers: HTB (`htb`) enforces the 1.5 Mbps rate cap, and netem adds delay and loss on top. netem alone cannot cap bandwidth.

### 4.4 Verify each profile before collecting data

For each profile, run this sequence:
1. Apply: `sudo ./netem.sh <profile>`
2. Open the player in Chrome and start playback
3. Open DevTools → Network tab
4. Confirm `.ts` segment request timings reflect the applied condition:
   - `latency`: each segment request shows ~150ms additional TTFB
   - `loss`: occasional failed or retried requests visible
   - `congested`: segment downloads are visibly slower; quality may fall to 360p
5. `sudo ./netem.sh clear` → confirm timings return to normal

Do not proceed to data collection until all four profiles are confirmed working in Chrome.

### 4.5 Data collection procedure

Preparation:
- Have a single 5-minute test video already processed and ready in the library
- All four tc netem profiles verified working in Chrome
- Prepare one copy of the recording template per profile

One run per profile (4 runs total):
1. Restart Node.js: `Ctrl+C`, then `node server.js` — clears in-memory job state
2. Open `player.html` for the test video — do not press play yet
3. Apply the profile: `sudo ./netem.sh <profile>`
4. Press play. Keep the Chrome tab active and visible the entire time. Backgrounded tabs throttle JavaScript timers — the 1-second stats interval stretches to 5–10 seconds and corrupts the dataset.
5. Every 30 seconds, read all 6 stats panel values and record them
6. After 3 minutes, take a DevTools Network screenshot showing the segment request waterfall
7. `sudo ./netem.sh clear`. Wait 30 seconds before starting the next profile.

Recording template (one copy per profile):

```
Profile:
Start time:

t=30s:   quality=  bw=  buffer=  switches=  stalls=  elapsed=
t=60s:   quality=  bw=  buffer=  switches=  stalls=  elapsed=
t=90s:   quality=  bw=  buffer=  switches=  stalls=  elapsed=
t=120s:  quality=  bw=  buffer=  switches=  stalls=  elapsed=
t=150s:  quality=  bw=  buffer=  switches=  stalls=  elapsed=
t=180s:  quality=  bw=  buffer=  switches=  stalls=  elapsed=

Notable events (freezes, quality drops, recoveries):
DevTools screenshot: saved as <profile>.png
```

### 4.6 Analysis

**Baseline** (reference for all comparisons)
- What quality does it stabilize at and how quickly?
- What is the steady-state buffer length?

**High Latency (150ms)**
- Does uniform delay cause gradual, steady buffer drain or sudden spikes?
- How do switch count and buffer length compare to baseline?

**Packet Loss (3%)**
- When does the first buffer stall occur?
- TCP retransmissions from packet loss create unpredictable delay spikes — does stall count exceed the latency profile despite similar throughput reduction?
- Does the stream recover after stalls or continue degrading?

**Congested (200ms ±30ms jitter + 2% loss + 1.5 Mbps cap)**
- Does quality fall back from 720p to 360p? The 1.5 Mbps cap makes 720p's 2500 kbps requirement mathematically unreachable — the ABR controller should settle at 360p quickly and stay there.
- How quickly does the switch happen after playback starts?
- The 200ms delay with jitter distinguishes this profile from normal internet latency (60–80ms cross-continental) and reflects realistic congested queue behavior where buffer occupancy fluctuates unpredictably.

**Four comparison charts** (any tool: Excel, Google Sheets, or hand-drawn):
- Average quality level per profile (360p = 1, 720p = 2)
- Total quality switches per profile
- Total buffer stalls per profile
- Average buffer length per profile

### 4.7 Presentation structure

| Slide | Content |
|---|---|
| 1 | Problem: streaming quality depends on network conditions; localhost shows nothing interesting; tc netem injects real kernel-level conditions so TCP behaves as on a real degraded network |
| 2 | Architecture: upload → FFmpeg → HLS segments → netem → browser |
| 3 | System demo: show the player and live stats panel |
| 4–7 | Results — one slide per profile: conditions, recorded stats table, DevTools screenshot |
| 8 | Key finding: compare latency vs. loss profiles — same degradation level, different mechanisms, different stall and switch-frequency signatures |
| 9 | Charts: the four comparison plots |
| 10 | Limitations: single client, controlled lab conditions vs. real BGP routing variation and ISP-level congestion |

### Gate — Phase 4

- `sudo ./netem.sh congested` visibly slows segment downloads in Chrome DevTools; `sudo ./netem.sh clear` restores normal timings
- All 24 data points collected (6 observations × 4 profiles), no missing entries
- All 4 comparison charts produced with actual measured values
- Presentation slides reference real data, not placeholder text

---

## Final Deliverables Checklist

- [ ] WSL2 confirmed VERSION 2
- [ ] Node.js v20+ installed via nvm
- [ ] FFmpeg working inside WSL2
- [ ] Server starts cleanly, upload saves to `uploads/`
- [ ] Upload → FFmpeg → HLS playback works end to end
- [ ] Error states surface through `GET /status/:jobId`
- [ ] Stats panel updates every second during playback
- [ ] All four tc netem profiles verified in Chrome DevTools
- [ ] All four profiles tested with data recorded
- [ ] DevTools screenshot captured for each profile
- [ ] Four comparison charts produced
- [ ] Presentation complete with real data, findings, and limitations section

---

## Implementation Reports

---

### Phase 1 — Implementation Report

**Status:** Code complete. Environment setup required before running.

#### Files created

| File | Purpose |
|---|---|
| `server.js` | Express server — multer upload, static serving, `/upload` route |
| `package.json` | Project manifest with `express` and `multer` dependencies declared |
| `public/index.html` | Placeholder page served at `GET /` to verify server is running |
| `.gitignore` | Excludes `node_modules/`, `uploads/`, `hls/` from version control |

#### What the server does

- On startup: creates `uploads/`, `hls/`, `public/` directories if they don't exist
- `GET /` → serves `public/index.html` from the static `public/` directory
- `GET /hls/*` → serves HLS segment files (empty until Phase 2)
- `POST /upload` (field name: `video`) → multer saves the file to `uploads/`, responds `{ jobId }` where `jobId` is the filename without extension
- Invalid file type → `req.file` is undefined → `400 { error: "No valid video file received" }`

#### Code decisions

- `destination` in diskStorage is set explicitly — omitting it would send files to the OS temp directory, breaking Phase 2
- `fileFilter` uses `path.extname(...).toLowerCase()` so `.MP4` and `.mp4` are both accepted
- `mkdirSync` with `{ recursive: true }` is idempotent — safe to call on restart
- `path.parse(filename).name` strips the extension to produce a clean jobId for Phase 2

#### Environment setup required (manual — run inside WSL2 Ubuntu)

```bash
# 1. Verify WSL2 version (run from Windows PowerShell)
wsl --list --verbose          # must show VERSION 2

# 2. Install Node.js via nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
source ~/.bashrc
nvm install --lts
node --version                # must be v20+

# 3. Install FFmpeg
sudo apt update && sudo apt install ffmpeg
ffmpeg -version

# 4. Navigate to project and install dependencies
# Option A — project already accessible via Windows mount (fine for Phase 1):
cd /mnt/c/Users/EskoQin/Desktop/Projects/CN_Finalpj
# Option B — copy to WSL2 native filesystem (recommended before Phase 2 for FFmpeg speed):
cp -r /mnt/c/Users/EskoQin/Desktop/Projects/CN_Finalpj ~/netstream && cd ~/netstream

npm install
```

#### Gate verification commands (run inside WSL2 after setup)

```bash
# Start the server
node server.js
# Expected output: Server listening on http://localhost:3000

# In a second terminal — test GET /
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/
# Expected: 200

# Test POST /upload with a dummy .mp4 file
echo "test" > /tmp/test.mp4
curl -s -F "video=@/tmp/test.mp4" http://localhost:3000/upload
# Expected: {"jobId":"test"}

# Confirm the file was saved
ls uploads/
# Expected: test.mp4

# Test rejection of wrong file type
echo "test" > /tmp/test.txt
curl -s -F "video=@/tmp/test.txt" http://localhost:3000/upload
# Expected: {"error":"No valid video file received"}
```

#### Known limitation

`jobId` is derived from the original filename. A file named `my video.mp4` produces `jobId = "my video"` which contains a space. Phase 2 sanitizes filenames before using them as directory names.

---

### Phase 2 — Implementation Report

**Status:** Complete and gate-verified. Tested with `ow2.mp4` (Overwatch clip).

#### What was added to server.js

| Addition | Purpose |
|---|---|
| `jobs` map | In-memory state: `jobId → { status, message?, masterUrl? }` |
| `queue` array + `startNextJob()` | Serializes FFmpeg jobs — one at a time |
| `processVideo()` | Creates HLS output dirs, spawns FFmpeg, writes `master.m3u8` on success |
| `GET /status/:jobId` | Client polls this to track progress and surface errors |
| `GET /videos` | Returns all ready jobIds — used by the frontend library |

#### FFmpeg command structure

Single `spawn()` call with two outputs (360p and 720p) from one input pass. Both renditions use `-hls_playlist_type vod` which appends `#EXT-X-ENDLIST` to each playlist, signalling the stream is complete. Segment length is 4 seconds (`-hls_time 4`). Encoder is `libx264` — the only H.264 encoder available inside WSL2.

#### Key behaviors

- `activeFfmpeg` variable prevents two FFmpeg processes running simultaneously; checked in `startNextJob()`
- `master.m3u8` is written synchronously inside the `close` callback — guaranteed to happen only after all segments exist on disk
- Raw upload file is deleted with `fs.unlink()` unconditionally after FFmpeg exits (success or error)
- `jobId` is sanitized: `replace(/[^a-zA-Z0-9_-]/g, '_')` — prevents special characters in HLS directory paths

#### Gate results (actual output)

```
curl /upload        → {"jobId":"ow2"}
curl /status/ow2    → {"status":"processing"}  [during encode]
curl /status/ow2    → {"status":"ready","masterUrl":"/hls/ow2/master.m3u8"}
ls hls/ow2/         → 360p  720p  master.m3u8
cat master.m3u8     → both rendition entries with correct BANDWIDTH values
ls uploads/         → empty (raw file deleted)
```

---

### Phase 3 — Implementation Report

**Status:** Complete and gate-verified. Tested in Windows Chrome.

#### Files created

| File | Purpose |
|---|---|
| `public/index.html` | Upload form, bounded polling, video library |
| `public/player.html` | hls.js player, live stats panel |

#### index.html — key behaviors

- On page load: fetches `GET /videos` and populates the library with any already-ready videos
- Upload: `fetch('/upload')` with `FormData` → starts polling on success
- Polling: max 40 attempts × 3 s = 2-minute ceiling; stops on `ready`, `error`, or timeout
- `addToLibrary()` checks for duplicate entries by id before inserting

#### player.html — stats panel sources

| Stat | Source |
|---|---|
| Quality | `hls.currentLevel` mapped to `360p` / `720p` |
| Bandwidth | `hls.bandwidthEstimate / 1000` kbps |
| Buffer | `video.buffered.end(last) - video.currentTime` |
| Switches | counter on `Hls.Events.LEVEL_SWITCHED` |
| Stalls | counter on `Hls.Events.ERROR` with `BUFFER_STALLED_ERROR` |
| Elapsed | `video.currentTime` |

Stats update every 1 second via `setInterval`. Safari fallback uses native HLS (`video.src = masterUrl`).

#### Gate results (confirmed by user)

- Upload form → `Uploading...` → `Processing...` → `Ready.` ✓
- Library link appears, click opens `player.html` ✓
- Video plays in Chrome ✓
- Stats panel updates every second during playback ✓

---

## Platform Reference

| Concern | Answer |
|---|---|
| AMD GPU encoding in WSL2 | Not possible. `h264_amf` requires Windows-native AMF. Use `-c:v libx264` (CPU) only. |
| CPU encoding speed | Ryzen 9800X3D with libx264: a 5-minute video encodes in ~30–60 seconds. |
| tc netem availability | Ships with WSL2 kernel 5.10+. Verify with `sudo modprobe sch_netem`. Run `wsl --update` if missing. |
| Port forwarding | WSL2 auto-forwards port 3000 to Windows. No manual setup needed in most cases. |
| Windows Firewall | If Chrome cannot reach localhost:3000, confirm Node.js is allowed in Windows Defender Firewall. |
| Project files location | Keep project inside WSL2 filesystem (`~/netstream`), not under `/mnt/c/`. |
| Node.js installation | Use nvm inside WSL2, not apt. apt gives outdated versions. |
| Multer destination | Must be set explicitly in diskStorage config — omitting it sends files to system temp. |
| Multer file size | Set `limits.fileSize` to 500 MB — the default limit rejects most video files. |
| spawn vs exec | Always use `spawn()` for FFmpeg — `exec()` buffers stderr and crashes on large videos. |
| master.m3u8 timing | Write it inside the spawn `close` callback — segments do not exist before FFmpeg exits. |
| tc interface | Target `lo` (loopback), not `eth0` — WSL2 mirrored networking mode causes Chrome to connect via loopback, not eth0. |
| tc port filtering | Port filtering on `lo` does not work reliably (Chrome may use IPv6 `::1`). Apply netem to all loopback traffic. |
| Browser tab focus | Keep the Chrome tab active during data collection — backgrounded tabs throttle JS timers. |
