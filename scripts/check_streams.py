"""Test every stream in source/us_english_all.m3u and record results in health.json.
Runs on GitHub's US servers. For HLS it loads the playlist, picks the top
variant and downloads a recent segment to measure speed vs the stream bitrate."""
import json, re, time, datetime, urllib.request, urllib.parse, ssl, concurrent.futures as cf

UA_DEFAULT = 'Mozilla/5.0 (Linux; Android 11) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'
TIMEOUT = 12
MAX_BYTES = 3_000_000
CTX = ssl.create_default_context()

def parse():
    ents, cur = [], None
    for l in open('source/us_english_all.m3u', encoding='utf-8').read().splitlines()[1:]:
        if l.startswith('#EXTINF'): cur = [l, []]
        elif l.startswith('#') and cur: cur[1].append(l)
        elif l.strip() and cur: cur.append(l.strip()); ents.append(cur); cur = None
    return ents

def headers_for(inf, opts):
    h = {'User-Agent': UA_DEFAULT}
    for src in [inf] + opts:
        for k, hk in (('http-user-agent', 'User-Agent'), ('http-referrer', 'Referer')):
            m = re.search(k + r'[=]"?([^"\n]+)"?', src)
            if m: h[hk] = m.group(1).strip()
    return h

def get(url, h, limit=MAX_BYTES):
    req = urllib.request.Request(url, headers=h)
    t = time.time()
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=CTX) as r:
        data = r.read(limit)
        return r.geturl(), data, time.time() - t

def check(url, h):
    final, data, dt = get(url, h, 400_000)
    text = data[:200_000].decode('utf-8', 'ignore')
    if '#EXTM3U' not in text[:50] and '#EXT' not in text[:500]:
        # not HLS: raw TS / mp4 / other - measure plain throughput
        _, data, dt = get(url, h, 1_500_000)
        if len(data) < 100_000: return {'status': 'dead', 'why': 'too little data'}
        return {'status': 'ok', 'speed': round((len(data) / dt) / 400_000, 2), 'kind': 'raw'}
    bw = None
    if '#EXT-X-STREAM-INF' in text:  # master: pick highest bandwidth
        best = None
        lines = text.splitlines()
        for i, l in enumerate(lines):
            if l.startswith('#EXT-X-STREAM-INF'):
                m = re.search(r'BANDWIDTH=(\d+)', l); b = int(m.group(1)) if m else 0
                uri = next((x for x in lines[i+1:] if x and not x.startswith('#')), None)
                if uri and (best is None or b > best[0]): best = (b, uri)
        if not best: return {'status': 'dead', 'why': 'empty master playlist'}
        bw = best[0] or None
        final, data, _ = get(urllib.parse.urljoin(final, best[1]), h, 400_000)
        text = data.decode('utf-8', 'ignore')
    segs, durs, cur = [], [], None
    for l in text.splitlines():
        if l.startswith('#EXTINF:'):
            try: cur = float(l[8:].split(',')[0])
            except ValueError: cur = None
        elif l and not l.startswith('#'):
            segs.append(l); durs.append(cur)
    if not segs: return {'status': 'dead', 'why': 'no segments'}
    i = max(0, len(segs) - 3)
    _, seg, dt = get(urllib.parse.urljoin(final, segs[i]), h)
    if len(seg) < 10_000: return {'status': 'dead', 'why': 'empty segment'}
    rate = len(seg) / max(dt, 0.01)                     # bytes/sec we achieved
    need = (bw / 8) if bw else (len(seg) / durs[i] if durs[i] else None)
    speed = round(rate / need, 2) if need else 9.99
    return {'status': 'ok' if speed >= 1.5 else 'slow', 'speed': speed, 'kind': 'hls'}

def run(e):
    inf, opts, url = e
    try:
        r = check(url, headers_for(inf, opts))
    except urllib.error.HTTPError as x:
        r = {'status': 'dead', 'why': f'HTTP {x.code}'}
    except Exception as x:
        r = {'status': 'dead', 'why': type(x).__name__}
    return url, inf.rsplit(',', 1)[1].strip(), r

try: health = json.load(open('health.json'))
except Exception: health = {}
today = datetime.date.today().isoformat()
ents = parse()
with cf.ThreadPoolExecutor(48) as ex:
    results = list(ex.map(run, ents))
new = {}
for url, name, r in results:
    old = health.get(url, {})
    fails = 0 if r['status'] != 'dead' else old.get('fails', 0) + 1
    new[url] = {'name': name, **r, 'fails': fails, 'checked': today,
                'last_ok': today if r['status'] != 'dead' else old.get('last_ok')}
json.dump(new, open('health.json', 'w'), indent=1, sort_keys=True)
c = {s: sum(1 for v in new.values() if v['status'] == s) for s in ('ok', 'slow', 'dead')}
print('stream check:', c)
