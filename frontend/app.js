// ── State ──
let currentStep = 1;
let sessionId = null;
let scriptData = null;

// ── Stepper Navigation ──

function goToStep(n) {
  currentStep = n;
  document.querySelectorAll('.step-panel').forEach(p => p.classList.remove('active'));
  document.getElementById(`step-${n}`).classList.add('active');

  document.querySelectorAll('.step-indicator').forEach(el => {
    const s = parseInt(el.dataset.step);
    el.classList.remove('active', 'done');
    if (s === n) el.classList.add('active');
    else if (s < n) el.classList.add('done');
  });
}

// ── Chip Selection ──

document.querySelectorAll('.chip-group').forEach(group => {
  group.querySelectorAll('.chip').forEach(chip => {
    chip.addEventListener('click', () => {
      group.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
    });
  });
});

function getChipValue(groupId) {
  const active = document.querySelector(`#${groupId} .chip.active`);
  return active ? active.dataset.val : null;
}

// ── Status Helpers ──

function showStatus(id, msg, type) {
  const el = document.getElementById(id);
  el.className = `status-bar ${type}`;
  el.innerHTML = type === 'info'
    ? `<span class="loader"></span>&nbsp; ${msg}`
    : msg;
}

function hideStatus(id) {
  const el = document.getElementById(id);
  el.className = 'status-bar';
  el.style.display = 'none';
}

// ── API Helper ──

async function apiPost(url, formData) {
  const resp = await fetch(url, { method: 'POST', body: formData });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(err.detail || 'Request failed');
  }
  return resp.json();
}

// ── Step 1: Script ──

async function generateScript() {
  const topic = document.getElementById('topic').value.trim();
  if (!topic) { alert('Enter a topic first'); return; }

  const tone = getChipValue('tone-chips') || 'comedy';
  const duration = document.getElementById('duration').value;
  const provider = document.getElementById('provider').value;

  showStatus('script-status', 'Generating script...', 'info');
  document.getElementById('script-result').style.display = 'none';

  try {
    const fd = new FormData();
    fd.append('topic', topic);
    fd.append('tone', tone);
    fd.append('duration', duration);
    fd.append('provider', provider);

    scriptData = await apiPost('/api/script/generate', fd);
    document.getElementById('script-text').value = scriptData.full_script || '';
    document.getElementById('script-title').textContent = scriptData.title || '';
    document.getElementById('script-caption').textContent = scriptData.caption || '';
    document.getElementById('script-result').style.display = 'block';

    showStatus('script-status', 'Script generated successfully!', 'success');
  } catch (e) {
    showStatus('script-status', `Error: ${e.message}`, 'error');
  }
}

function acceptScript() {
  const text = document.getElementById('script-text').value.trim();
  if (!text) { alert('Script is empty'); return; }
  document.getElementById('voice-script').value = text;
  goToStep(2);
}

// ── Step 2: Voice ──

async function generateVoice() {
  const script = document.getElementById('voice-script').value.trim();
  if (!script) { alert('No script text'); return; }

  const voice = document.getElementById('voice-select').value;
  showStatus('voice-status', 'Generating voiceover...', 'info');
  document.getElementById('voice-preview').style.display = 'none';

  try {
    const fd = new FormData();
    fd.append('script', script);
    fd.append('voice', voice);
    if (sessionId) fd.append('session_id', sessionId);

    const result = await apiPost('/api/voice/generate', fd);
    sessionId = result.session_id;

    const audioEl = document.getElementById('voice-audio');
    audioEl.src = `/api/session/${sessionId}/download/${result.audio_file}?t=${Date.now()}`;
    document.getElementById('voice-preview').style.display = 'block';

    showStatus('voice-status', `Voice generated! ${result.word_count} words, ${result.sentences} sentences.`, 'success');
  } catch (e) {
    showStatus('voice-status', `Error: ${e.message}`, 'error');
  }
}

// ── Step 3: Avatar ──

async function loadAvatarPresets() {
  try {
    const resp = await fetch('/api/avatar/presets');
    const data = await resp.json();
    const grid = document.getElementById('avatar-grid');
    grid.innerHTML = '';
    (data.presets || []).forEach((p, i) => {
      const div = document.createElement('div');
      div.className = `avatar-option ${i === 0 ? 'selected' : ''}`;
      div.dataset.preset = p.name;
      div.innerHTML = `<div style="width:60px;height:60px;border-radius:8px;background:var(--surface2);display:flex;align-items:center;justify-content:center;margin:0 auto;">
        <span style="font-size:28px;">&#x1F464;</span>
      </div><span>${p.name}</span>`;
      div.onclick = () => {
        grid.querySelectorAll('.avatar-option').forEach(o => o.classList.remove('selected'));
        div.classList.add('selected');
      };
      grid.appendChild(div);
    });
  } catch (e) { /* presets optional */ }
}

