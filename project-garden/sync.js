(() => {
  const TOKEN_KEY = 'project-garden-sync-token-v1';
  const META_KEY = 'project-garden-sync-meta-v1';
  let meta = JSON.parse(localStorage.getItem(META_KEY) || '{}');
  let lastSig = new Map();
  let syncing = false;
  let pushTimer = null;

  const projectSig = p => JSON.stringify({
    category: p.category, name: p.name, status: p.status, priority: p.priority,
    next: p.next, star: !!p.star, notes: p.notes || ''
  });
  const remember = () => data.forEach(p => lastSig.set(p.id, projectSig(p)));
  const saveMeta = () => localStorage.setItem(META_KEY, JSON.stringify(meta));
  const token = () => localStorage.getItem(TOKEN_KEY) || '';
  const headers = () => ({ 'Content-Type': 'application/json', Authorization: `Bearer ${token()}` });

  const settings = document.querySelector('#settings .section');
  settings.insertAdjacentHTML('afterbegin', `
    <div id="cloudbox" style="background:#fffef9;border:1px solid #d8ddcf;border-radius:14px;padding:13px;margin-bottom:18px">
      <h2 style="margin:0 0 5px">☁ Cloud sync</h2>
      <div id="cloudstatus" class="next">Not connected on this device.</div>
      <label>Private sync key</label>
      <input id="cloudkey" type="password" autocomplete="off" placeholder="Paste your Project Garden sync key" style="width:100%;border:1px solid #d8ddcf;border-radius:11px;padding:10px;background:white;font:inherit;font-size:13px">
      <div class="actions"><button class="btn" id="cloudsave">Save & sync</button><button class="btn alt" id="cloudpull">Sync now</button></div>
      <button class="btn alt" id="clouddisconnect" style="width:100%;margin-top:8px">Disconnect this device</button>
      <div class="meta" style="margin-top:8px">The key stays in this browser. Project data is stored in the private Railway Postgres database.</div>
    </div>`);

  const statusEl = document.querySelector('#cloudstatus');
  const keyEl = document.querySelector('#cloudkey');
  if (token()) keyEl.value = token();

  function setStatus(text, ok = null) {
    statusEl.textContent = text;
    statusEl.style.color = ok === true ? '#2f855a' : ok === false ? '#c53030' : '#4e594f';
  }

  async function push(ids) {
    if (!token() || !ids.length) return;
    const unique = [...new Set(ids)];
    const projects = unique.map(id => data.find(p => p.id === id)).filter(Boolean).map(p => ({ ...p, modifiedAt: meta[p.id] || Date.now() }));
    const r = await fetch('/api/sync', { method: 'POST', headers: headers(), body: JSON.stringify({ projects }) });
    if (r.status === 401) throw new Error('bad_key');
    if (!r.ok) throw new Error('push_failed');
    const body = await r.json();
    return body.projects || [];
  }

  async function syncNow() {
    if (!token()) { setStatus('Not connected on this device.'); return; }
    if (syncing) return;
    syncing = true;
    setStatus('Syncing…');
    try {
      const r = await fetch('/api/projects', { headers: { Authorization: `Bearer ${token()}` } });
      if (r.status === 401) throw new Error('bad_key');
      if (!r.ok) throw new Error('pull_failed');
      const body = await r.json();
      const cloud = Array.isArray(body.projects) ? body.projects : [];
      const cloudMap = new Map(cloud.map(p => [p.id, p]));
      const pushIds = [];
      let changed = false;

      if (!cloud.length) {
        const now = Date.now();
        data.forEach((p, i) => { meta[p.id] = meta[p.id] || now + i; pushIds.push(p.id); });
        saveMeta();
      } else {
        for (const cp of cloud) {
          const i = data.findIndex(p => p.id === cp.id);
          const localM = meta[cp.id] || 0;
          const cloudM = Number(cp.modifiedAt) || 0;
          if (i < 0) {
            const { modifiedAt, ...clean } = cp;
            data.push(clean); meta[cp.id] = cloudM; changed = true;
          } else if (cloudM > localM) {
            const { modifiedAt, ...clean } = cp;
            data[i] = { ...data[i], ...clean };
            meta[cp.id] = cloudM; changed = true;
          } else if (localM > cloudM) pushIds.push(cp.id);
        }
        for (const p of data) {
          if (!cloudMap.has(p.id)) {
            meta[p.id] = meta[p.id] || Date.now();
            pushIds.push(p.id);
          }
        }
        saveMeta();
      }

      if (changed) { save(); render(); }
      remember();
      if (pushIds.length) await push(pushIds);
      setStatus(`Synced · ${new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`, true);
    } catch (e) {
      setStatus(e.message === 'bad_key' ? 'Sync key rejected.' : 'Cloud unavailable — local edits are safe.', false);
    } finally { syncing = false; }
  }

  function detectChanges() {
    const changed = [];
    const now = Date.now();
    for (const p of data) {
      const sig = projectSig(p), old = lastSig.get(p.id);
      if (old !== undefined && sig !== old) {
        meta[p.id] = now; changed.push(p.id);
      }
      lastSig.set(p.id, sig);
    }
    if (!changed.length) return;
    saveMeta();
    clearTimeout(pushTimer);
    pushTimer = setTimeout(async () => {
      if (!token()) return;
      try { setStatus('Saving…'); await push(changed); setStatus('Synced', true); }
      catch (e) { setStatus(e.message === 'bad_key' ? 'Sync key rejected.' : 'Cloud unavailable — local edits are safe.', false); }
    }, 500);
  }

  document.querySelector('#cloudsave').onclick = async () => {
    const v = keyEl.value.trim();
    if (!v) return setStatus('Enter the private sync key.', false);
    localStorage.setItem(TOKEN_KEY, v);
    await syncNow();
  };
  document.querySelector('#cloudpull').onclick = syncNow;
  document.querySelector('#clouddisconnect').onclick = () => {
    localStorage.removeItem(TOKEN_KEY); keyEl.value = ''; setStatus('Disconnected. Cloud data was not deleted.');
  };

  remember();
  setInterval(detectChanges, 700);
  setInterval(syncNow, 30000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) syncNow(); });
  window.addEventListener('online', syncNow);
  if (token()) syncNow();
})();
