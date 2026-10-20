"""Build an XMLTV guide for source/us_english_all.m3u from the free
matthuisman/i.mjh.nz guides, and write playlists that point at it.
Usage: python scripts/build_epg.py <raw-base-url>"""
import gzip, re, sys, collections, urllib.request, io
import xml.etree.ElementTree as ET

BASE = sys.argv[1].rstrip('/') if len(sys.argv) > 1 else ''
SRC = 'https://raw.githubusercontent.com/matthuisman/i.mjh.nz/master/'
SOURCES = [('pluto', 'PlutoTV/all.xml.gz'), ('pbs', 'PBS/all.xml.gz'),
           ('samsung', 'SamsungTVPlus/us.xml.gz'), ('plex', 'Plex/us.xml.gz'),
           ('roku', 'Roku/all.xml.gz')]
# Extra US cable/broadcast guides - used only for channels the streaming guides don't cover.
# Each is tried every build; results are written to EPG_SOURCES.md.
EXTRA = [('epgshare', 'https://epgshare01.online/epgshare01/epg_ripper_US1.xml.gz'),
         ('openepg', 'https://www.open-epg.com/files/unitedstates1.xml.gz'),
         ('openepg2', 'https://www.open-epg.com/files/unitedstates2.xml.gz')]
SOURCES += EXTRA
EXTRA_KEYS = [k for k, _ in EXTRA]
source_status = {}

def fetch(path):
    url = path if path.startswith('http') else SRC + path
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 iptv-us-english'})
    with urllib.request.urlopen(req, timeout=180) as r:
        data = r.read()
    if data[:2] == b'\x1f\x8b': data = gzip.decompress(data)
    return ET.fromstring(data)

def norm(n):
    n = re.sub(r'\[.*?\]|\((\d+p|United States|US|USA)\)', '', n, flags=re.I)
    n = re.sub(r'\s+(US|USA)\s*$', '', n.strip(), flags=re.I)
    n = re.sub(r'\b(HD|SD|East|West)\b', '', n, flags=re.I)
    n = n.lower().replace('&', 'and').replace('+', ' plus')
    n = re.sub(r'^(pluto tv|plex|samsung tv plus)\s+', '', n)
    return re.sub(r'[^a-z0-9]', '', n)

guides = {}
for s, p in SOURCES:
    try:
        guides[s] = fetch(p)
        source_status[s] = f"ok - {len(guides[s].findall('channel'))} channels"
    except Exception as e:  # one source failing shouldn't kill the build
        print(f'WARN: {s} failed: {e}')
        source_status[s] = f'failed - {type(e).__name__}: {str(e)[:80]}'
        guides[s] = ET.Element('tv')

nidx = {}
for s, root in guides.items():
    c = collections.defaultdict(set)
    for ch in root.findall('channel'):
        for dn in ch.findall('display-name'):
            c[norm(dn.text or '')].add(ch.get('id'))
    nidx[s] = {k: next(iter(v)) for k, v in c.items() if len(v) == 1 and k}
pluto_ids = {ch.get('id') for ch in guides['pluto'].findall('channel')}

ents, cur = [], None
for l in open('source/us_english_all.m3u', encoding='utf-8').read().splitlines()[1:]:
    if l.startswith('#EXTINF'): cur = [l, []]
    elif l.startswith('#') and cur: cur[1].append(l)
    elif l.strip() and cur: cur.append(l); ents.append(cur); cur = None

ALIASES = {}
try:
    for l in open('source/epg_aliases.txt', encoding='utf-8'):
        if '=' in l and not l.startswith('#'):
            a, b = l.split('=', 1); ALIASES[a.strip().lower()] = b.strip()
except FileNotFoundError:
    pass
