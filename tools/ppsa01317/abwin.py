import sys, json, re, os, bisect
R = sys.argv[1]
events = [json.loads(l) for l in open(os.path.join(R, 'live-abba.jsonl'))]
blocks = [(e['t_ms'], e['state'], bool(e.get('held'))) for e in events if e['event'] == 'block']
eops = [(e['index'], e['t_ms']) for e in events if e['event'] == 'eop']
start = blocks[0][0]
def state(wall):
    s = '?'
    for t, st, h in blocks:
        if wall >= t: s = st + ('+H' if h else '')
    return s
wins = []
for f in ('stderr.log', 'stderr.tail.previous.log', 'stderr.tail.log'):
    p = os.path.join(R, f)
    if not os.path.exists(p): continue
    cur = None
    for line in open(p, errors='replace'):
        if line.startswith('[eop] deferred'):
            cur = {'file': f, 'p': None, 'dr': None, 'qi': None, 'cb': None, 'ind': None, 'pk': None, 'idle': ''}; wins.append(cur)
        elif cur is None: continue
        elif line.startswith('[present]'): cur['p'] = int(line.split()[1])
        elif line.startswith('[draws] '): cur['dr'] = int(line.split()[1])
        elif line.startswith('[draw] committer idle'): cur['idle'] = re.sub(r'.*\(10 s\): ', '', line.strip()).replace(' ms', '')
        elif line.startswith('[draw] pipelined'):
            m = re.search(r'\): (\d+) commits at ([\d.]+) us', line)
            if m: cur['cb'] = int(int(m.group(1)) * float(m.group(2)) / 1000)
            m = re.search(r'indirect (\d+) \(([\d.]+) ms\)', line); cur['ind'] = m and '%s/%dms' % (m.group(1), float(m.group(2)))
            m = re.search(r'packet (\d+) \(([\d.]+) ms\)', line); cur['pk'] = m and '%s/%dms' % (m.group(1), float(m.group(2)))
        elif line.startswith('[chain]'):
            m = re.search(r'queue 0x0 \d+ subs idle (\d+) ms', line); cur['qi'] = m and int(m.group(1))
# windows are ~10 s apart; anchor the head windows on the toggler's eop timestamps, extend by 10 s for the rest
head = [w for w in wins if w['file'] == 'stderr.log']
times = dict(eops)
last = None
for i, w in enumerate(wins):
    if w['file'] == 'stderr.log' and (i + 1) in times: w['wall'] = times[i + 1]; last = (i, w['wall'])
    elif last: w['wall'] = last[1] + (i - last[0]) * 10100
    else: w['wall'] = None
agg = {}
for w in wins:
    if w['wall'] is None: continue
    rel = (w['wall'] - start) / 1000; st = state(w['wall'])
    fps = w['p'] / 10 if w['p'] else None
    print('+%4.0f %-4s fps %-4s draws %-6s committer %-5s ind-drain %-10s pkt-drain %-9s q0idle %-5s | %s' % (rel, st, fps, w['dr'], w['cb'], w['ind'], w['pk'], w['qi'], w['idle'][:110]))
    if rel > 125 and fps and w['dr']: agg.setdefault(st, []).append((fps, w['dr']))
for st, v in sorted(agg.items()):
    print(st, 'windows', len(v), 'mean fps %.2f' % (sum(x[0] for x in v) / len(v)), 'mean draws/10s %d' % (sum(x[1] for x in v) / len(v)))
