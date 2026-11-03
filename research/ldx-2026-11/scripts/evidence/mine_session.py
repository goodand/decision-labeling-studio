import json, sys, re, collections
sys.stdout.reconfigure(encoding="utf-8")
path = sys.argv[1]
calls = []
files = collections.Counter()
kinds = collections.Counter()
pat = re.compile(r"[A-Za-z]:[\\/][^\"' \n]+?\.(?:sqlite|db|xlsx|csv)")
for line in open(path, encoding="utf-8"):
    try:
        o = json.loads(line)
    except Exception:
        continue
    if o.get("type") != "assistant":
        continue
    for x in o.get("message", {}).get("content", []) or []:
        if not (isinstance(x, dict) and x.get("type") == "tool_use"):
            continue
        name = x["name"]
        s = json.dumps(x.get("input", {}), ensure_ascii=False)
        if re.search(r"sqlite|duckdb|select |SELECT |openpyxl|read_excel|\.xlsx|\.csv", s):
            kinds[name] += 1
            for m in pat.findall(s):
                files[m.replace("\\\\", "\\")] += 1
            calls.append((o.get("timestamp", "")[:16], name, s[:260].replace("\n", " ")))
print("DB/엑셀 관련 도구 호출", sum(kinds.values()), dict(kinds))
print("\n자주 쓴 파일:")
for f, c in files.most_common(20):
    print(f" {c:3d} {f}")
print("\n표본 호출(간격 샘플 40개):")
step = max(1, len(calls) // 40)
for t, n, s in calls[::step][:40]:
    print(f"{t} {n}: {s}")
