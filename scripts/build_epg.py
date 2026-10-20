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

def fetch(path):
    with urllib.request.urlopen(SRC + path, timeout=120) as r:
        return ET.parse(gzip.GzipFile(fileobj=io.BytesIO(r.read()))).getroot()

def norm(n):
    n = re.sub(r'\[.*?\]|\((\d+p|United States|US|USA)\)', '', n, flags=re.I)
    n = re.sub(r'\b(HD|SD|East|West)\b', '', n, flags=re.I)
    n = n.lower().replace('&', 'and').replace('+', ' plus')
    n = re.sub(r'^(pluto tv|plex|samsung tv plus)\s+', '', n)
    return re.sub(r'[^a-z0-9]', '', n)

guides = {}
for s, p in SOURCES:
    try:
        guides[s] = fetch(p)
    except Exception as e:  # one source failing shouldn't kill the build
        print(f'WARN: {s} failed: {e}')
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
    k = norm(inf.rsplit(',', 1)[1])
    for s in order:
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

hdr = f'#EXTM3U url-tvg="{BASE}/epg.xml.gz"\n' if BASE else '#EXTM3U\n'
for name, keep in (('playlist_all.m3u', lambda t: True),
                   ('playlist_guide_only.m3u', lambda t: t in mapping)):
    with open(name, 'w', encoding='utf-8') as f:
        f.write(hdr)
        for inf, opts, url in ents:
            if keep(tid_of(inf)):
                f.write('\n'.join([inf, *opts, url]) + '\n')
print(f'channels with guide: {len(mapping)} / {len({tid_of(e[0]) for e in ents})}, programmes: {len(progs)}')
if len(mapping) < 50: sys.exit('Too few matches - not publishing a broken guide')
