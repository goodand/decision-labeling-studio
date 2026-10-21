// 위치 판정: dataset.unlocated.json + 설정의 locate 규칙 → dataset.json (위치·쪽·이유). 원본은 읽기만 한다.
//   node adapters/program_link/locate.mjs <rhwp dir> <dataset.unlocated.json> <dataset.json>
// 확실한 위치만 status 'ok'. 그 외는 'unlocatable' + 이유(추측 하이라이트 금지).
import fs from 'fs';
import { pageOfMatch } from '../../ui/conflict/hwp_locate.js';

const [rhwpDir, inPath, outPath] = process.argv.slice(2);
const m = await import('file:///' + rhwpDir.replace(/\\/g, '/') + '/rhwp.js');
globalThis.measureTextWidth = (font, text) => text.length * 10; // node엔 canvas가 없다. 쪽 확정은 run 스캔으로 한다.
await m.default({ module_or_path: fs.readFileSync(rhwpDir + '/rhwp_bg.wasm') });

const data = JSON.parse(fs.readFileSync(inPath, 'utf8')), R = data.locate_rules;
const J = s => { try { return JSON.parse(s); } catch { return null; } }, T = f => { try { return f(); } catch { return null; } };
const docs = {};
const open = id => docs[id] ??= (() => { const d = data.docs[id]; if (d.status !== 'ok') return { err: d.status };
  try { return new m.HwpDocument(new Uint8Array(fs.readFileSync(d.path))); } catch (e) { return { err: 'rhwp 열기 실패: ' + e.message }; } })();
const search = (doc, q) => (q && q.trim() ? J(T(() => doc.searchAllText(q, false, true))) || [] : []);
const labels = R.answer_name_labels.map(x => new RegExp(x));

function cellText(doc, sec, pp, ci, cell) {
  const n = T(() => doc.getCellParagraphCount(sec, pp, ci, cell)) || 0; let t = '';
  for (let k = 0; k < n; k++) { const len = T(() => doc.getCellParagraphLength(sec, pp, ci, cell, k)); if (len) t += (T(() => doc.getTextInCell(sec, pp, ci, cell, k, 0, len)) || '') + ' '; }
  return t.trim();
}
// 같은 행에서 바로 왼쪽 칸의 글자(표 밖이면 null)
function leftLabel(doc, mt) {
  const c = mt.cellContext; if (!c) return null;
  const me = J(T(() => doc.getCellInfo(mt.sec, c.parentPara, c.ctrlIdx, c.cellIdx))); if (!me) return null;
  for (let i = 0; i < 2000; i++) {
    const x = J(T(() => doc.getCellInfo(mt.sec, c.parentPara, c.ctrlIdx, i))); if (!x) break;
    if (x.row <= me.row && x.row + x.rowSpan > me.row && x.col + x.colSpan === me.col) return cellText(doc, mt.sec, c.parentPara, c.ctrlIdx, i);
  }
  return null;
}
const ok = (doc, mt, rule, query) => { const page = pageOfMatch(doc, mt);
  return page == null ? { status: 'unlocatable', reason: '찾은 위치가 그려진 쪽을 확인하지 못함', rule, query }
    : { status: 'ok', rule, query, page, match: { sec: mt.sec, para: mt.para, cellContext: mt.cellContext || null, charOffset: mt.charOffset, length: mt.length } }; };

// A: 결과서 표기. 원래 표기 → 정리된 이름 순서로, '사업명' 칸 유일 → 문서 전체 유일 일 때만 확정.
function locateAnswer(doc, mention, searchName) {
  const tried = [];
  for (const q of [mention.original, searchName]) {
    if (tried.some(t => t.query === q)) continue;
    const ms = search(doc, q), labelled = ms.filter(mt => { const l = leftLabel(doc, mt); return l != null && labels.some(r => r.test(l)); });
    tried.push({ query: q, matches: ms.length, labelled: labelled.length });
    if (labelled.length === 1) return ok(doc, labelled[0], 'label_unique', q);
    if (labelled.length > 1) return { status: 'unlocatable', reason: `'사업명' 칸에 ${labelled.length}곳`, tried };
    if (ms.length === 1) return ok(doc, ms[0], 'global_unique', q);
  }
  const t = tried.map(x => `"${x.query}" ${x.matches}곳`).join(', ');
  return { status: 'unlocatable', reason: tried.every(x => !x.matches) ? '원문에서 표기를 찾지 못함 (' + t + ')' : '여러 곳에 있고 사업명 칸으로 특정되지 않음 (' + t + ')', tried };
}
// B: 예산서 구획. 세부사업=파일 제목 유일, 내역사업=DB 원문 앞부분이 문서에서 유일.
function locateSegment(doc, s) {
  if (s.레벨명 === '세부사업') {
    const ms = search(doc, s.title);
    return ms.length === 1 ? ok(doc, ms[0], 'title_unique', s.title) : { status: 'unlocatable', reason: `파일 제목 "${s.title}" ${ms.length}곳` };
  }
  const raws = s.content.map(c => c.원문).filter(Boolean);
  if (!raws.length) return { status: 'unlocatable', reason: 'DB에 이 구획의 사업내용 원문이 없어 위치 기준이 없음' };
  const tried = [];
  for (const raw of raws) for (const n of R.budget_raw_prefix_lengths) {
    const q = raw.trim().slice(0, n); if (tried.some(t => t.query === q)) continue;
    const ms = search(doc, q); tried.push({ query: q.slice(0, 20) + '…', matches: ms.length });
    if (ms.length === 1) return ok(doc, ms[0], 'raw_prefix_unique', q);
  }
  return { status: 'unlocatable', reason: 'DB 원문 앞부분이 문서에서 유일하지 않거나 없음 (' + tried.map(t => t.matches).join('/') + '곳)', tried };
}

for (const b of data.businesses) {
  for (const mt of b.mentions) { const d = open(mt.doc); mt.locate = d.err ? { status: 'unrendered', reason: d.err } : locateAnswer(d, mt, b.search_name); }
  for (const s of b.segments) { const d = open(s.doc); s.locate = d.err ? { status: 'unrendered', reason: d.err } : locateSegment(d, s); }
}
for (const [id, d] of Object.entries(docs)) data.docs[id].rendered = !d.err && T(() => d.pageCount()) > 0;
data.locate_summary = {
  docs: { total: Object.keys(data.docs).length, rendered: Object.values(data.docs).filter(d => d.rendered).length },
  mentions: count(data.businesses.flatMap(b => b.mentions)), segments: count(data.businesses.flatMap(b => b.segments)),
};
function count(xs) { const o = { total: xs.length }; for (const x of xs) o[x.locate.status] = (o[x.locate.status] || 0) + 1; return o; }
fs.writeFileSync(outPath, JSON.stringify(data, null, 1) + '\n');
console.log(JSON.stringify(data.locate_summary));
