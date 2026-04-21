# NetStream — Project Explanation

**Project name:** NetStream
**Topic:** Computer Networks — Adaptive Bitrate Streaming under Network Degradation
**Author:** KSVKORD
**Date:** April 2025

---

## What This Project Is About

Every time you watch a video on YouTube, Netflix, or any streaming platform, the video quality adjusts automatically. When your internet is fast, you get crisp 1080p or 4K. When it slows down, the video drops to a lower resolution like 360p or 480p, so it keeps playing instead of buffering.

Most people have noticed this happening, but very few know the mechanism behind it. This project builds a complete video streaming server from scratch, then deliberately degrades the network connection in four different ways to measure exactly when and why the streaming quality changes.

The central question is: do all types of network problems cause quality drops, or only specific ones?

---

## Background: How Video Streaming Works

When you stream a video, the file is not sent to you all at once. Instead, it is cut into short **segments** — small pieces of video, each a few seconds long — and your device downloads them one at a time, playing them back in sequence. In this project each segment is 4 seconds long. While you are watching segment 3, the player is already downloading segment 5 or 6.

The segments that have been downloaded but not yet played are stored in the **buffer** — a temporary holding area of ready-to-play video that acts as a cushion against short connection slowdowns. If your connection hiccups for 2 seconds but you have 20 seconds buffered, you never notice. Only when the buffer runs empty does the video freeze and show a loading spinner.

---

## Background: Bitrate and Quality Tiers

**Bitrate** is the amount of data per second a video needs in order to play at a given resolution — higher resolution means more data per second. This project uses two quality tiers:

- **360p (low quality):** 500 kbps — about 60 kilobytes per second
- **720p (high quality):** 2,500 kbps — about 300 kilobytes per second

If the network can only deliver 1,000 kbps, it is mathematically impossible to play 720p without buffering. The segments would download slower than they are being played, and the buffer would eventually drain.

The threshold of 2,500 kbps is the critical number for this entire experiment. Any network condition that keeps measured throughput above 2,500 kbps should leave video quality unchanged. Any condition that drops it below 2,500 kbps should force the player to switch to 360p.

---

## Background: Adaptive Bitrate Streaming and HLS

**Adaptive Bitrate Streaming (ABR)** is a system where the video player automatically picks the highest quality the current internet speed can support, and switches up or down as conditions change — with no input from the viewer.

**HLS (HTTP Live Streaming)** is a video delivery format, originally designed by Apple, that makes ABR possible by encoding a video into multiple quality versions and splitting each version into small segment files. A text file called the **master playlist** lists all available quality versions and the bandwidth each one requires. When the player opens a stream, it reads the master playlist, picks a quality version to start downloading, and after each segment arrives, measures how long the download took to estimate current bandwidth. If the estimate falls below what the current quality version needs, it switches to a lower quality for the next segment. If bandwidth improves, it switches back up.

**hls.js** is an open-source JavaScript library that implements the full HLS player inside any web browser, handling all segment fetching, quality switching, and buffering automatically. This is the player used in this project.

---

## Background: Types of Network Problems

Not all network problems affect throughput the same way. This project tests three types:

**Latency** is the time a packet takes to travel from server to client — high latency means packets arrive late, slowing the start of each segment download, but not reducing the total amount of data that can be delivered. Once the data starts arriving, it flows at full speed. Latency does not cap throughput; it only delays when each segment begins.

**Packet loss** means some data packets are dropped by the network and never arrive. **TCP (Transmission Control Protocol)** — the standard internet protocol that guarantees all data eventually arrives by automatically detecting and retransmitting lost packets — handles this transparently. The client receives all the data, but the retransmissions take extra time. The loss is invisible at the application level as long as retransmissions complete before the buffer runs out.

**Bandwidth cap** is a hard limit on how many bits per second can pass through a connection. Unlike latency or loss, a cap directly restricts throughput. There is no way to compensate for it. If the cap is lower than what a quality tier requires, that tier simply cannot be delivered on time, regardless of how much buffering or retransmission is attempted.

---

## Background: tc netem

