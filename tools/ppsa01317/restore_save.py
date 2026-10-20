"""Restore the proto private save to its original state.

Usage: python -I -B restore_save.py <run_dir>
Refuses unless <run_dir>/exit.json exists. Moves the current private
directories into proto/saved-state-<UTC>, recreates them, copies the
private-initial-copy files from PROTO-LAYOUT.json and verifies sha256.
"""
import datetime, hashlib, json, os, shutil, sys

PROTO = r"C:\Users\Koiki\Documents\Project\AnyPS5-upstream\branch\proto"
RUNTIME = os.path.join(PROTO, "runtime")

run_dir = sys.argv[1]
if not os.path.isfile(os.path.join(run_dir, "exit.json")):
    sys.exit(f"refusing: no exit.json in {run_dir}")

with open(os.path.join(PROTO, "PROTO-LAYOUT.json"), encoding="utf-8") as f:
    layout = json.load(f)

stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
saved = os.path.join(PROTO, f"saved-state-{stamp}")
os.makedirs(saved)
for d in layout["private_directories"]:
    src = os.path.join(RUNTIME, d)
    if os.path.exists(src):
        shutil.move(src, os.path.join(saved, d))
    os.makedirs(src)

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

bad = 0
for e in layout["files"]:
    if e["role"] != "private-initial-copy":
        continue
    dst = os.path.join(RUNTIME, e["relative"])
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(e["source"], dst)
    ok = sha256(dst) == e["sha256"] and os.path.getsize(dst) == e["bytes"]
    bad += not ok
    print("ok " if ok else "BAD", e["relative"])

print(f"previous state moved to {saved}")
sys.exit(1 if bad else 0)
