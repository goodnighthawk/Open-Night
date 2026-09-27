const express = require('express');
const path = require('path');
const fs = require('fs');
const { Pool } = require('pg');

const app = express();
const port = process.env.PORT || 8080;
const token = process.env.SYNC_TOKEN || '';
const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: process.env.DATABASE_URL && process.env.DATABASE_URL.includes('railway.internal') ? false : { rejectUnauthorized: false }
});

app.use(express.json({ limit: '2mb' }));

async function initDb() {
  await pool.query(`
    CREATE TABLE IF NOT EXISTS project_garden_projects (
      id TEXT PRIMARY KEY,
      payload JSONB NOT NULL,
      modified_at BIGINT NOT NULL DEFAULT 0,
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
  `);
}

function assistantUpdates() {
  const allowed = new Set(['category', 'name', 'status', 'priority', 'next', 'star', 'notes']);
  const out = [];
  for (const [key, value] of Object.entries(process.env)) {
    if (!key.startsWith('GARDEN_UPDATE_') || !value) continue;
    try {
      const p = JSON.parse(value);
      if (!p || typeof p.id !== 'string' || !p.id) continue;
      const modifiedAt = Number(p.modifiedAt) || 0;
      const patch = {};
      for (const [k, v] of Object.entries(p)) if (allowed.has(k)) patch[k] = v;
      if (modifiedAt > 0 && Object.keys(patch).length) out.push({ id: p.id, modifiedAt, patch });
    } catch (_) {}
  }
  return out;
}

async function applyAssistantUpdates() {
  for (const u of assistantUpdates()) {
    await pool.query(`
      UPDATE project_garden_projects
      SET payload = payload || $2::jsonb, modified_at = $3, updated_at = NOW()
      WHERE id = $1 AND modified_at < $3
    `, [u.id, JSON.stringify(u.patch), Math.trunc(u.modifiedAt)]);
  }
}

function auth(req, res, next) {
  if (!token) return res.status(503).json({ error: 'sync_not_configured' });
  if (req.get('authorization') !== `Bearer ${token}`) return res.status(401).json({ error: 'unauthorized' });
  next();
}

app.get('/api/health', async (_req, res) => {
  try {
    await pool.query('SELECT 1');
    res.json({ ok: true, storage: 'postgres' });
  } catch (e) {
    res.status(503).json({ ok: false, error: 'database_unavailable' });
  }
});

app.get('/api/projects', auth, async (_req, res) => {
  try {
    await applyAssistantUpdates();
    const result = await pool.query('SELECT id, payload, modified_at FROM project_garden_projects ORDER BY id');
    res.json({ projects: result.rows.map(r => ({ ...r.payload, id: r.id, modifiedAt: Number(r.modified_at) })) });
  } catch (e) {
    console.error('GET /api/projects', e);
    res.status(500).json({ error: 'read_failed' });
  }
});

app.post('/api/sync', auth, async (req, res) => {
  const projects = Array.isArray(req.body && req.body.projects) ? req.body.projects : null;
  if (!projects || projects.length > 500) return res.status(400).json({ error: 'invalid_projects' });
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    for (const p of projects) {
      if (!p || typeof p.id !== 'string' || !p.id || p.id.length > 180) continue;
      const modifiedAt = Number.isFinite(Number(p.modifiedAt)) ? Math.max(0, Math.trunc(Number(p.modifiedAt))) : 0;
      const payload = { ...p };
      delete payload.modifiedAt;
      await client.query(`
        INSERT INTO project_garden_projects (id, payload, modified_at, updated_at)
        VALUES ($1, $2::jsonb, $3, NOW())
        ON CONFLICT (id) DO UPDATE SET
          payload = EXCLUDED.payload,
          modified_at = EXCLUDED.modified_at,
          updated_at = NOW()
        WHERE EXCLUDED.modified_at >= project_garden_projects.modified_at
      `, [p.id, JSON.stringify(payload), modifiedAt]);
    }
    await client.query('COMMIT');
    await applyAssistantUpdates();
    const result = await pool.query('SELECT id, payload, modified_at FROM project_garden_projects ORDER BY id');
    res.json({ ok: true, projects: result.rows.map(r => ({ ...r.payload, id: r.id, modifiedAt: Number(r.modified_at) })) });
  } catch (e) {
    await client.query('ROLLBACK');
    console.error('POST /api/sync', e);
    res.status(500).json({ error: 'sync_failed' });
  } finally {
    client.release();
  }
});

function sendIndex(_req, res) {
  fs.readFile(path.join(__dirname, 'index.html'), 'utf8', (err, html) => {
    if (err) return res.status(500).send('Project Garden unavailable');
    if (!html.includes('src="sync.js"')) html = html.replace('</body>', '<script src="sync.js"></script></body>');
    res.type('html').send(html);
  });
}

app.get(['/', '/index.html'], sendIndex);
app.use(express.static(__dirname, { index: false, maxAge: '5m' }));
app.get('*', sendIndex);

async function start() {
  let lastError;
  for (let i = 0; i < 40; i++) {
    try {
      await initDb();
      await applyAssistantUpdates();
      app.listen(port, '0.0.0.0', () => console.log(`Project Garden listening on ${port}`));
      return;
    } catch (e) {
      lastError = e;
      console.log(`Waiting for database (${i + 1}/40)…`);
      await new Promise(r => setTimeout(r, 2000));
    }
  }
  console.error('Database initialization failed', lastError);
  process.exit(1);
}

start();