**tc netem (Traffic Control Network Emulator)** is a Linux kernel tool that injects artificial delay, packet loss, or speed limits into a network connection so network conditions can be tested reproducibly. Because it operates at the kernel level, TCP and all higher-level protocols see these conditions as genuine — the behavior is identical to a real degraded connection.

In this project, tc netem runs inside **WSL2 (Windows Subsystem for Linux 2)** — a feature of Windows 11 that runs a full Linux environment inside Windows without needing a separate virtual machine. The streaming server also runs inside WSL2, and the browser runs in Windows Chrome. Network conditions are applied to the loopback interface inside WSL2, which is the path all Chrome-to-server traffic travels through.

---

## Project Goal

Build a complete HLS video streaming system, apply four different network conditions using tc netem, measure how the adaptive bitrate player responds to each one, and determine: which types of network problems actually cause quality changes, and which ones does the system absorb without any change to the viewer's experience?

---

## Project Roadmap

The project was built in four sequential phases. Each phase had a set of gate requirements — specific checks that had to pass before the next phase could begin.

| Phase | Name | Goal | Gate |
|-------|------|------|------|
| 1 | Infrastructure | Server accepts file uploads | POST /upload returns 200 with jobId |
| 2 | Streaming Pipeline | FFmpeg encodes video to HLS | /status/:id returns "ready" with segments present |
| 3 | Client Interface | Browser player with live stats panel | Video plays, stats update every second |
| 4 | Network Experiment | tc netem profiles applied and verified | Segment timings change in DevTools per profile |

---

## Phase 1: Infrastructure

**Node.js** is a JavaScript runtime that lets you run JavaScript code on a server, outside the browser. **Express** is a Node.js web framework — a library that makes it easy to define HTTP routes and handle requests. **multer** is a Node.js library that handles file uploads sent from a browser form. These three form the foundation of the server.

The server creates three directories on startup: `uploads/` for raw video files, `hls/` for processed streaming files, and `public/` for the browser frontend.

**nvm (Node Version Manager)** is a tool for installing and switching between Node.js versions — used here to install Node.js v24.15.0 inside WSL2 instead of the outdated version available through the system package manager.

**FFmpeg** is a command-line program that converts, encodes, and processes video files — it is what transforms the uploaded video into HLS segments. FFmpeg 6.1.1 was installed inside WSL2 via apt.

The server exposes:
- `GET /` — serves the frontend pages
- `POST /upload` — accepts a video file, saves it to `uploads/`, returns a job ID
- Static serving of `/hls/` so the browser can fetch video segments directly

**Gate result:**
- `node --version` → v24.15.0
- `ffmpeg -version` → version 6.1.1
- `GET /` → HTTP 200
- `POST /upload` with a test video → `{"jobId":"test"}`, file saved to uploads/

---

## Phase 2: Streaming Pipeline

**FFmpeg** is invoked using Node.js's `child_process.spawn()` — a function that starts an external program and streams its output instead of buffering it all in memory. Using `exec()` instead would buffer all FFmpeg terminal output in memory; a long video generates enough output to overflow the default buffer and crash the server. `spawn()` avoids this.

A single FFmpeg command encodes both renditions simultaneously:
- 360p at 500 kbps, 4-second segments, saved to `hls/{jobId}/360p/`
- 720p at 2,500 kbps, 4-second segments, saved to `hls/{jobId}/720p/`

The video codec used is **libx264** — a software-based encoder that compresses video using the H.264 standard, running entirely on the CPU. Hardware encoding is not available inside WSL2 because WSL2 does not have direct access to GPU encoding units.

An in-memory job map tracks each upload through states: `pending → processing → ready → error`. A job queue ensures only one FFmpeg process runs at a time — without this, two simultaneous uploads would write to overlapping output paths.

When FFmpeg finishes, the server writes the **master playlist** (`master.m3u8`) — a plain text file that lists all available quality versions and the bandwidth each one requires, which hls.js reads first when the player loads.

The raw uploaded file is deleted after processing regardless of success or failure.

**HLS output structure after encoding:**
```
hls/
└── ow2/
    ├── master.m3u8
    ├── 360p/
    │   ├── index.m3u8
    │   ├── seg000.ts
    │   └── ...
    └── 720p/
        ├── index.m3u8
        ├── seg000.ts
        └── ...
```

