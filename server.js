const express      = require('express');
const multer       = require('multer');
const path         = require('path');
const fs           = require('fs');
const { spawn }    = require('child_process');

const app = express();

// Ensure directories exist on startup
['uploads', 'hls', 'public'].forEach(d => fs.mkdirSync(d, { recursive: true }));

// ── Job state ──────────────────────────────────────────────────────────────
const jobs  = {};  // jobId → { status, message?, masterUrl? }
const queue = [];  // pending { jobId, inputPath }
let activeFfmpeg = null;

function startNextJob() {
  if (activeFfmpeg || queue.length === 0) return;
  const { jobId, inputPath } = queue.shift();
  processVideo(jobId, inputPath);
}

function processVideo(jobId, inputPath) {
  jobs[jobId].status = 'processing';
  fs.mkdirSync(`hls/${jobId}/360p`, { recursive: true });
  fs.mkdirSync(`hls/${jobId}/720p`, { recursive: true });

  let stderr = '';
  const ff = spawn('ffmpeg', [
    '-i', inputPath,
    // 360p
    '-map', '0:v:0', '-map', '0:a:0',
    '-c:v', 'libx264', '-b:v', '500k',  '-s', '640x360',
    '-c:a', 'aac',     '-b:a', '96k',
    '-f', 'hls', '-hls_time', '4', '-hls_playlist_type', 'vod',
    '-hls_segment_filename', `hls/${jobId}/360p/seg%03d.ts`,
    `hls/${jobId}/360p/index.m3u8`,
    // 720p
    '-map', '0:v:0', '-map', '0:a:0',
    '-c:v', 'libx264', '-b:v', '2500k', '-s', '1280x720',
    '-c:a', 'aac',     '-b:a', '128k',
    '-f', 'hls', '-hls_time', '4', '-hls_playlist_type', 'vod',
    '-hls_segment_filename', `hls/${jobId}/720p/seg%03d.ts`,
    `hls/${jobId}/720p/index.m3u8`,
  ]);

  activeFfmpeg = ff;
  ff.stderr.on('data', d => { stderr += d; });

  ff.on('close', code => {
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
      console.log(`[done] ${jobId}`);
    } else {
      jobs[jobId] = { status: 'error', message: stderr.slice(-300) };
      console.error(`[fail] ${jobId} (exit ${code})`);
    }
    fs.unlink(inputPath, () => {});  // delete raw upload
    startNextJob();
  });

  console.log(`[proc] ${jobId}`);
}

// ── Static serving ─────────────────────────────────────────────────────────
app.use('/',    express.static('public'));
app.use('/hls', express.static('hls'));

// ── Routes ─────────────────────────────────────────────────────────────────
app.post('/upload', multer({
  storage: multer.diskStorage({
    destination: 'uploads/',
    filename: (req, file, cb) => cb(null, file.originalname),
  }),
  limits: { fileSize: 500 * 1024 * 1024 },
  fileFilter: (req, file, cb) => {
    const ok = ['.mp4', '.mov', '.avi', '.mkv'].includes(
      path.extname(file.originalname).toLowerCase()
    );
    cb(null, ok);
  },
}).single('video'), (req, res) => {
  if (!req.file) return res.status(400).json({ error: 'No valid video file received' });
  const jobId = path.parse(req.file.filename).name.replace(/[^a-zA-Z0-9_-]/g, '_');
  jobs[jobId] = { status: 'pending' };
  queue.push({ jobId, inputPath: req.file.path });
  startNextJob();
  res.json({ jobId });
});

app.get('/status/:jobId', (req, res) => {
  const job = jobs[req.params.jobId];
  if (!job) return res.status(404).json({ error: 'Job not found' });
  res.json(job);
});

app.get('/videos', (req, res) => {
  res.json(Object.keys(jobs).filter(id => jobs[id].status === 'ready'));
});

// ── Start ──────────────────────────────────────────────────────────────────
app.listen(3000, () => console.log('Server listening on http://localhost:3000'));
process.on('exit', () => { if (activeFfmpeg) activeFfmpeg.kill(); });
