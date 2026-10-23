// audit_cards.location(XPath) → rhwp 위치 판정. 순수 함수(브라우저·node 공용).
// XPath 예: /HwpDoc/BodyText/SectionDef[1]/ColumnSet/Paragraph[13]/LineSeg/TableControl/.../TableCell[3]/Paragraph
//   SectionDef[s] → sec s-1, 첫 Paragraph[p] → para p-1, 표 안이면 마지막 Paragraph[k](번호 없으면 1) → cellPara k-1.
export function parseXPath(loc) {
  if (typeof loc !== 'string' || !loc.startsWith('/HwpDoc/BodyText/')) return null;
  const parts = loc.split('/'), num = s => { const m = /\[(\d+)\]$/.exec(s); return m ? +m[1] : 1; };
  const si = parts.findIndex(x => x.startsWith('SectionDef')), pi = parts.findIndex((x, i) => i > si && x.startsWith('Paragraph'));
  if (si < 0 || pi < 0) return null;
  const tables = parts.filter(x => x === 'TableControl').length;
  if (tables > 1) return null; // 중첩 표는 대응 규칙 미확인
  const r = { sec: num(parts[si]) - 1, para: num(parts[pi]) - 1, cellPara: null };
  if (tables) { const last = parts.map((x, i) => [x, i]).filter(([x, i]) => i > pi && x.startsWith('Paragraph')).pop(); if (!last) return null; r.cellPara = num(last[0]) - 1; }
  return r;
}

export const searchKey = q => (q || '').trim().slice(0, 40);

// matches: rhwp searchAllText 결과. XPath와 같은 위치의 일치만 'ok'.
export function pickMatch(matches, loc) {
  const x = parseXPath(loc);
  if (!matches.length) return { status: 'not_found', reason: '원본에서 인용 문자열을 찾지 못함' };
  if (!x) return { status: 'xpath_unreadable', reason: 'XPath를 해석할 수 없음(인용 ' + matches.length + '곳 발견)' };
  const hit = matches.find(m => m.sec === x.sec && (x.cellPara == null
    ? !m.cellContext && m.para === x.para
    : m.cellContext && m.cellContext.parentPara === x.para && m.cellContext.cellPara === x.cellPara));
  return hit ? { status: 'ok', match: hit } : { status: 'xpath_mismatch', reason: 'XPath 위치에 인용 없음(다른 곳 ' + matches.length + '곳 발견)' };
}

// 실제 표시 쪽. getPageOfPosition은 표가 시작하는 쪽을 주므로(여러 쪽 표에서 틀림),
// 그 쪽부터 앞으로 훑어 해당 문단(표 안이면 그 칸의 문단)의 글자 run이 있는 첫 쪽을 고른다.
export function pageOfMatch(doc, m, maxScan = 30) {
  const j = s => { try { return JSON.parse(s); } catch { return null; } };
  const c = m.cellContext, start = j(doc.getPageOfPosition(m.sec, c ? c.parentPara : m.para));
  if (!start || !start.ok || !Number.isInteger(start.page)) return null;
  const end = Math.min(doc.pageCount(), start.page + maxScan);
  for (let p = start.page; p < end; p++) {
    const runs = (j(doc.getPageTextLayout(p)) || {}).runs || [];
    const hit = runs.some(r => r.secIdx === m.sec && (c
      ? r.parentParaIdx === c.parentPara && r.controlIdx === c.ctrlIdx && r.cellIdx === c.cellIdx && r.cellParaIdx === c.cellPara
      : r.paraIdx === m.para && !r.cellPath) && r.charStart <= m.charOffset + m.length && r.charStart + r.text.length > m.charOffset);
    if (hit) return p;
  }
  return null;
}