**master.m3u8 content:**
```
#EXTM3U
#EXT-X-VERSION:3
#EXT-X-STREAM-INF:BANDWIDTH=500000,RESOLUTION=640x360
360p/index.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=2500000,RESOLUTION=1280x720
720p/index.m3u8
```

hls.js reads this file first. The BANDWIDTH values are what it compares against its measured download speed to decide which tier to request.

**Gate result:**
- Upload ow2.mp4 → `{"jobId":"ow2"}`
- Poll `/status/ow2` → `{"status":"processing"}` then `{"status":"ready"}`
- `ls hls/ow2/` → 360p/, 720p/, master.m3u8 all present
- `ls uploads/` → empty after encoding completes

---

## Phase 3: Client Interface

**Upload page (index.html):**
The page sends the file using the **Fetch API** — a browser built-in for making HTTP requests from JavaScript — with a FormData object. Once the server responds with a job ID, the page polls `GET /status/:jobId` every 3 seconds, capped at 40 attempts (2 minutes maximum). Without this cap, a failed encoding job would leave the browser polling forever with no feedback. When ready, the video appears in a library list with a link to the player page.

**Player page (player.html):**
hls.js is loaded from a **CDN (Content Delivery Network)** — a globally distributed network of servers that hosts JavaScript libraries so they load fast without being bundled into the project. hls.js reads the master playlist URL, fetches segments, handles quality switching, and manages the buffer — all automatically.

A stats panel updates every 1 second displaying:
- **Current quality level** — which rendition hls.js is currently downloading (360p or 720p)
- **Bandwidth estimate (kbps)** — hls.js's running measurement of available download speed
- **Buffer length (seconds)** — how much video is downloaded and ready to play ahead of the current position
- **Total quality switches** — how many times hls.js changed quality tiers during the session
- **Total buffer stalls** — how many times the buffer ran empty and playback froze
- **Elapsed playback time** — how long the video has been playing

The video has the `loop` attribute so it repeats automatically, since the test clip is shorter than the 3-minute observation window.

An auto-recorder captures a snapshot of all six stats every 30 seconds for 3 minutes (6 samples total) and exports the results as a **CSV file** — a plain text format where each row is one time sample and each column is one measurement.

**Gate result:**
- Upload → polling → player opens → video plays in Chrome
- Stats panel updates every second during playback
- After 3 minutes, CSV downloads with 6 rows of data

---

## Phase 4: Network Experiment

**netem.sh** is a shell script that wraps the tc netem commands into a simple one-argument interface. It targets the loopback interface (`lo`) inside WSL2 and clears any existing rules before applying a new profile.

| Profile | Delay | Packet Loss | Bandwidth Cap |
|---------|-------|-------------|---------------|
| baseline | 0 ms | 0% | none |
| latency | 150 ms | 0% | none |
| loss | 0 ms | 3% | none |
| congested | 50 ms | 1% | 1.5 Mbps |

**Critical discovery during setup:**
The initial script targeted **eth0** — the standard virtual network adapter that WSL2 uses to communicate with Windows. After applying the latency profile, Chrome's segment download times did not change. Testing confirmed eth0 itself was being affected, but Chrome traffic was not.

The diagnosis: WSL2 with `systemd=true` in `/etc/wsl.conf` uses **mirrored networking mode** — a WSL2 feature where the loopback address `127.0.0.1` in Windows is mapped directly to the same loopback inside WSL2. Chrome connecting to `localhost:3000` from Windows sends traffic through the **loopback interface (`lo`)** — a virtual network adapter that connects a machine to itself — inside WSL2, bypassing eth0 entirely. Fix: changed the target interface from eth0 to lo.

A second issue: adding a port filter (so only port 3000 traffic was affected) stopped working after the interface switch. The likely reason is that Chrome connects via **IPv6** (`::1`) — the newer internet addressing standard — rather than IPv4 (`127.0.0.1`), but the filter used IPv4-only syntax. Fix: removed the port filter, applying netem rules to all loopback traffic.

