"""Freeze the prototype AGC build and write proto/proto.json for the baseline launcher (--config).

Same layout, protections and E flags as the validated baseline (runtime inputs hardlinked to the verified
originals, private game state copied, protected seed read-only); only the AGC PRX differs. Run with -I -B.
--ports takes the PRX from the coherence-ports worktree (src-ports, built in build-ports) instead of src/build.
"""
import json, shutil, subprocess, sys
from pathlib import Path
sys.dont_write_bytecode = True
LAUNCHER = Path(r'C:\Users\Koiki\Documents\AnyPS5Diagnostics\GT7-Baseline-Persistence-20261018T002953Z\launcher')
sys.path.insert(0, str(LAUNCHER))
from aps5base import get, sha, load

B = Path(__file__).resolve().parent; P = B / 'proto'; P.mkdir(exist_ok=True); (P / 'package').mkdir(exist_ok=True)
args = sys.argv[1:]
tree = 'src-ports' if args[:1] == ['--ports'] else 'src'
if tree == 'src-ports': args = args[1:]
SRC, BUILD = B / tree, B / ('build-ports' if tree == 'src-ports' else 'build')
built = BUILD / 'core' / 'libs' / 'libs' / 'libSceAgcDriver.prx'
commit = subprocess.run(['git', '-C', str(SRC), 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()
frozen = P / 'package' / ('libSceAgcDriver-%s.prx' % commit)
if args[:1] == ['--reuse-frozen']:
    # Back to an earlier frozen build without rebuilding (the build directory may hold a later commit).
    # Short hashes grew from 7 to 8 digits once more objects were fetched: match on the full hash.
    full = subprocess.run(['git', '-C', str(SRC), 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()
    found = [p for p in (P / 'package').glob('libSceAgcDriver-*.prx') if full.startswith(p.stem.split('-', 1)[1])]
    assert len(found) == 1, 'no single frozen PRX for %s: %s' % (commit, found)
    frozen = found[0]; commit = frozen.stem.split('-', 1)[1]
else:
    if not frozen.exists(): shutil.copyfile(built, frozen)
    assert sha(frozen) == sha(built), 'frozen PRX differs from the current build'
base = load(LAUNCHER / 'baseline.json')
dispatch_runs = base['variants']['E-dispatchruns']['set']
cfg = {**{k: base[k] for k in ('kind', 'layout', 'layout_sha256', 'layout_exclusions', 'game_command', 'historical_runtime', 'historical_agc_sha256',
                                 'content_junction', 'private_directories', 'seed', 'seed_manifest', 'seed_manifest_sha256', 'seed_files',
                                 'fixed_environment', 'marker_script', 'gpu_sample', 'preserved')},
       'experiment': 'GT7-ASYNC-QUEUE-PROTOTYPE', 'configuration': 'prototype AGC %s (branch %s) + E flags + dispatch runs, CPU-cost log off' % (commit, tree),
       'root': str(P), 'runtime': str(P / 'runtime'), 'output_root': str(P / 'runs'), 'staging_record': str(P / 'STAGING.json'),
       'packaged_prx': str(frozen), 'packaged_sha256': sha(frozen), 'raw_prx': str(frozen), 'raw_sha256': sha(frozen),
       'E_environment': {**{k: v for k, v in base['E_environment'].items() if k != 'APS5_CPU_COSTS'}, **dispatch_runs},
       'path_prefix': [str(P / 'runtime' / 'libs'), r'C:\tools\mingw64\bin'],
       'variants': {
           'E': {'set': {}, 'note': 'parity: prototype build with APS5_ASYNC_QUEUES absent must match E-dispatchruns (2.02 FPS)'},
           'P-async4a': {'set': {'APS5_ASYNC_QUEUES': '0x4a'}, 'note': 'guest queue 0x4a on the second Vulkan queue. RESULT 2026-10-18: 2.34 FPS vs parity 2.16; 0x4a delay 5 -> 16 ms (async batches reaped only by the 0x4a worker poll)'},
           'P-async4a-eop': {'set': {'APS5_ASYNC_QUEUES': '0x4a', 'APS5_EOP_COMPLETION_THREAD': '1'},
                             'note': 'P-async4a + completion thread: each recorder\'s completions delivered when its timeline signals. RESULT 2026-10-18: 2.13 FPS; 0x4a delay 16 -> 1.05 ms, 0x20 18.7 -> 8.5 ms; 0x4a not the gating chain'},
           'P-async4a20-eop': {'set': {'APS5_ASYNC_QUEUES': '0x4a,0x20', 'APS5_EOP_COMPLETION_THREAD': '1'},
                               'note': 'queues 0x4a and 0x20 on the second Vulkan queue, with the completion thread. RESULT 2026-10-18: 2.04 FPS; completion waiting 333 -> 105 ms/frame; FPS unchanged (not the gate); user progressed further in the timed race'},
           'P-stack-profile': {'set': {'APS5_ASYNC_QUEUES': '0x4a,0x20', 'APS5_EOP_COMPLETION_THREAD': '1', 'APS5_PROFILE_DRAW': '1'},
                               'note': 'diagnostic: best stack + draw-pipeline profiler. RESULT 2026-10-18: GPU mutex held ~46% of wall time, draw committer ~1.9 s/10 s; slow prep/commit are CPU-bound (zero waits)'},
           'P-stack-fork': {'set': {'APS5_ASYNC_QUEUES': '0x4a,0x20', 'APS5_EOP_COMPLETION_THREAD': '1', 'APS5_FORK_BUILD': '1'},
                            'note': 'best stack + fork-join draw build. RESULT 2026-10-18: crashed at race initialisation (title access violation, Job#1) - not race-safe'},
           'P-stack-sample': {'set': {'APS5_ASYNC_QUEUES': '0x4a,0x20', 'APS5_EOP_COMPLETION_THREAD': '1', 'APS5_SAMPLE': '120,60,10', 'APS5_SAMPLE_THREADS': 'Agc'},
                              'run_files': {'APS5_SAMPLE_OUT': 'agc-stacks.txt'},
                              'note': 'diagnostic: best stack + in-process sampler on every named driver thread. RESULT 2026-10-18 (5c578e9): driver threads mostly waiting; head-of-line blocking in the in-order draw pipeline (q0 48% waiting for room, prep 37% waitPrepTurn, committer 71% idle)'},
           'P-pipe': {'set': {'APS5_ASYNC_QUEUES': '0x4a,0x20', 'APS5_EOP_COMPLETION_THREAD': '1', 'APS5_PREP_REORDER': '1', 'APS5_PIPELINED_DRAWS': '32'},
                      'note': 'best stack + prep reorder buffer + pipeline depth 32. RESULT 2026-10-18: hung at race init (title BVH assertion); queue 0x20 routing dropped'},
           'P-pipe-safe': {'set': {'APS5_PREP_REORDER': '1', 'APS5_PIPELINED_DRAWS': '32'},
                           'note': 'safe stack + prep reorder + depth 32. RESULT 2026-10-18: crashed at race init (title access violation, Job#8) without async routing - pipeline switches not race-load-safe'},
           'P-live': {'set': {}, 'run_files': {'APS5_LIVE_FLAGS': 'live-flags.txt'},
                      'note': 'safe stack + live-flags file, toggled mid-race by live_abba.py. RESULT 2026-10-18 (restored save): race loaded; label_known+lock_handoff+async_unordered on -> GPU batch hang within 5 s'},
           'P-live4a': {'set': {'APS5_ASYNC_QUEUES': '0x4a'}, 'run_files': {'APS5_LIVE_FLAGS': 'live-flags.txt'},
                        'note': 'play stack + live flags: prep_reorder toggled ABBA mid-race. RESULT 2026-10-18 (restored save): race loaded; reorder on +10-15% (race 1.6 -> 1.8, failure screen 2.4 -> 2.8), no glitches'},
           'P-reorder4a': {'set': {'APS5_ASYNC_QUEUES': '0x4a', 'APS5_PREP_REORDER': '1'},
                           'note': 'play stack + prep reorder from launch. RESULT 2026-10-18: stuck at race init (title BVH assertion) on a clean save - reorder not load-safe; live governor run ~1.9 FPS, felt slower -> dropped'},
           'P-chain4a': {'set': {'APS5_ASYNC_QUEUES': '0x4a', 'APS5_CHAIN': '1'},
                         'note': 'play stack + APS5_CHAIN per-queue timing (idle/backlog/order/execute per 10 s): splits the frame into guest, driver and GPU-completion time'},
           'P-split12': {'set': {'APS5_ASYNC_QUEUES': '0x4a', 'APS5_SPLIT_DRAWS': '12'},
                         'note': 'play stack with 12 draw-prep workers (E uses 6; room 8x12=96): P-chain4a showed queue 0 executing ~84% of wall time, and the sampler showed it waiting for draw-pipeline room behind in-order prep. RESULT 2026-10-19 (171bbf6): user saw <1 FPS and slow scenery pop-in; rejected (confounded: since the NVIDIA 617.42 update every run recompiles all pipelines)'},
           'P-cache4a': {'set': {'APS5_ASYNC_QUEUES': '0x4a', 'APS5_PIPELINE_CACHE_DIR': str(P / 'pipeline-cache')},
                         'note': 'play stack + writable private Vulkan pipeline cache (2e14be7c; 8967d5ff saves 8 MiB growth after 30 s since close crashes skip the teardown save). RESULT 2026-10-19: fill run 1.5 FPS; warm run 2: race-init BVH assertion; warm run 3: race start 2.4 FPS with scenery present, slower past the start line (uncached pipelines, unsaved under 2e14be7c). The protected seed file was made for NVIDIA 610.88 and is ignored by 617.42, so every run since 2026-10-18 15:14 compiled ~1100-1900 pipelines; first run fills the cache, later runs should load it'},
           'P-cache4a-map': {'set': {'APS5_ASYNC_QUEUES': '0x4a', 'APS5_PIPELINE_CACHE_DIR': str(P / 'pipeline-cache')}, 'run_files': {'APS5_WRITE_MAP': 'write-map.txt'},
                             'note': 'P-cache4a + APS5_WRITE_MAP diagnostic: which GPU writes / driver stores land on units the title CPU-wrote, to find what corrupts the PSR BVH data at race init (refit_leaf_count assertion, Job#0 index -1 crash)'},
           'P-copy4a': {'set': {'APS5_ASYNC_QUEUES': '0x4a', 'APS5_PIPELINE_CACHE_DIR': str(P / 'pipeline-cache'), 'APS5_PROFILE_DRAW': '1'},
                        'run_files': {'APS5_WRITE_MAP': 'write-map.txt', 'APS5_PERF_CONTROL': 'perf-control.txt'},
                        'note': 'P-cache4a-map + draw profiler + live performance controls: in_place_draw_inputs toggled ABBA mid-race by live_perf_abba.py (A=1 in place, the default; B=0 copied). Upstream #6763 copies draw inputs on NVIDIA Windows (Astro Bot 4.7 -> 7.5 FPS); GT7 binds ~6.7 GB per 10 s in place in the race'},
           'P-ports4a-map': {'set': {'APS5_ASYNC_QUEUES': '0x4a', 'APS5_PIPELINE_CACHE_DIR': str(P / 'pipeline-cache')}, 'run_files': {'APS5_WRITE_MAP': 'write-map.txt'},
                             'note': 'P-cache4a-map on the coherence-ports build (make_proto.py --ports; src-ports 087015890 = 56bdb76f + hand ports of upstream #6364 and #7769): candidate fix for the race-init PSR BVH corruption; the write map still captures a failure'},
           'P-ports4a-1080': {'set': {'APS5_ASYNC_QUEUES': '0x4a', 'APS5_PIPELINE_CACHE_DIR': str(P / 'pipeline-cache'), 'APS5_OPERATION_SUBMODE': '1'},
                              'note': 'play stack on the ports build at GT7 native 1920x1080 (libkernel APS5_OPERATION_SUBMODE=1, Gjonn bs49 e370775b1; World Map 19 -> 21.5 FPS for Gjonn); new resolution means new pipelines/targets, first run compiles'},
           'P-ports4a-profile': {'set': {'APS5_ASYNC_QUEUES': '0x4a', 'APS5_PIPELINE_CACHE_DIR': str(P / 'pipeline-cache'), 'APS5_PROFILE_DRAW': '1', 'APS5_CHAIN': '1',
                                          'APS5_SAMPLE': '120,150,5', 'APS5_SAMPLE_THREADS': 'Agc'}, 'run_files': {'APS5_SAMPLE_OUT': 'agc-stacks.txt'},
                                  'note': 'warm profiled run (play stack, 4K): draw profiler + per-queue chain timing + 150 s thread sampler from 120 s after launch (the warm race starts ~95 s in); splits a race frame into driver CPU, GPU waits and GPU time before the batching/serial-path work'},
           'P-spec4a-live': {'set': {'APS5_ASYNC_QUEUES': '0x4a', 'APS5_PIPELINE_CACHE_DIR': str(P / 'pipeline-cache'), 'APS5_PROFILE_DRAW': '1', 'APS5_CHAIN': '1'},
                             'run_files': {'APS5_LIVE_FLAGS': 'live-flags.txt'},
                             'note': 'draw speculation (live flag spec) toggled ABBA mid-race by live_abba.py: the prep workers (94% idle in 223042Z) do the template/BDA lookup and proofs, the committer (93 us/draw, lookup 31 + resources 22 us, serial) only re-checks. 223042Z: committer bound ~330 ms of a ~550 ms race frame'},
           'P-fork4a-live': {'set': {'APS5_ASYNC_QUEUES': '0x4a', 'APS5_PIPELINE_CACHE_DIR': str(P / 'pipeline-cache'), 'APS5_PROFILE_DRAW': '1', 'APS5_CHAIN': '1',
                                      'APS5_FORK_STATS': '1', 'APS5_FORK_DEPTH': '32'},
                             'run_files': {'APS5_LIVE_FLAGS': 'live-flags.txt'},
                             'note': 'draw plans + prebuild on the prep workers + fork-join draw build (live flags plan,parallel_build,fork_build; all off by default in our build, Gjonn runs plan=1 parallel_build=1; fork jobs need a prebuild; with fork_build the pipeline depth goes 8 -> 32) toggled ABBA mid-race by live_abba.py, so race init never sees it (P-stack-fork crashed at race init with it on from launch, during the evolving-save period). 4 fork workers build runs of same-pass draws in parallel under the committer GPU mutex; recording stays in order. Judge by draws/frame-normalized committer us/draw and [fork] lines'},
           'P-drain4a-live': {'set': {'APS5_ASYNC_QUEUES': '0x4a', 'APS5_PIPELINE_CACHE_DIR': str(P / 'pipeline-cache'), 'APS5_PROFILE_DRAW': '1', 'APS5_CHAIN': '1', 'APS5_FORK_STATS': '1'},
                              'run_files': {'APS5_LIVE_FLAGS': 'live-flags.txt'},
                              'note': 'wait_overlap (memory-wait drains end once the awaited value is in memory) + plan/parallel_build/fork_build at the normal depth 8, toggled together ABBA mid-race by live_abba.py. 225648Z: fork at depth 32 cut committer busy ~15% but drains grew 2-3x; drains here should shrink (packet drain ms) while fork keeps its committer saving. Build e7dc78df6 also names the [slow-prep] phases'},
           'P-whole4a-profile': {'set': {'APS5_ASYNC_QUEUES': '0x4a', 'APS5_PIPELINE_CACHE_DIR': str(P / 'pipeline-cache'), 'APS5_PROFILE_DRAW': '1', 'APS5_CHAIN': '1',
                                          'APS5_SAMPLE': '150,60,10', 'APS5_SAMPLE_RAW': '1'}, 'run_files': {'APS5_SAMPLE_OUT': 'all-stacks.txt'},
                                  'note': 'whole-process sampler (every thread incl. the game threads, raw guest label spins) for 60 s from 150 s after launch, play stack (wait_overlap dropped from launch after 231856Z crashed at race init, PSR_BVH data in r15). 223042Z/225648Z/230939Z: speculation, fork build and wait_overlap each cut driver-side costs without moving FPS (~2.0): every driver thread mostly waits, so the frame is set elsewhere; this finds what the game threads wait for'},
           'P-fence4a-watch': {'set': {'APS5_ASYNC_QUEUES': '0x4a', 'APS5_PIPELINE_CACHE_DIR': str(P / 'pipeline-cache'), 'APS5_PROFILE_DRAW': '1', 'APS5_CHAIN': '1',
                                        'APS5_LABEL_WATCH': '125b000000-125e000000'},
                                'note': 'label watch over the GT7 frame fences: 232148Z whole-process sampler showed every Job thread (Job#0 97% busy) spinning `while (*p != 0)` on 0x125b996f80 / 0x125b2c6f80 (alternating, value 1). Names the queue packet that writes them and how long after its submission was queued; nothing printed beyond the arming line = no queue packet writes them'},
           'P-unordered4a-live': {'set': {'APS5_ASYNC_QUEUES': '0x4a', 'APS5_PIPELINE_CACHE_DIR': str(P / 'pipeline-cache'), 'APS5_PROFILE_DRAW': '1', 'APS5_CHAIN': '1',
                                           'APS5_LABEL_WATCH': '125b000000-125e000000'},
                                   'run_files': {'APS5_LIVE_FLAGS': 'live-flags.txt'},
                                   'note': 'async_unordered alone, toggled ABBA mid-race by live_abba.py. 233545Z label watch: GT7 frame fences (value 0 RELEASE_MEM) come from compute queues 0x20/0x2b, the first of each frame 200-290 ms after it was queued, because wait-free async submissions are held behind every earlier queue-0 submission (orderReleased; [chain] order 66-84% on 0x20/0x24/0x2b/0x2c/0x4a). Gjonn runs async_unordered=1. Earlier mid-race test turned it on together with label_known+lock_handoff and hung the GPU in 5 s'},
           'P-play4a': {'set': {'APS5_ASYNC_QUEUES': '0x4a', 'APS5_PIPELINE_CACHE_DIR': str(P / 'pipeline-cache')},
                        'run_files': {'APS5_LIVE_FLAGS': 'live-flags.txt'},
                        'note': 'play setup, no profilers: race loads with every live flag off, then `live_abba.py proto/runs fork_stats 120 30 0 async_unordered,wait_overlap,plan,parallel_build,fork_build` turns the five on at 120 s and leaves them on. 235430Z: those four on top of async_unordered gave 1.82 -> 2.37 FPS mean (+30%), draws 41k -> 53k per 10 s, responsive driving'},
           'P-splitind-live': {'set': {'APS5_ASYNC_QUEUES': '0x4a', 'APS5_PIPELINE_CACHE_DIR': str(P / 'pipeline-cache'), 'APS5_PROFILE_DRAW': '1', 'APS5_CHAIN': '1'},
                               'run_files': {'APS5_LIVE_FLAGS': 'live-flags.txt'},
                               'note': 'split_indirect (24de97fab) toggled ABBA on top of the held play stack: `live_abba.py proto/runs split_indirect 120 30 8 async_unordered,wait_overlap,plan,parallel_build,fork_build`. 235430Z with that stack: indirect drains ~0.75 s + committer idle while draining ~1.4 s per 10 s'},
           'P-backoff-live': {'set': {'APS5_PIPELINE_CACHE_DIR': str(P / 'pipeline-cache'), 'APS5_PROFILE_DRAW': '1', 'APS5_CHAIN': '1', 'APS5_FORK_STATS': '1'},
                              'run_files': {'APS5_LIVE_FLAGS': 'live-flags.txt'},
                              'note': 'no second Vulkan queue, like P-load-noasync (APR fix 4b223d0a9 confirmed 3/3 there). fork_backoff_short (a86ee9ba0) toggled ABBA on top of the held play stack: `live_abba.py proto/runs fork_backoff_short 120 30 8 async_unordered,wait_overlap,plan,parallel_build,fork_build,split_indirect`. 230939Z fork-on window: 16.6k normal commits at 125 us vs 31.3k forked at 41 us per 10 s, 8.9k runs cut by the 16-run refusal backoff'},
           'P-rescache32k': {'set': {'APS5_PIPELINE_CACHE_DIR': str(P / 'pipeline-cache'), 'APS5_PROFILE_DRAW': '1', 'APS5_CHAIN': '1', 'APS5_FORK_STATS': '1',
                                     'APS5_RESOURCE_CACHE_ENTRIES': '32768'},
                             'run_files': {'APS5_LIVE_FLAGS': 'live-flags.txt'},
                             'note': 'P-backoff-live with the resource cache at 32768 entries (E has 8192). 180513Z play-stack windows: [rescache] dispatch ~9k hits / ~34k misses per 10 s, misses mostly V# base churn (ring allocations?), draws ~83% hits. Whole-run comparison vs its A+H windows (2.14 FPS, 49.6k draws/10 s): `live_abba.py proto/runs fork_stats 120 30 0 async_unordered,wait_overlap,plan,parallel_build,fork_build,split_indirect`. Entries pin textures past the texture budgets: watch VRAM / device lost'},
           'P-idp-live': {'set': {'APS5_PIPELINE_CACHE_DIR': str(P / 'pipeline-cache'), 'APS5_PROFILE_DRAW': '1', 'APS5_CHAIN': '1', 'APS5_FORK_STATS': '1'},
                          'run_files': {'APS5_LIVE_FLAGS': 'live-flags.txt'},
                          'note': 'indirect_draw_params (81ec707a4) toggled ABBA on top of the held play stack: `live_abba.py proto/runs indirect_draw_params 120 30 8 async_unordered,wait_overlap,plan,parallel_build,fork_build,split_indirect`. 183116Z: all ~6k CPU-side indirect draws per 10 s are s16/s17 shared ("patched SGPR not folded"), 57% empty; each drained the draw pipeline. ON: [draws] indirect line should move them to gpu-side and the drains/committer prep-room idle should fall. First ON block compiles the few vertex variants'},
           'P-idp-profile': {'set': {'APS5_PIPELINE_CACHE_DIR': str(P / 'pipeline-cache'), 'APS5_PROFILE_DRAW': '1', 'APS5_CHAIN': '1',
                                     'APS5_SAMPLE': '170,60,10', 'APS5_SAMPLE_RAW': '1', 'APS5_LABEL_WATCH': '125b000000-125e000000'},
                             'run_files': {'APS5_LIVE_FLAGS': 'live-flags.txt', 'APS5_SAMPLE_OUT': 'all-stacks.txt'},
                             'note': 'what the game waits on once queue 0 keeps up: 185348Z with indirect_draw_params on had queue 0 idle 1.1-2.8 s per 10 s waiting for submissions, GPU ~37%. Whole-process sampler 170-230 s (raw guest spins), chain timing per queue, label watch over the frame-fence range (232148Z/233545Z: fences 0x125b..-0x125d.. written by RELEASE_MEM on 0x20/0x2b). Play stack + indirect_draw_params held from 120 s: `live_abba.py proto/runs fork_stats 120 30 0 async_unordered,wait_overlap,plan,parallel_build,fork_build,split_indirect,indirect_draw_params`'},
           'P-handoff-live': {'set': {'APS5_PIPELINE_CACHE_DIR': str(P / 'pipeline-cache'), 'APS5_PROFILE_DRAW': '1', 'APS5_CHAIN': '1', 'APS5_FORK_STATS': '1'},
                              'run_files': {'APS5_LIVE_FLAGS': 'live-flags.txt'},
                              'note': 'lock_handoff toggled ABBA on top of the held play stack + indirect_draw_params: `live_abba.py proto/runs lock_handoff 120 30 8 async_unordered,wait_overlap,plan,parallel_build,fork_build,split_indirect,indirect_draw_params`. 190844Z profile: nothing saturated (Job#0 59% idle-polling its job queues + 21% on a GPU frame fence, committer 30%, GPU ~37%); queue 0x22 (15-29k dispatches per 10 s, execute 7-9 s per 10 s) waited 4.1-4.8 s per 10 s for the GPU mutex the draw committer holds 5.4-7.8 s per 10 s (SRW lock not fair: the committer re-acquires per draw). 2026-10-18 lock_handoff alone: no gain, but the frame-fence hold dominated then; label_known+lock_handoff+async_unordered together hung the GPU (label_known not used here)'},
           'P-lockrun-live': {'set': {'APS5_PIPELINE_CACHE_DIR': str(P / 'pipeline-cache'), 'APS5_PROFILE_DRAW': '1', 'APS5_CHAIN': '1', 'APS5_FORK_STATS': '1'},
                              'run_files': {'APS5_LIVE_FLAGS': 'live-flags.txt'},
                              'note': 'dispatch_lock_runs (351bb3913) toggled ABBA on top of the held play stack + indirect_draw_params: `live_abba.py proto/runs dispatch_lock_runs 120 30 8 async_unordered,wait_overlap,plan,parallel_build,fork_build,split_indirect,indirect_draw_params`. 190844Z: queue 0x22 waited 4.1-4.8 s per 10 s for the GPU mutex in ~7-9k of 17-33k acquisitions; lock_handoff (fair hand-off) hung the GPU (192203Z). Compare [lock] queue 0x22 waits, [chain] 0x22 execute, queue-0 idle and FPS per block'},
           'P-kinds-profile': {'set': {'APS5_PIPELINE_CACHE_DIR': str(P / 'pipeline-cache'), 'APS5_PROFILE_DRAW': '1', 'APS5_CHAIN': '1', 'APS5_FORK_STATS': '1'},
                               'run_files': {'APS5_LIVE_FLAGS': 'live-flags.txt'},
                               'note': 'per-kind draw phase costs ([draw-kinds], diag commit after e1075b0c9) with the play stack held from 120 s (no toggling, no indirect_draw_params): `live_abba.py proto/runs fork_stats 120 30 0 async_unordered,wait_overlap,plan,parallel_build,fork_build,split_indirect`. 194943Z: BDA template hits 250-320 us each (35-38k per 10 s) vs plain template hits 80-104 us: find the phase'},
           'P-trace-indirect': {'set': {'APS5_PIPELINE_CACHE_DIR': str(P / 'pipeline-cache'), 'APS5_TRACE_INDIRECT_DRAWS': '1'},
                                'run_files': {'APS5_LIVE_FLAGS': 'live-flags.txt'},
                                'note': 'diagnostic: per indirect draw the shader analyzer view (vertex/instance offset SGPR, shared, conflict) vs the SGPRs the packet writes, and the records. ~6.1k indirect draws per 10 s take the CPU path as "patched SGPR not folded" (180513Z); each needs the draw pipeline empty first, ~2-2.8 s committer idle per 10 s. Decides whether they can go GPU-side. Play stack held from 120 s: `live_abba.py proto/runs fork_stats 120 30 0 async_unordered,wait_overlap,plan,parallel_build,fork_build,split_indirect`'},
           'P-loadmap4a': {'set': {'APS5_ASYNC_QUEUES': '0x4a', 'APS5_PIPELINE_CACHE_DIR': str(P / 'pipeline-cache'), 'APS5_WRITE_MAP_SECONDS': '2'},
                           'run_files': {'APS5_WRITE_MAP': 'write-map.txt'},
                           'note': 'race-load corruption hunt (6645d91a5): write map every 2 s plus on a rejected submission, now with M events for guest allocation changes. 002113Z failed loading with a zeroed command buffer at 0x125cf54100 inside allocation 0x125ce00000+0x200000, right after "leased allocation ... still pinned after 8 recorder syncs" for that same allocation; other failures are the PSR BVH assertion / Job#N crashes'},
           'P-load-noasync': {'set': {'APS5_PIPELINE_CACHE_DIR': str(P / 'pipeline-cache')},
                              'run_files': {'APS5_LIVE_FLAGS': 'live-flags.txt'},
                              'note': 'race-load test without the second Vulkan queue (no APS5_ASYNC_QUEUES=0x4a, which every variant since 2026-10-18 had). 0x20 on that queue gave the PSR BVH assertion at race init; the BVH assertion / Job#N crashes / zeroed command buffers hit ~half the loads with 0x4a, and the storeOwn fix 8471363cb did not stop them (003618Z). Live flags file so the play stack can still be held on after 120 s'},
           'P-split12-warm': {'set': {'APS5_ASYNC_QUEUES': '0x4a', 'APS5_PIPELINE_CACHE_DIR': str(P / 'pipeline-cache'), 'APS5_SPLIT_DRAWS': '12',
                                       'APS5_PROFILE_DRAW': '1', 'APS5_CHAIN': '1'},
                              'note': 'warm retest of 12 draw-prep workers (P-split12 was confounded by the 617.42 compile storm), profiled like P-ports4a-profile 205957Z (prep 567 us/draw on 6 workers, 4.0 s/10 s waiting for room; committer 85 us/draw)'},
           'P-port4a': {'set': {'APS5_ASYNC_QUEUES': '0x4a'},
                        'note': 'play stack on the build with Gjonn ports 18e09c7a6 (wake idle queue 0 for completions) + 85a4c828b (hand-off spin 150 us, draw-path trims); compare with P-async4a ~2.0-2.5. RESULT 2026-10-18 (5c36e144, original save): menus ~18-19 FPS; crashed right after race Initialising (title access violation Job#0, mesh adjacency 0xffffffff)'},
           'P-port4a-nospin': {'set': {'APS5_ASYNC_QUEUES': '0x4a', 'APS5_HANDOFF_SPIN_US': '0'},
                               'note': 'P-port4a with the hand-off spin off: isolates the spin (lock timing) from the queue-0 wake and the trims'}},
       'limits': {**base['limits'], 'run_output_bytes': 32 << 20, 'log_head_bytes': 2 << 20, 'log_tail_bytes': 4 << 20},
       'budget': {'preserved_retained_bytes': base['budget']['preserved_retained_bytes'], 'static_cap_bytes': 3 << 30,  # 1 -> 3 GiB (user, 2026-10-19): private pipeline cache ~0.7 GB plus its atomic-save copy
                  'tooling_cap_bytes': base['budget']['tooling_cap_bytes'], 'run_output_allocation_bytes': 256 << 20,
                  'basis': 'Development workspace (10 GiB cap, outside the 512 MiB experiment ledger).'}}
# The ports tree also replaces libkernel (APS5_OPERATION_SUBMODE, Gjonn bs49 e370775b1; default submode 0 as
# before): its own layout lists the frozen libkernel instead of the CPUCosts one, which it is built from.
if tree == 'src-ports':
    kernel = P / 'package' / ('libkernel-%s.prx' % commit)
    if not kernel.exists(): shutil.copyfile(BUILD / 'core' / 'libs' / 'libs' / 'libkernel.prx', kernel)
    assert sha(kernel) == sha(BUILD / 'core' / 'libs' / 'libs' / 'libkernel.prx'), 'frozen libkernel differs from the current build'
    layout = load(cfg['layout'])
    for r in layout['files']:
        if r['relative'].lower() == r'libs\libkernel.prx':
            r.update({'source': str(kernel), 'bytes': kernel.stat().st_size, 'sha256': sha(kernel), 'identity': get(kernel)['identity']})
    layout['status'] = 'PROTO_LAYOUT (baseline layout, libkernel from %s)' % kernel.name
    (P / 'PROTO-LAYOUT.json').write_text(json.dumps(layout, indent=2), encoding='utf-8')
    cfg['layout'], cfg['layout_sha256'] = str(P / 'PROTO-LAYOUT.json'), sha(P / 'PROTO-LAYOUT.json')
(P / 'proto.json').write_text(json.dumps(cfg, indent=2), encoding='utf-8')
print('frozen', frozen.name, cfg['packaged_sha256'][:16])