tid_of = lambda inf: re.search(r'tvg-id="([^"]*)"', inf).group(1)
mapping = {}
for inf, opts, url in ents:
    tid = tid_of(inf)
    if tid in mapping: continue
    m = re.search(r'/plu-([0-9a-f]{24})', url)
    if m and m.group(1) in pluto_ids:
        mapping[tid] = ('pluto', m.group(1)); continue
    order = ['pbs', 'samsung', 'plex', 'roku', 'pluto']
    for hint, src in (('samsung', 'samsung'), ('amagi', 'samsung'), ('plex', 'plex'), ('roku', 'roku')):
        if hint in url:
            order = [src] + [o for o in order if o != src]; break
    nm = inf.rsplit(',', 1)[1].strip()
    k = norm(ALIASES.get(nm.lower(), nm))
    for s in order + EXTRA_KEYS:
        if k in nidx[s]:
            mapping[tid] = (s, nidx[s][k]); break

rev = collections.defaultdict(list)
for tid, key in mapping.items(): rev[key].append(tid)
tv = ET.Element('tv', {'generator-info-name': 'iptv-us-english (from i.mjh.nz)'})
progs = []
for s, root in guides.items():
    cmap = {ch.get('id'): ch for ch in root.findall('channel')}
    for (ss, sid), tids in rev.items():
        if ss != s: continue
        for tid in tids:
            ch = ET.SubElement(tv, 'channel', {'id': tid})
            for c in cmap[sid]: ch.append(c)
    for p in root.findall('programme'):
        for tid in rev.get((s, p.get('channel')), []):
            q = ET.fromstring(ET.tostring(p)); q.set('channel', tid); progs.append(q)
tv.extend(progs)
with gzip.open('epg.xml.gz', 'wb') as f:
    ET.ElementTree(tv).write(f, encoding='utf-8', xml_declaration=True)

def clean(inf):
    m = re.search(r'group-title="([^"]*)"', inf)
    g = (m.group(1).split(';')[0] if m else '') or 'Other'
    if g == 'Undefined': g = 'Other'
    inf = re.sub(r'\s*group-title="[^"]*"', '', inf)
    inf = re.sub(r'\s*tvg-chno="[^"]*"', '', inf)
    return g, inf
import json
try: health = json.load(open('health.json'))
except Exception: health = {}
import datetime
HIDE_AFTER_HOURS = 12   # hidden only if still failing 12+ hours after its first failed check
NOW = datetime.datetime.now(datetime.timezone.utc)
try:
    FAVS = [l.strip() for l in open('source/favourites.txt', encoding='utf-8') if l.strip() and not l.startswith('#')]
except FileNotFoundError:
    FAVS = []
FAV_SET = {f.lower() for f in FAVS}
def failing_hours(v):
    if v.get('status') != 'dead' or not v.get('first_fail'): return 0
    return (NOW - datetime.datetime.fromisoformat(v['first_fail'])).total_seconds() / 3600
def should_hide(v):
    return failing_hours(v) >= HIDE_AFTER_HOURS and v.get('fails', 0) >= 2
def hidden(url, name=''):
    if name.strip().lower() in FAV_SET: return False      # never auto-hide favourites
    return should_hide(health.get(url, {}))
def speed(url):
    v = health.get(url, {})
    return -(v.get('speed') or 0) if v.get('status') in ('ok', 'slow') else 1
ordered = []
for inf, opts, url in ents:
    if hidden(url, inf.rsplit(',', 1)[1]): continue
    g, inf2 = clean(inf)
    nm = inf2.rsplit(',', 1)[1].strip()
    base = re.sub(r'\s*(\(\d+p\)|\[.*?\]|\bHD\b|\bSD\b)', '', nm).strip().lower()
    ordered.append((g, base, inf2, opts, url, tid_of(inf), speed(url), nm.lower()))
# A-Z by channel; when a channel has several copies, the fastest copy comes first
ordered.sort(key=lambda e: (e[0] == 'Other', e[0].lower(), e[1], e[6], e[7]))
ordered = [e[:6] for e in ordered]
# Favourites group at the top (copies; channels also stay in their own category)
favs = FAVS
by_name = {}
for e in ordered:
    by_name.setdefault(e[2].rsplit(',', 1)[1].strip().lower(), e)  # first = fastest copy
