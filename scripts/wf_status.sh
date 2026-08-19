#!/usr/bin/env bash
# Estado de un workflow de Claude Code leyendo su journal en disco.
# Uso: ./scripts/wf_status.sh [run_id]   (por defecto: el mas reciente)
set -euo pipefail

BASE="$HOME/.claude/projects/-Users-cloudnonic-Desktop-university-pg-IdeoGraphCO"
RUN="${1:-}"
if [[ -z "$RUN" ]]; then
  DIR=$(find "$BASE" -type d -name 'wf_*' -maxdepth 4 2>/dev/null \
        | xargs -I{} stat -f '%m %N' {} | sort -rn | head -1 | cut -d' ' -f2-)
else
  DIR=$(find "$BASE" -type d -name "*${RUN}*" -maxdepth 4 2>/dev/null | head -1)
fi
[[ -z "${DIR:-}" ]] && { echo "no encontre ningun workflow"; exit 1; }

echo "workflow : $(basename "$DIR")"
echo "hora     : $(date '+%H:%M:%S')"
echo

python3 - "$DIR" <<'PYEOF'
import json, os, sys, time, collections
d = sys.argv[1]
jp = os.path.join(d, 'journal.jsonl')
started = 0
buckets = collections.Counter()
counts = collections.Counter()
texts = 0
if os.path.exists(jp):
    for line in open(jp):
        try: rec = json.loads(line)
        except Exception: continue
        if rec.get('type') == 'started':
            started += 1; continue
        r = rec.get('result')
        if isinstance(r, dict):
            # cualquier lista dentro del resultado cuenta como "hallazgos"
            for k, v in r.items():
                if isinstance(v, list):
                    buckets[k] += 1
                    counts[k] += len(v)
        elif isinstance(r, str):
            texts += 1

done = sum(buckets.values()) + texts
print(f"agentes lanzados  : {started}")
print(f"agentes con result: {done}")
for k in sorted(buckets):
    print(f"  {k:14} {buckets[k]:3} agentes -> {counts[k]:5} items")
if texts:
    print(f"  {'informes':14} {texts:3} (sintesis / critica)")
print()

now = time.time()
files = sorted((f for f in os.listdir(d) if f.startswith('agent-') and f.endswith('.jsonl')),
               key=lambda f: os.path.getmtime(os.path.join(d, f)))
print("agente     ultima escritura   tamano   estado")
for f in files:
    p = os.path.join(d, f)
    age = now - os.path.getmtime(p)
    estado = "ACTIVO" if age < 90 else ("pausado" if age < 600 else "terminado")
    stamp = time.strftime('%H:%M:%S', time.localtime(os.path.getmtime(p)))
    print(f"{f[6:14]}   {stamp}          {os.path.getsize(p)//1024:4}K   {estado} ({int(age)}s)")
PYEOF
