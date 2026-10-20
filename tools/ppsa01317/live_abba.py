"""Mid-race ABBA toggling of driver live flags (APS5_LIVE_FLAGS) for one owned GT7 run.

Usage: python -I -B live_abba.py <runs-dir> <flag>[,<flag>...] [first_s=120] [block_s=30] [blocks=8] [held_flag,...]

Waits for the newest run of <runs-dir> to start (watchdog-ready.json), then, relative to its start time,
writes <run>/live-flags.txt in blocks A B B A A B B A (A: flags 0, B: flags 1), so race loading always
happens with the flags off. Held flags (optional sixth argument) are 0 until first_s and 1 from then on, in
both blocks, so the toggled flags are compared on top of them. Every second it also records when a new
[eop] window line reaches the run's stderr.log, so each 10 s window can be attributed to a block afterwards
(live-abba.jsonl). Writes only inside the run directory; stops when the run's exit.json appears or after
the last block.
"""
import json, sys, time, datetime
from pathlib import Path

runs = Path(sys.argv[1]); flags = sys.argv[2].split(',')
first, block, blocks = (float(sys.argv[3]) if len(sys.argv) > 3 else 120.0), (float(sys.argv[4]) if len(sys.argv) > 4 else 30.0), (int(sys.argv[5]) if len(sys.argv) > 5 else 8)
held = sys.argv[6].split(',') if len(sys.argv) > 6 and sys.argv[6] else []
pattern = ('A', 'B', 'B', 'A') * ((blocks + 3) // 4)

before = {p.name for p in runs.glob('baseline-*')}
run = None
for _ in range(600):
    fresh = sorted(p for p in runs.glob('baseline-*') if p.name not in before and (p / 'watchdog-ready.json').exists())
    if fresh: run = fresh[-1]; break
    time.sleep(0.5)
if run is None: sys.exit('no new run started')
meta = json.loads((run / 'run.json').read_text(encoding='utf-8-sig'))
start = datetime.datetime.fromisoformat(meta['start_utc'].replace('Z', '+00:00')[:26] + '+00:00').timestamp()
flagfile = run / 'live-flags.txt'; log = (run / 'live-abba.jsonl').open('a', encoding='utf-8')

def note(**fields):
    log.write(json.dumps({'t_ms': int(time.time() * 1000), **fields}) + '\n'); log.flush()

def write(state, holding=False):
    tmp = flagfile.with_suffix('.tmp')
    lines = ['%s=%s\n' % (f, '1' if state == 'B' else '0') for f in flags] + ['%s=%s\n' % (f, '1' if holding else '0') for f in held]
    tmp.write_text(''.join(lines), encoding='ascii')
    tmp.replace(flagfile)
    note(event='block', state=state, flags=flags, held=held if holding else [])

write('A')  # explicit off from the start: race loading never sees the flags
note(event='armed', run=run.name, first_s=first, block_s=block, pattern=''.join(pattern[:blocks]), held=held)
seen = 0; current = ('A', False)
while not (run / 'exit.json').exists():
    elapsed = time.time() - start
    index = int((elapsed - first) // block) if elapsed >= first else -1
    want = ('A' if index < 0 or index >= blocks else pattern[index], bool(held) and elapsed >= first)
    if want != current: write(*want); current = want
    try:
        count = sum(1 for line in (run / 'stderr.log').read_text(errors='replace').splitlines() if line.startswith('[eop] deferred'))
    except OSError:
        count = seen
    if count > seen:
        note(event='eop', index=count, state=current[0]); seen = count
    if index >= blocks and current[0] == 'A' and elapsed > first + block * blocks + 15: break
    time.sleep(1.0)
note(event='done')