After both fixes, segment download times in Chrome **DevTools** — the browser's built-in developer panel — changed visibly per profile and normalized when cleared.

**Data collection procedure:**
Each run followed the same steps:
1. Restart the server to clear in-memory state
2. Upload the test video, wait for processing
3. Open the player page with browser cache disabled
4. Apply the network profile
5. Click play and start the auto-recorder immediately
6. Keep the browser tab active and in the foreground (background tabs throttle JavaScript timers, corrupting the 1-second update interval)
7. After 3 minutes, the CSV downloads automatically
8. Clear the profile, wait 30 seconds before the next run

---

## Results

Six samples were collected per profile across 4 profiles, giving 24 total data points.

**Quality level over time:**

| Profile | t=30s | t=60s | t=90s | t=120s | t=150s | t=180s |
|---------|-------|-------|-------|--------|--------|--------|
| Baseline | 720p | 720p | 720p | 720p | 720p | 720p |
| High Latency | 720p | 720p | 720p | 720p | 720p | 720p |
| Packet Loss | 720p | 720p | 720p | 720p | 720p | 720p |
| Congested | 360p | 360p | 360p | 360p | 360p | 360p |

**Bandwidth estimate (same across all samples within each profile):**

| Profile | Measured Bandwidth | Ratio vs 720p threshold |
|---------|-------------------|------------------------|
| Baseline | 369,257 kbps | 148x above threshold |
| High Latency | 69,755 kbps | 28x above threshold |
| Packet Loss | 207,238 kbps | 83x above threshold |
| Congested | 1,501 kbps | 0.6x — below threshold |

Buffer stalls: 0 across all profiles and all time points.

The two charts (`data/charts.png`) visualize this data. Because the bandwidth values span a 250-to-1 range, the left chart uses a **logarithmic scale** — a scale where each step represents a multiplication rather than an addition, making very large and very small values readable on the same chart. The dashed line at 2,500 kbps marks the minimum bandwidth required for 720p. Three profiles sit far above it; one sits below.

---

## Analysis

**Why latency did not cause a quality drop:**
Adding 150ms of delay reduced the measured bandwidth from 369,257 kbps to 69,755 kbps — an 80% reduction. Despite this, 69,755 kbps is still 28 times the 2,500 kbps threshold for 720p. hls.js had no reason to switch quality. Latency slows when each segment starts arriving, but not the speed at which data flows once transmission begins. The player's buffer absorbed the slower segment starts without difficulty.

**Why packet loss did not cause a quality drop:**
3% packet loss reduced measured bandwidth from 369,257 kbps to 207,238 kbps — a 44% reduction. Again, 207,238 kbps is 83 times the 720p threshold. TCP detected every dropped packet and retransmitted it. Every segment arrived complete. The retransmissions added variable extra time to some downloads, reducing the bandwidth estimate, but the estimate remained far above the threshold. Zero stalls, zero quality switches.

**Why congestion caused a quality drop:**
The congested profile applied a hard cap at 1,500 kbps. The 720p tier requires 2,500 kbps. These two numbers are incompatible — no retransmission or buffering can push 2,500 kbps worth of data through a 1,500 kbps pipe. hls.js measured 1,501 kbps, recognized it was below the 720p threshold, and selected 360p before the first 30-second sample was taken. Quality stayed at 360p for all six samples with no switches and no stalls. 360p requires only 500 kbps, which the 1,500 kbps cap handles comfortably.

---

## Key Finding

| Profile | Network Degraded? | Quality Changed? | Why |
|---------|-------------------|-----------------|-----|
| High Latency | Yes | No | Bandwidth still 28x above threshold |
| Packet Loss | Yes | No | TCP retransmissions hid the loss |
| Congested | Yes | Yes | Hard cap fell below 720p minimum |

Adaptive bitrate streaming is not sensitive to network degradation in general. It is specifically sensitive to whether available bandwidth falls below the minimum required for the current quality tier. Latency and packet loss are forms of degradation that TCP compensates for — data eventually arrives, just more slowly. A bandwidth cap cannot be compensated for. The ABR algorithm responds to it by selecting a lower quality tier that fits within the ceiling.

---

## Technical Challenges

