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
// 공백·가운뎃점 차이 무시: search_rules.projection(linker_v1이 재사용하는 원 함수)의 정규식을 원본 파일에서 그대로 읽는다(새 규칙 없음).
import crypto from 'node:crypto';
const projSrc = fs.readFileSync(R.projection_source);
if (crypto.createHash('sha256').update(projSrc).digest('hex') !== R.projection_source_sha256) throw Error('search_rules.py sha256 불일치');
const projClass = /def projection\(s\):return re\.sub\(r'(\[[^\]]+\])',''/.exec(projSrc.toString('utf8'))[1];
const projChar = new RegExp('^' + projClass + '$', 'u');
const projection = t => [...t].filter(c => !projChar.test(c)).join('').toLowerCase(); // Python: re.sub(...).casefold()
for (const [name, py] of Object.entries(data.projection_check)) if (projection(name) !== py) throw Error(`projection 이식 불일치: ${name} → ${projection(name)} / Python ${py}`);
// 문단(표 칸 문단 포함) 글자를 쪽 배치 run에서 다시 모아 projection 위치를 원래 글자 위치로 되돌린다. 중첩 표는 제외.
const paraIndex = new Map();
function paragraphs(doc) {
  if (paraIndex.has(doc)) return paraIndex.get(doc);
  const P = new Map();
  for (let pg = 0; pg < doc.pageCount(); pg++) for (const r of (J(T(() => doc.getPageTextLayout(pg))) || {}).runs || []) {
    if (r.cellPath && r.cellPath.length > 1) continue;
    const cell = r.cellPath ? { parentPara: r.parentParaIdx, ctrlIdx: r.controlIdx, cellIdx: r.cellIdx, cellPara: r.cellParaIdx } : null;
    const key = cell ? `${r.secIdx}|c|${cell.parentPara}|${cell.ctrlIdx}|${cell.cellIdx}|${cell.cellPara}` : `${r.secIdx}|p|${r.paraIdx}`;
    const e = P.get(key) || { sec: r.secIdx, para: cell ? cell.parentPara : r.paraIdx, cellContext: cell, chars: [] };
    [...r.text].forEach((c, i) => { e.chars[r.charStart + i] = c; }); P.set(key, e);
  }
  paraIndex.set(doc, P); return P;
}
function projSearch(doc, name) {
  const want = projection(name), out = []; if (!want) return out;
  for (const e of paragraphs(doc).values()) {
    const map = [], proj = [];
    e.chars.forEach((c, i) => { if (c === undefined || projChar.test(c)) return; for (const x of c.toLowerCase()) { proj.push(x); map.push(i); } });
    const text = proj.join('');
    for (let k = text.indexOf(want); k >= 0; k = text.indexOf(want, k + 1)) {
      const st = map[k], en = map[k + want.length - 1] + 1;
      out.push({ sec: e.sec, para: e.para, cellContext: e.cellContext, charOffset: st, length: en - st, projection: true });
    }
  }
  return out;
}
const cand = ms => ms.slice(0, R.max_candidates).map(m => ({ sec: m.sec, para: m.para, cellContext: m.cellContext || null, charOffset: m.charOffset, length: m.length }));

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
    if (labelled.length > 1) return { status: 'unlocatable', reason: `'사업명' 칸에 ${labelled.length}곳`, tried, candidates: cand(labelled) };
    if (ms.length === 1) return ok(doc, ms[0], 'global_unique', q);
  }
  if (tried.every(x => !x.matches)) {  // 표기 그대로는 0곳: 공백·가운뎃점 차이 무시(projection)로 다시 찾는다
    const ms = projSearch(doc, mention.original), labelled = ms.filter(mt => { const l = leftLabel(doc, mt); return l != null && labels.some(r => r.test(l)); });
    tried.push({ query: 'projection(' + mention.original + ')', matches: ms.length, labelled: labelled.length });
    if (labelled.length === 1) return ok(doc, labelled[0], 'label_unique_projection', mention.original);
    if (labelled.length === 0 && ms.length === 1) return ok(doc, ms[0], 'global_unique_projection', mention.original);
    if (ms.length) return { status: 'unlocatable', reason: `공백·가운뎃점 무시로 ${ms.length}곳(사업명 칸 ${labelled.length}곳) — 특정 불가`, tried, candidates: cand(labelled.length ? labelled : ms) };
  }
  const allMs = tried.reduce((acc, x) => acc.length ? acc : search(doc, x.query), []);
  const t = tried.map(x => `"${x.query}" ${x.matches}곳`).join(', ');
  return { status: 'unlocatable', reason: tried.every(x => !x.matches) ? '원문에서 표기를 찾지 못함 (' + t + ')' : '여러 곳에 있고 사업명 칸으로 특정되지 않음 (' + t + ')', tried, candidates: cand(allMs) };
}
// B: 예산서 구획. 세부사업=파일 제목 유일, 내역사업=DB 원문 앞부분이 문서에서 유일.
function locateSegment(doc, s) {
  if (s.레벨명 === '세부사업') {
    const ms = search(doc, s.title);
    return ms.length === 1 ? ok(doc, ms[0], 'title_unique', s.title) : { status: 'unlocatable', reason: `파일 제목 "${s.title}" ${ms.length}곳` };
  }
  const raws = s.content.map(c => c.원문).filter(Boolean);
  if (!raws.length) {  // DB 원문이 없으면 구획 사업명을 공백·가운뎃점 차이 무시로 찾는다. 유일할 때만 확정.
    const ms = projSearch(doc, s.사업명);
    if (ms.length === 1) return ok(doc, ms[0], 'name_unique_projection', s.사업명);
    return { status: 'unlocatable', reason: ms.length ? `DB 원문 없음 · 사업명이 ${ms.length}곳에 있음 — 특정 불가` : 'DB 원문 없음 · 사업명도 원문에서 찾지 못함', candidates: cand(ms) };
  }
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
