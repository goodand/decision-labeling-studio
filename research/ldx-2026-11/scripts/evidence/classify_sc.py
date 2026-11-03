"""세션 사용자 메시지를 시나리오별 키워드 규칙으로 분류해 빈도를 센다(LLM 판정 없음)."""
import json, re, sys, collections
sys.stdout.reconfigure(encoding="utf-8")

RULES = {
    "SC1 어디에 무엇이(소스 위치)": r"어느 DB|어떤 DB|무슨 DB|DB는\?|들어 있는|우리가 다루는|어디에 (있|저장)|파일 (있|없)|DB를 더 넓|sqlite, csv|엑셀 또는 sqlite",
    "SC2 사업명 검색": r"검색|찾아|찾았|안 나오|못 찾|어디에도 없|누락",
    "SC3 두 소스 대조": r"대조|비교|일치|불일치|같은 것 맞|다르|동일 사업|vs|양쪽|매핑|대응",
    "SC4 개수 세기": r"몇 개|갯수|개수|몇 건|몇 행|count|몇개",
    "SC5 열·연도·type 확인": r"column|열 |컬럼|회계연도|대상연도|연도|type|세부사업|내역사업|내내역|단위",
    "SC6 사람이 고친 엑셀": r"엑셀.*(수정|READ|다시|초기화|열어)|내가 (수정|만든|고친)|직접 수정",
    "SC7 내부·공유금지": r"내부|공유금지|인용|유출|원문 인용",
    "SC8 결과 신뢰·완전성": r"믿을 수|누락한|빠진|전부|다 본|확인했|검증|근거",
}

def texts(path):
    seen = set()
    for line in open(path, encoding="utf-8"):
        try:
            o = json.loads(line)
        except Exception:
            continue
        if o.get("type") != "user":
            continue
        c = o.get("message", {}).get("content")
        t = " ".join(x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text") if isinstance(c, list) else (c or "")
        t = t.strip()
        if not t or t.startswith(("<", "Base directory", "# ", "This session is being continued")) or "cross-session-message" in t:
            continue
        key = t[:120]
        if key in seen:  # 같은 메시지가 재생(재개)으로 중복된 경우 1회만
            continue
        seen.add(key)
        yield o.get("timestamp", "")[:10], t

path = sys.argv[1]
msgs = list(texts(path))
db_related = [(d, t) for d, t in msgs if re.search(r"DB|db|sqlite|엑셀|xlsx|csv|CSV|시트|테이블|조회", t)]
print(f"사용자 메시지(중복 제거) {len(msgs)}건, DB·엑셀 관련 {len(db_related)}건")
cnt = collections.Counter(); ex = collections.defaultdict(list); days = collections.defaultdict(set)
for d, t in db_related:
    for sc, pat in RULES.items():
        if re.search(pat, t, re.I):
            cnt[sc] += 1; days[sc].add(d)
            if True:
                ex[sc].append(t[:90].replace("\n", " "))
for sc in RULES:
    print(f"\n{sc}: {cnt[sc]}건, {len(days[sc])}일")
    for e in ex[sc]:
        print("   -", e)