| Problem | Root Cause | Fix |
|---------|-----------|-----|
| netem had no effect on Chrome | WSL2 mirrored networking — Chrome uses loopback (`lo`), not eth0 | Changed target interface from eth0 to lo |
| tc port filter ineffective | Chrome uses IPv6 (`::1`); filter was IPv4 only | Removed port filter, applied netem to all loopback traffic |
| Server crash on large video upload | `exec()` buffers all FFmpeg output in memory, overflowing the default limit | Switched to `spawn()` which streams output without storing it |
| Polling loop never stops on FFmpeg failure | No exit condition in original design | Added MAX_POLLS = 40 (2-minute ceiling) |
| Special characters in filenames break output paths | Filenames used directly as directory names | Sanitized job ID: replace non-alphanumeric characters with underscore |

---

## Limitations

The experiment was conducted on a single machine using loopback networking. All traffic traveled within the same computer, eliminating real-world factors including routing across multiple network hops, physical link instability, and congestion from other users sharing the same connection.

The controlled environment is a strength for reproducibility, but the findings describe how the ABR algorithm responds to idealized network conditions, not the unpredictable noise of a real internet connection.

Only two quality tiers were tested. Real streaming platforms offer 4 to 6 tiers with finer granularity — more intermediate steps between low and high quality. Only one video clip was tested, short enough to require looping during the 3-minute observation window.

---

## Full Data Table

| Profile | t (s) | quality | bw_kbps | buffer_s | switches | stalls | elapsed_s |
|---------|-------|---------|---------|----------|----------|--------|-----------|
| baseline | 30 | 720p | 369,257 | 16.2 | 1 | 0 | 30.5 |
| baseline | 60 | 720p | 369,257 | 33.0 | 3 | 0 | 13.7 |
| baseline | 90 | 720p | 369,257 | 3.0 | 3 | 0 | 43.7 |
| baseline | 120 | 720p | 369,257 | 19.7 | 5 | 0 | 27.0 |
| baseline | 150 | 720p | 369,257 | 36.5 | 7 | 0 | 10.2 |
| baseline | 180 | 720p | 369,257 | 6.5 | 7 | 0 | 40.2 |
| latency | 30 | 720p | 69,755 | 17.3 | 1 | 0 | 29.3 |
| latency | 60 | 720p | 69,755 | 34.1 | 3 | 0 | 12.6 |
| latency | 90 | 720p | 69,755 | 4.1 | 3 | 0 | 42.6 |
| latency | 120 | 720p | 69,755 | 20.9 | 5 | 0 | 25.8 |
| latency | 150 | 720p | 69,755 | 37.6 | 7 | 0 | 9.1 |
| latency | 180 | 720p | 69,755 | 7.6 | 7 | 0 | 39.1 |
| loss | 30 | 720p | 207,238 | 16.4 | 1 | 0 | 30.3 |
| loss | 60 | 720p | 207,238 | 33.1 | 3 | 0 | 13.6 |
| loss | 90 | 720p | 207,238 | 3.1 | 3 | 0 | 43.6 |
| loss | 120 | 720p | 207,238 | 19.9 | 5 | 0 | 26.8 |
| loss | 150 | 720p | 207,238 | 36.6 | 7 | 0 | 10.0 |
| loss | 180 | 720p | 207,238 | 6.6 | 7 | 0 | 40.1 |
| congestion | 30 | 360p | 1,501 | 16.3 | 0 | 0 | 30.4 |
| congestion | 60 | 360p | 1,501 | 33.0 | 0 | 0 | 13.7 |
| congestion | 90 | 360p | 1,501 | 3.0 | 0 | 0 | 43.7 |
| congestion | 120 | 360p | 1,501 | 19.8 | 0 | 0 | 26.9 |
| congestion | 150 | 360p | 1,501 | 36.5 | 0 | 0 | 10.1 |
| congestion | 180 | 360p | 1,501 | 6.6 | 0 | 0 | 40.1 |

**Chart file:** `data/charts.png`
- Left panel: bandwidth estimate per profile on a log scale, dashed line at 2,500 kbps
- Right panel: quality outcome per profile (720p vs 360p)