fav_rows = []
for f in favs:
    e = by_name.get(f.lower())
    if e: fav_rows.append(('★ Top Picks',) + e[1:])
    else: print('favourite not found or hidden:', f)
ordered = fav_rows + ordered

def line(g, inf, n):
    head, name = inf.rsplit(',', 1)
    return f'{head} tvg-chno="{n}" group-title="{g}",{name}'

hdr = f'#EXTM3U url-tvg="{BASE}/epg.xml.gz"\n' if BASE else '#EXTM3U\n'
for name, keep in (('playlist_all.m3u', lambda t: True),
                   ('playlist_guide_only.m3u', lambda t: t in mapping)):
    with open(name, 'w', encoding='utf-8') as f:
        f.write(hdr)
        n = 0
        for g, _, inf, opts, url, tid in ordered:
            if keep(tid) or g == '★ Top Picks':
                n += 1
                f.write('\n'.join([line(g, inf, n), *opts, url]) + '\n')
print(f'channels with guide: {len(mapping)} / {len({tid_of(e[0]) for e in ents})}, programmes: {len(progs)}')
if len(mapping) < 50: sys.exit('Too few matches - not publishing a broken guide')

if health:
    rows = sorted(health.values(), key=lambda v: (v['status'] != 'dead', v['status'] != 'slow', v['name'].lower()))
    cnt = collections.Counter(v['status'] for v in health.values())
    hid = sum(1 for v in health.values() if should_hide(v) and v['name'].lower() not in FAV_SET)
    fav_bad = [v for v in rows if v['name'].lower() in FAV_SET and v['status'] != 'ok']
    last = max(v['checked'] for v in health.values())
    def fmt(v):
        h = failing_hours(v)
        hidden_txt = 'yes' if should_hide(v) and v['name'].lower() not in FAV_SET else ''
        return (f"| {v['name']} | {v['status']} | {v.get('speed') or ''} | "
                f"{round(h) if h else ''} | {hidden_txt} | {v.get('why','')} |\n")
    head = "| Channel | Status | Speed | Hours failing | Hidden | Note |\n|---|---|---|---|---|---|\n"
    with open('STREAM_HEALTH.md', 'w', encoding='utf-8') as f:
        f.write(f"# Stream health\n\nLast checked {last} UTC from GitHub's US servers (twice daily, ~4 AM and ~4 PM Jamaica time).\n\n"
                f"OK: {cnt['ok']} - Slow: {cnt['slow']} - Failed: {cnt['dead']} - Hidden from playlists: {hid}\n\n"
                "**Speed** = how many times faster than real time a segment downloaded (under 1.5 = likely to buffer). "
                f"A stream is **hidden** once it has failed checks at least {HIDE_AFTER_HOURS} hours apart, and comes back automatically when it works again. "
                "Favourites are never hidden automatically.\n\n")
        f.write("## Favourites with problems\n\n")
        f.write(head + ''.join(fmt(v) for v in fav_bad) if fav_bad else "None - all favourites passed the last check.\n")
        f.write("\n## All slow and failing streams\n\n" + head)
        for v in rows:
            if v['status'] != 'ok': f.write(fmt(v))
    print('hidden streams:', hid, '| favourites with problems:', len(fav_bad))

with open('EPG_SOURCES.md', 'w', encoding='utf-8') as f:
    cnt = collections.Counter(v[0] for v in mapping.values())
    f.write("# Guide sources\n\nResult of the last build. Channels are matched to the first source that lists them.\n\n"
            "| Source | Status | Channels matched |\n|---|---|---|\n")
    for k, _ in SOURCES:
        f.write(f"| {k} | {source_status.get(k,'')} | {cnt.get(k,0)} |\n")
