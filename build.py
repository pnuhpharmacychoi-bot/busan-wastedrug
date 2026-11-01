"""부산 폐의약품 수거함 페이지 만들기

부산광역시 공공데이터(폐의약품 수거함 현황) API에서 최신 데이터를 받아
template.html에 넣어 index.html을 만든다.
GitHub Actions가 매주 자동으로 실행하며, 키는 저장소 비밀값 DATA_GO_KR_KEY에서 읽는다.
데이터를 제대로 못 받으면 index.html을 건드리지 않고 실패로 끝난다(기존 페이지 유지).
"""
import json, os, re, sys, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

API = "https://apis.data.go.kr/6260000/WasteMedicineBoxService/getWasteMedicineBox"
MIN_ROWS = 100  # 이보다 적게 오면 뭔가 잘못된 것으로 보고 갱신하지 않음

def fail(msg):
    print("갱신 실패:", msg)
    sys.exit(1)

def fetch_all(key):
    rows, page, per = [], 1, 1000
    while True:
        url = f"{API}?serviceKey={key}&pageNo={page}&numOfRows={per}&resultType=json"
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                body = r.read().decode("utf-8")
        except Exception as e:
            fail(f"API 호출 오류: {e}")
        try:
            d = json.loads(body)
        except ValueError:
            fail("API가 JSON이 아닌 응답을 보냄(키 만료·오류 가능): " + body[:300])
        if "response" not in d:
            fail("API 오류 응답: " + body[:300])
        head = d["response"]["header"]
        if head.get("resultCode") != "00":
            fail(f"API 결과 코드 {head.get('resultCode')}: {head.get('resultMsg')}")
        b = d["response"]["body"]
        items = (b.get("items") or {}).get("item") or []
        if isinstance(items, dict):
            items = [items]
        rows += items
        total = int(b.get("totalCount") or 0)
        if not items or len(rows) >= total:
            return rows, total
        page += 1

def clean(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()

def classify(name, pos):
    s = name + " " + pos
    if "약국" in s: return "P"
    if re.search(r"초등학교|중학교|고등학교|보건실", s): return "R"
    if re.search(r"행정복지센터|주민센터|보건소|보건지소|건강생활지원센터|구청|군청|민원", s): return "G"
    if re.search(r"경로당|아파트|마을회관|노인정|할머니|할아버지|사랑방|분회|집하장|집히장|재활용|분리수거|관리사무|놀이터|\d+동", s): return "R"
    return "O"

def main():
    raw = os.environ.get("DATA_GO_KR_KEY", "").strip()
    if not raw:
        fail("저장소 비밀값 DATA_GO_KR_KEY가 비어 있음")
    key = raw if "%" in raw else urllib.parse.quote(raw, safe="")
    items, total = fetch_all(key)
    rank = {"P": 0, "G": 1, "O": 2, "R": 3}
    # 구·군 이름을 가나다순으로 정렬 (새 구가 생겨도 자동으로 제자리에 들어감)
    gu = sorted({clean(it.get("sggNm")) for it in items if clean(it.get("sggNm"))})
    out = []
    for it in items:
        try:
            lng, lat = float(it["xcor"]), float(it["ycor"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (34.8 < lat < 35.6 and 128.6 < lng < 129.5):
            continue  # 부산 밖 좌표는 제외
        g = clean(it.get("sggNm"))
        if not g:
            continue
        name, addr, pos = clean(it.get("conm")), clean(it.get("dtlAddr")), clean(it.get("pstnCn"))
        out.append([gu.index(g), name, addr, pos, round(lng, 6), round(lat, 6), classify(name, pos)])
    if len(out) < MIN_ROWS:
        fail(f"받은 수거함이 {len(out)}곳뿐이라 갱신하지 않음 (API 총계 {total})")
    out.sort(key=lambda r: (r[0], rank[r[6]], r[1]))
    now = datetime.now(timezone(timedelta(hours=9)))
    asof = f"{now.year}년 {now.month}월 {now.day}일"
    data = json.dumps({"gu": gu, "rows": out}, ensure_ascii=False, separators=(",", ":"))
    here = os.path.dirname(os.path.abspath(__file__))
    tpl = open(os.path.join(here, "template.html"), encoding="utf-8").read()
    html = (tpl.replace("__DATA__", data)
               .replace("__TOTAL__", f"{len(out):,}")
               .replace("__ASOF__", asof))
    if raw in html or key in html:
        fail("키가 페이지에 들어갈 뻔해서 중단함")
    with open(os.path.join(here, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print(f"갱신 완료: {len(out)}곳, {asof} 기준")

if __name__ == "__main__":
    main()
