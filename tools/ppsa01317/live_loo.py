"""Mid-race leave-one-out of driver live flags (APS5_LIVE_FLAGS) for one owned GT7 run.

Usage: python -I -B live_loo.py <runs-dir> <flag>[,<flag>...] [first_s=120] [block_s=30]

Waits for the newest run of <runs-dir> to start (watchdog-ready.json). Until first_s every flag is 0 (race
loading never sees them); from then on all flags are 1, and blocks of block_s alternate between all on and
one flag off, in the order given: all, -f1, all, -f2, ... all. So each flag's absence is bracketed by two
all-on blocks. Records the block states and when each new [eop] window line reaches stderr.log
(live-abba.jsonl, same events as live_abba.py: 'state' is "all", "-<flag>" or "off"). Writes only inside the
run directory; stops when the run's exit.json appears or after the last block.
"""
import json, sys, time, datetime
from pathlib import Path

runs = Path(sys.argv[1]); flags = sys.argv[2].split(',')
first = float(sys.argv[3]) if len(sys.argv) > 3 else 120.0
block = float(sys.argv[4]) if len(sys.argv) > 4 else 30.0
schedule = []
for flag in flags: schedule += ['all', '-' + flag]
schedule.append('all')

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

def write(state):
    tmp = flagfile.with_suffix('.tmp')
    off = state[1:] if state.startswith('-') else None
    tmp.write_text(''.join('%s=%s\n' % (f, '0' if state == 'off' or f == off else '1') for f in flags), encoding='ascii')
    tmp.replace(flagfile)
    note(event='block', state=state, flags=flags)

write('off')
note(event='armed', run=run.name, first_s=first, block_s=block, schedule=schedule)
seen = 0; current = 'off'
while not (run / 'exit.json').exists():
    elapsed = time.time() - start
    index = int((elapsed - first) // block) if elapsed >= first else -1
    want = 'off' if index < 0 else schedule[min(index, len(schedule) - 1)]
    if want != current: write(want); current = want
    try:
        count = sum(1 for line in (run / 'stderr.log').read_text(errors='replace').splitlines() if line.startswith('[eop] deferred'))
    except OSError:
        count = seen
    if count > seen:
        note(event='eop', index=count, state=current); seen = count
    if index >= len(schedule) and elapsed > first + block * len(schedule) + 15: break
    time.sleep(1.0)
note(event='done')
