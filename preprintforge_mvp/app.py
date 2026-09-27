import asyncio, html, json, os, re, secrets, sqlite3
from pathlib import Path
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from pypdf import PdfReader
import httpx

APP_NAME=os.getenv('APP_NAME','PreprintForge')
DB=Path(os.getenv('DATABASE_PATH','data/preprintforge.db')); DB.parent.mkdir(parents=True,exist_ok=True)
UPLOAD=Path(os.getenv('UPLOAD_DIR','data/uploads')); UPLOAD.mkdir(parents=True,exist_ok=True)
BASE_URL=os.getenv('BASE_URL','http://localhost:8000').rstrip('/')
MAX_MB=int(os.getenv('MAX_UPLOAD_MB','25'))
app=FastAPI(title=APP_NAME)

REVIEWERS=[
('physics','Physics Consistency','Test physical assumptions, dimensions, limiting cases and whether conclusions follow.'),
('methods','Methods & Experimental Design','Find missing controls, ambiguous methods, calibration weaknesses and alternatives.'),
('math','Equations & Numerical Consistency','Check equations, variables, units, numerical consistency and orders of magnitude.'),
('stats','Statistics & Uncertainty','Inspect uncertainty propagation, statistical assumptions, significance and robustness.'),
('repro','Reproducibility','Identify code, data, parameters, versions and procedures needed for reproduction.'),
('adversary','Adversarial Referee','Seek the strongest plausible failure mode and propose falsification tests.'),
]

CSS='''body{font-family:Inter,system-ui,sans-serif;margin:0;background:#f5f3ec;color:#171713}a{color:inherit}.top{display:flex;justify-content:space-between;padding:18px 5vw;border-bottom:1px solid #c9c6ba}.brand{font-weight:900;text-decoration:none}.top nav a{margin-left:20px}.wrap{width:min(1050px,90vw);margin:auto}.hero{padding:70px 0 45px}.ey{font-size:12px;letter-spacing:.12em;font-weight:800;text-transform:uppercase}.hero h1,h1{font-family:Georgia,serif;font-size:clamp(40px,7vw,78px);line-height:.98;margin:.22em 0}.hero p{font-size:20px;max-width:720px;line-height:1.5}.btn{display:inline-block;background:#171713;color:white;padding:12px 18px;text-decoration:none;border:0;font-weight:800;margin:5px 7px 5px 0;cursor:pointer}.ghost{background:transparent;color:#171713;border:1px solid #171713}.card,.review,.price{background:white;border:1px solid #cbc8bc;padding:22px;margin:15px 0}.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:15px}.form{display:grid;gap:16px;max-width:760px}.form input,.form textarea{width:100%;padding:11px;margin-top:5px;box-sizing:border-box}.tag{font-size:11px;font-weight:900;letter-spacing:.08em;text-transform:uppercase}.meta{color:#68665e}.pricing{display:grid;grid-template-columns:repeat(3,1fr);gap:15px}.money{font:700 54px Georgia,serif}.footer{border-top:1px solid #c9c6ba;margin-top:60px;padding:25px 0 45px;color:#68665e;font-size:13px}@media(max-width:760px){.grid,.pricing{grid-template-columns:1fr}.hero{padding-top:45px}}'''

def con():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def init_db():
    with con() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS preprints(id INTEGER PRIMARY KEY,slug TEXT UNIQUE,title TEXT,authors TEXT,abstract TEXT,email TEXT,filename TEXT,stored_path TEXT,extracted_text TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);CREATE TABLE IF NOT EXISTS reviews(id INTEGER PRIMARY KEY,preprint_id INTEGER,reviewer_key TEXT,reviewer_name TEXT,verdict TEXT,severity TEXT,summary TEXT,findings TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);''')
init_db()

def esc(x): return html.escape(str(x or ''))
def page(title,body):
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)} · {APP_NAME}</title><style>{CSS}</style></head><body><header class="top"><a class="brand" href="/">{APP_NAME}</a><nav><a href="/upload">Upload</a><a href="/pricing">Pricing</a></nav></header><main class="wrap">{body}</main><footer class="wrap footer">Machine Review is automated analysis, not human peer review or publication acceptance.</footer></body></html>'''

def slugify(title):
    base=re.sub(r'[^a-z0-9]+','-',title.lower()).strip('-')[:60] or 'preprint'; return f'{base}-{secrets.token_hex(3)}'

def pdf_text(path):
    out=[]
    for pg in PdfReader(str(path)).pages:
        try: out.append(pg.extract_text() or '')
        except Exception: pass
    return '\n'.join(out)

