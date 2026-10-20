import bisect, collections, sys, re
syms_file, stacks_file, thread, base = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4], 16)
depth = int(sys.argv[5]); top = int(sys.argv[6]); skip = sys.argv[7].split('|') if len(sys.argv) > 7 else []
syms = []
for line in open(syms_file, errors='replace'):
    a, t, name = line.rstrip('\n').split(' ', 2); syms.append((int(a, 16), name))
syms.sort(); addrs = [s[0] for s in syms]
def sym(off):
    i = bisect.bisect_right(addrs, base + off) - 1
    n = syms[i][1] if i >= 0 else '?'
    n = re.sub(r'\(.*', '', n); n = n.replace('AgcDriver::', '').replace('DriverDetail::', '').replace('(anonymous namespace)::', '')
    return n
c = collections.Counter(); total = 0; busy = 0
for line in open(stacks_file, errors='replace'):
    p = line.rstrip('\n').split('\t')
    if len(p) < 4 or p[1] != thread: continue
    n = int(p[2]); total += n; frames = p[3].split()
    waiting = any(f.startswith(('ntdll.dll+16', 'KERNELBASE.dll+22', 'KERNELBASE.dll+1be')) for f in frames[:2])
    if not waiting: busy += n
    names = [sym(int(f.split('+')[1], 16)) for f in frames if f.startswith('libSceAgcDriver.prx+')]
    key = ('W ' if waiting else 'B ') + ' < '.join(names[:depth])
    if any(s and s in key for s in skip): continue
    c[key] += n
print('total', total, 'busy', busy, '%.1f%%' % (100 * busy / max(total, 1)))
for k, n in c.most_common(top): print('%5d %4.1f%% %s' % (n, 100 * n / total, k))