async function generateAvatar() {
  if (!sessionId) { alert('Generate voice first'); return; }

  const mode = getChipValue('avatar-mode-chips') || 'animated';
  const selected = document.querySelector('#avatar-grid .avatar-option.selected');
  const preset = selected ? selected.dataset.preset : 'default';

  showStatus('avatar-status', 'Generating avatar video... This may take a minute.', 'info');
  document.getElementById('avatar-preview').style.display = 'none';

  try {
    const fd = new FormData();
    fd.append('session_id', sessionId);
    fd.append('mode', mode);
    fd.append('avatar_preset', preset);

    const fileInput = document.getElementById('avatar-upload');
    if (fileInput.files.length > 0) {
      fd.append('avatar_image', fileInput.files[0]);
    }

    const result = await apiPost('/api/avatar/generate', fd);

    const videoEl = document.getElementById('avatar-video');
    videoEl.src = `/api/session/${sessionId}/download/${result.video_file}?t=${Date.now()}`;
    document.getElementById('avatar-preview').style.display = 'block';

    showStatus('avatar-status', `Avatar video created! Mode: ${result.mode}, ${result.duration_sec || '?'}s`, 'success');
  } catch (e) {
    showStatus('avatar-status', `Error: ${e.message}`, 'error');
  }
}

// ── Step 4: BGM ──

async function selectBGM() {
  if (!sessionId) { alert('Complete previous steps first'); return; }

  const category = getChipValue('bgm-chips') || 'comedy';
  showStatus('bgm-status', 'Selecting background music...', 'info');
  document.getElementById('bgm-preview').style.display = 'none';

  try {
    const fd = new FormData();
    fd.append('session_id', sessionId);
    fd.append('category', category);

    const result = await apiPost('/api/bgm/select', fd);

    const audioEl = document.getElementById('bgm-audio');
    audioEl.src = `/api/session/${sessionId}/download/${result.bgm_file}?t=${Date.now()}`;
    document.getElementById('bgm-preview').style.display = 'block';

    showStatus('bgm-status', `BGM applied! Source: ${result.source}, Category: ${result.category}`, 'success');
  } catch (e) {
    showStatus('bgm-status', `Error: ${e.message}`, 'error');
  }
}

// ── Step 5: Compose ──

async function composeVideo() {
  if (!sessionId) { alert('Complete previous steps first'); return; }

  const addCaptions = document.getElementById('add-captions').checked;
  const captionStyle = document.getElementById('caption-style').value;

  showStatus('compose-status', 'Composing video... This may take a moment.', 'info');
  document.getElementById('compose-preview').style.display = 'none';

  try {
    const fd = new FormData();
    fd.append('session_id', sessionId);
    fd.append('add_captions', addCaptions);
    fd.append('caption_style', captionStyle);

    const result = await apiPost('/api/video/compose', fd);

    const videoEl = document.getElementById('composed-video');
    videoEl.src = `/api/session/${sessionId}/download/${result.video_file}?t=${Date.now()}`;
    document.getElementById('compose-preview').style.display = 'block';

    showStatus('compose-status', 'Video composed successfully!', 'success');
  } catch (e) {
    showStatus('compose-status', `Error: ${e.message}`, 'error');
  }
}

// ── Step 6: Finalize ──

async function finalizeVideo() {
  if (!sessionId) { alert('Complete previous steps first'); return; }

  const grain = document.getElementById('grain').value;
  const roomTone = document.getElementById('room-tone').checked;

  showStatus('final-status', 'Applying anti-detection filters and finalizing...', 'info');
  document.getElementById('final-preview').style.display = 'none';

  try {
    const fd = new FormData();
    fd.append('session_id', sessionId);
    fd.append('grain_intensity', grain);
    fd.append('audio_room_tone', roomTone);

    const result = await apiPost('/api/video/finalize', fd);

    const videoEl = document.getElementById('final-video');
    const downloadUrl = `/api/session/${sessionId}/download/${result.video_file}`;
    videoEl.src = `${downloadUrl}?t=${Date.now()}`;
    document.getElementById('download-link').href = downloadUrl;
    document.getElementById('final-preview').style.display = 'block';

    showStatus('final-status', 'Reel finalized! All anti-detection filters applied.', 'success');
  } catch (e) {
    showStatus('final-status', `Error: ${e.message}`, 'error');
  }
}

// ── Start New ──

function startNew() {
  sessionId = null;
  scriptData = null;
  currentStep = 1;

  document.getElementById('topic').value = '';
  document.getElementById('script-text').value = '';
  document.getElementById('script-result').style.display = 'none';
  document.getElementById('voice-preview').style.display = 'none';
  document.getElementById('avatar-preview').style.display = 'none';
  document.getElementById('bgm-preview').style.display = 'none';
  document.getElementById('compose-preview').style.display = 'none';
  document.getElementById('final-preview').style.display = 'none';

  ['script-status', 'voice-status', 'avatar-status', 'bgm-status', 'compose-status', 'final-status']
    .forEach(hideStatus);

  goToStep(1);
}

// ── Mobile Tunnel ──

function toggleMobilePanel() {
  const panel = document.getElementById('mobile-panel');
  panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
}

function showMobileQR() {
  const pcIP = window.location.hostname;
  const pcPort = window.location.port || '8000';
  const apiUrl = `http://${pcIP}:${pcPort}`;
  const mobilePageUrl = `https://kausynew-afk.github.io/ai-reel-mobile/?api=${encodeURIComponent(apiUrl)}`;

  document.getElementById('qr-img').src =
    `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(mobilePageUrl)}`;
  document.getElementById('mobile-url-text').textContent = mobilePageUrl;
  document.getElementById('qr-box').style.display = 'block';
  showStatus('mobile-status', `Your PC API: ${apiUrl} — Scan QR with your phone (same WiFi)`, 'success');
}

// ── Init ──
loadAvatarPresets();