def heuristic(key,name,text):
    low=text.lower()
    words=len(re.findall(r"\b\w+\b", text))
    def n(*terms): return sum(low.count(t) for t in terms)
    signals={
        'uncertainty':n('uncert','error bar','standard deviation','confidence interval','systematic error','statistical error'),
        'calibration':n('calibrat','control experiment','control sample','benchmark','reference measurement'),
        'methods':n('methods','experimental setup','apparatus','procedure','protocol','sample preparation'),
        'equations':len(re.findall(r'\([0-9]{1,3}\)', text)),
        'units':len(re.findall(r'\b(?:hz|khz|mhz|ghz|ev|mev|kev|gev|nm|um|µm|ms|ns|tesla|gauss|kelvin|\bk\b)\b', low)),
        'data':n('data availability','data are available','dataset','repository','zenodo','figshare'),
        'code':n('code availability','source code','github','gitlab','software repository'),
        'supplement':n('supplementary','supplemental','appendix'),
        'claims':n('we show','we demonstrate','we find','we report','we observe','we conclude'),
    }
    findings=[]
    if key=='physics':
        findings.append(f"Screened about {words:,} extracted words; detected {signals['claims']} explicit result/claim phrases and {signals['units']} unit-bearing tokens.")
        findings.append(f"Found {signals['calibration']} calibration/control/benchmark markers and {signals['uncertainty']} uncertainty/error markers.")
        verdict='No obvious structural physics red flag' if words>3000 and signals['claims'] else 'Physics structure needs inspection'
        severity='info' if words>3000 and signals['claims'] else 'advisory'
    elif key=='methods':
        findings.append(f"Detected {signals['methods']} methods/apparatus/procedure markers and {signals['calibration']} calibration/control/benchmark markers.")
        if signals['methods']==0: findings.append('No strong methods-section markers were detected in extracted text; confirm that the experimental/computational procedure is explicit.')
        verdict='Methods signals detected' if signals['methods'] else 'Methods detail not clearly detected'
        severity='info' if signals['methods'] else 'needs-attention'
    elif key=='math':
        findings.append(f"Detected approximately {signals['equations']} equation-number-like labels and {signals['units']} physical-unit tokens in the extracted PDF text.")
        findings.append('This fallback screen does not yet symbolically re-derive equations or recompute numerical results.')
        verdict='Equation audit pending' if signals['equations'] else 'Few equation markers detected'
        severity='advisory'
    elif key=='stats':
        findings.append(f"Detected {signals['uncertainty']} uncertainty/error/statistical markers in the manuscript text.")
        if signals['uncertainty']==0: findings.append('No explicit uncertainty language was detected; check whether uncertainties and systematics are quantified where required.')
        verdict='Uncertainty treatment detected' if signals['uncertainty'] else 'Uncertainty treatment not detected'
        severity='info' if signals['uncertainty'] else 'needs-attention'
    elif key=='repro':
        findings.append(f"Detected data-sharing markers: {signals['data']}; code-sharing markers: {signals['code']}; supplementary/appendix markers: {signals['supplement']}.")
        missing=[]
        if not signals['data']: missing.append('data availability')
        if not signals['code']: missing.append('code/software availability')
        if missing: findings.append('Not clearly detected: '+', '.join(missing)+'. This may be appropriate for some experiments, but should be stated explicitly when relevant.')
        if signals['data'] and signals['code']: verdict='Reproducibility resources detected'; severity='info'
        elif signals['data'] or signals['code'] or signals['supplement']: verdict='Partial reproducibility information detected'; severity='advisory'
        else: verdict='Reproducibility statement not detected'; severity='needs-attention'
    else:
        findings.append(f"Detected {signals['claims']} explicit claim phrases. An adversarial review should target the central claim with a competing explanation or null test.")
        if signals['calibration']==0: findings.append('No calibration/control/benchmark marker was detected by the fallback screen; a targeted control test is a priority check.')
        else: findings.append(f"Detected {signals['calibration']} calibration/control/benchmark markers that can be examined as possible falsification tests.")
        verdict='Adversarial test identified' if signals['claims'] else 'Central claim needs explicit falsification test'
        severity='advisory'
    summary='Structured manuscript screening completed. This is a deterministic fallback analysis; manuscript-specific LLM review is not connected yet.'
    return {'reviewer_key':key,'reviewer_name':name,'verdict':verdict,'severity':severity,'summary':summary,'findings':findings}

async def one_review(key,name,remit,text):
    url=os.getenv('LLM_API_URL','').strip(); token=os.getenv('LLM_API_KEY','').strip(); model=os.getenv('LLM_MODEL','').strip()
    if not(url and token and model): return heuristic(key,name,text)
    prompt=f'''You are one component of a transparent machine-review system. Role: {name}. Remit: {remit}. Do not decide publication acceptance and do not fabricate checks. Return JSON only with verdict, severity, summary, findings. severity must be info, advisory, needs-attention, or critical. Findings must be concrete. MANUSCRIPT:\n{text[:70000]}'''
    async with httpx.AsyncClient(timeout=120) as client:
        r=await client.post(url,headers={'Authorization':f'Bearer {token}','Content-Type':'application/json'},json={'model':model,'messages':[{'role':'system','content':'Rigorous scientific reviewer. Output strict JSON.'},{'role':'user','content':prompt}],'temperature':0.2}); r.raise_for_status()
    raw=r.json()['choices'][0]['message']['content'].strip(); raw=re.sub(r'^```(?:json)?\s*|\s*```$','',raw,flags=re.I|re.S); d=json.loads(raw)
    return {'reviewer_key':key,'reviewer_name':name,'verdict':str(d.get('verdict','Scientific assessment returned'))[:120],'severity':str(d.get('severity','advisory'))[:40],'summary':str(d.get('summary',''))[:2000],'findings':[str(x)[:1500] for x in d.get('findings',[])][:8]}

async def run_reviews(text):
    out=[]
    for key,name,remit in REVIEWERS:
        try: out.append(await one_review(key,name,remit,text))
        except Exception as e:
            x=heuristic(key,name,text); x['summary']+=f' Live-review provider error: {type(e).__name__}.'; out.append(x)
    return out

def review_html(rows):
    if not rows:return '<div class="card">Machine review has not been run for this version.</div>'
    blocks=[]
    for r in rows:
        findings=json.loads(r['findings']) if isinstance(r['findings'],str) else r['findings']
        lis=''.join(f'<li>{esc(x)}</li>' for x in findings)
        blocks.append(f'''<article class="review"><span class="tag">{esc(r['reviewer_name'])} · {esc(r['severity'])}</span><h2>{esc(r['verdict'])}</h2><p>{esc(r['summary'])}</p><ul>{lis}</ul></article>''')
    return ''.join(blocks)

@app.get('/health')
def health(): return {'ok':True,'service':APP_NAME}

@app.get('/',response_class=HTMLResponse)
def home():
    with con() as c: rows=c.execute('SELECT * FROM preprints ORDER BY id DESC LIMIT 8').fetchall()
    cards=''.join(f'''<a class="card" href="/p/{esc(r['slug'])}"><span class="tag">PREPRINT</span><h2>{esc(r['title'])}</h2><p>{esc(r['authors'])}</p><small>{esc(r['created_at'])}</small></a>''' for r in rows) or '<div class="card"><h2>No records yet</h2><p>Upload the first manuscript.</p></div>'
    body=f'''<section class="hero"><span class="ey">AI-assisted scientific preprints</span><h1>Stress-test the paper<br>before the referees do.</h1><p>Post a free preprint. Run transparent machine reviewers for physics, methods, equations, uncertainty, reproducibility and adversarial falsification.</p><a class="btn" href="/upload">Upload a preprint</a><a class="btn ghost" href="/pricing">Review plans</a></section><h2>Recent preprints</h2><section class="grid">{cards}</section>'''
    return page('Home',body)

@app.get('/upload',response_class=HTMLResponse)
def upload_page():
    body='''<section class="hero"><span class="ey">Free preprint posting</span><h1>Upload manuscript</h1><p>Uploaded PDFs and metadata are stored on persistent server storage. Do not upload confidential or embargoed work.</p><form class="form" method="post" enctype="multipart/form-data"><label>Title<input name="title" required></label><label>Authors<input name="authors" required></label><label>Abstract<textarea name="abstract" rows="7" required></textarea></label><label>Contact email<input name="email" type="email" required></label><label>PDF<input name="manuscript" type="file" accept="application/pdf,.pdf" required></label><button class="btn">Create preprint record</button></form></section>'''
    return page('Upload',body)

@app.post('/upload')
async def upload(title:str=Form(...),authors:str=Form(...),abstract:str=Form(...),email:str=Form(...),manuscript:UploadFile=File(...)):
    b=await manuscript.read()
    if len(b)>MAX_MB*1024*1024: raise HTTPException(413,'PDF too large')
    if not b.startswith(b'%PDF'): raise HTTPException(400,'Valid PDF required')
    slug=slugify(title); path=UPLOAD/f'{slug}.pdf'; path.write_bytes(b)
    try: text=pdf_text(path)
    except Exception: text=''
    with con() as c:
        cur=c.execute('INSERT INTO preprints(slug,title,authors,abstract,email,filename,stored_path,extracted_text) VALUES(?,?,?,?,?,?,?,?)',(slug,title.strip(),authors.strip(),abstract.strip(),email.strip(),manuscript.filename,str(path),text)); pid=cur.lastrowid
    return RedirectResponse(f'/dashboard/{pid}',303)

@app.get('/dashboard/{pid}',response_class=HTMLResponse)
def dashboard(pid:int):
    with con() as c:
        p=c.execute('SELECT * FROM preprints WHERE id=?',(pid,)).fetchone(); rows=c.execute('SELECT * FROM reviews WHERE preprint_id=? ORDER BY id',(pid,)).fetchall()
    if not p: raise HTTPException(404)
    body=f'''<section class="hero"><span class="ey">Author dashboard</span><h1>{esc(p['title'])}</h1><p>{esc(p['authors'])}</p><a class="btn ghost" href="/p/{esc(p['slug'])}">Public page</a><form style="display:inline" method="post" action="/dashboard/{pid}/review"><button class="btn">Run 6-reviewer panel</button></form></section><h2>Latest machine review</h2>{review_html(rows)}'''
    return page(p['title'],body)

@app.post('/dashboard/{pid}/review')
async def review(pid:int):
    with con() as c:p=c.execute('SELECT * FROM preprints WHERE id=?',(pid,)).fetchone()
    if not p: raise HTTPException(404)
    rows=await run_reviews(p['extracted_text'] or f"TITLE: {p['title']}\nABSTRACT: {p['abstract']}")
    with con() as c:
        c.execute('DELETE FROM reviews WHERE preprint_id=?',(pid,))
        for r in rows:c.execute('INSERT INTO reviews(preprint_id,reviewer_key,reviewer_name,verdict,severity,summary,findings) VALUES(?,?,?,?,?,?,?)',(pid,r['reviewer_key'],r['reviewer_name'],r['verdict'],r['severity'],r['summary'],json.dumps(r['findings'])))
    return RedirectResponse(f'/dashboard/{pid}',303)

@app.get('/p/{slug}',response_class=HTMLResponse)
def public(slug:str):
    with con() as c:
        p=c.execute('SELECT * FROM preprints WHERE slug=?',(slug,)).fetchone(); rows=c.execute('SELECT * FROM reviews WHERE preprint_id=? ORDER BY id',(p['id'],)).fetchall() if p else []
    if not p: raise HTTPException(404)
    body=f'''<article class="hero"><span class="ey">Automated-screening preprint</span><h1>{esc(p['title'])}</h1><p><b>{esc(p['authors'])}</b></p><p>{esc(p['abstract'])}</p><a class="btn" href="/p/{esc(slug)}/pdf">Open PDF</a><p class="meta">Posted {esc(p['created_at'])} · Preprint record, not journal acceptance.</p></article><h2>Transparent machine review</h2>{review_html(rows)}'''
    return page(p['title'],body)

@app.get('/p/{slug}/pdf')
def pdf(slug:str):
    with con() as c:p=c.execute('SELECT * FROM preprints WHERE slug=?',(slug,)).fetchone()
    if not p: raise HTTPException(404)
    return FileResponse(p['stored_path'],media_type='application/pdf',filename=p['filename'])

@app.get('/pricing',response_class=HTMLResponse)
def pricing():
    ready=bool(os.getenv('STRIPE_SECRET_KEY'))
    body=f'''<section class="hero"><span class="ey">Pay for analysis, never acceptance</span><h1>Launch pricing</h1><p>Posting stays free. Paid products buy additional computation and review.</p></section><section class="pricing"><article class="price"><h2>Preprint</h2><div class="money">$0</div><p>Public manuscript record and basic screening.</p><a class="btn ghost" href="/upload">Post free</a></article><article class="price"><h2>Full Machine Review</h2><div class="money">$29</div><p>Multi-agent scientific critique.</p><form method="post" action="/checkout/full-review"><button class="btn">Buy review</button></form></article><article class="price"><h2>Repro Audit</h2><div class="money">$79</div><p>Review plus reproducibility audit workflow.</p><form method="post" action="/checkout/repro-audit"><button class="btn">Buy audit</button></form></article></section>{'' if ready else '<div class="card">Checkout is disabled until Stripe keys and Price IDs are configured.</div>'}'''
    return page('Pricing',body)

@app.post('/checkout/{plan}')
def checkout(plan:str):
    import stripe
    secret=os.getenv('STRIPE_SECRET_KEY',''); prices={'full-review':os.getenv('STRIPE_PRICE_FULL_REVIEW',''),'repro-audit':os.getenv('STRIPE_PRICE_REPRO_AUDIT','')}; price=prices.get(plan)
    if not(secret and price): raise HTTPException(503,'Payments are not configured yet.')
    stripe.api_key=secret; s=stripe.checkout.Session.create(mode='payment',line_items=[{'price':price,'quantity':1}],success_url=f'{BASE_URL}/payment/success',cancel_url=f'{BASE_URL}/pricing')
    return RedirectResponse(s.url,303)

@app.get('/payment/success',response_class=HTMLResponse)
def success(): return page('Success','<section class="hero"><span class="ey">Payment received</span><h1>Review credit purchased.</h1><p>Checkout succeeded.</p><a class="btn" href="/upload">Upload manuscript</a></section>')
