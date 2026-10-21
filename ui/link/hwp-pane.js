// HWP 원본 패널 하나. rhwp 초기화·SVG 렌더·글자 run 하이라이트는 ui/conflict/rhwp-viewer.js(uncertain_review_v1 출처)의 방식을 따른다.
// 같은 화면에 A(결과서)·B(예산서) 두 개를 띄우므로 전역 DOM id 대신 컨테이너 안에서만 동작한다.
import init, { HwpDocument } from '/rhwp/rhwp.js';
import { pageOfMatch } from '/hwp_locate.js';

const J = s => { try { return JSON.parse(s); } catch { return null; } };
let ready = null;
const docs = new Map(); // doc id → Promise<HwpDocument>
function engine() {
  return ready ??= (globalThis.measureTextWidth = (font, text) => { const c = document.createElement('canvas').getContext('2d'); c.font = font; return c.measureText(text).width; },
    init({ module_or_path: '/rhwp/rhwp_bg.wasm' }));
}
export function loadDoc(id) {
  if (!docs.has(id)) docs.set(id, (async () => {
    await engine();
    const res = await fetch('/api/doc?id=' + encodeURIComponent(id));
    if (!res.ok) throw Error((J(await res.text()) || {}).error || 'HTTP ' + res.status);
    return new HwpDocument(new Uint8Array(await res.arrayBuffer()));
  })());
  return docs.get(id);
}

export class HwpPane {
  constructor(host) {
    this.host = host; this.doc = null; this.page = 0; this.mark = null; this.url = null; this.seq = 0;
    host.innerHTML = '<div class="pbar"><button type="button" data-a="prev" aria-label="이전 쪽">◀</button><span class="pg">-</span><button type="button" data-a="next" aria-label="다음 쪽">▶</button><span class="zoom"><button type="button" data-a="out" aria-label="축소">−</button><span class="zl">100%</span><button type="button" data-a="in" aria-label="확대">+</button><button type="button" data-a="fit">폭 맞춤</button></span></div><div class="pview"><div class="ppage"></div></div>';
    host.querySelector('[data-a=prev]').onclick = () => { this.page--; this.render(); };
    host.querySelector('[data-a=next]').onclick = () => { this.page++; this.render(); };
    // 확대: 1 = 칸 폭에 맞춤. 확대 상태는 문서를 바꿔도 유지(검수자가 고른 읽기 크기).
    this.zoom = 1;
    const setZoom = z => { this.zoom = Math.min(4, Math.max(0.5, z)); this.applyZoom(); };
    host.querySelector('[data-a=in]').onclick = () => setZoom(this.zoom * 1.25);
    host.querySelector('[data-a=out]').onclick = () => setZoom(this.zoom / 1.25);
    host.querySelector('[data-a=fit]').onclick = () => setZoom(1);
  }
  // located: {page, match} 이면 그 쪽으로 가서 강조. 아니면 1쪽을 보여 주고 강조하지 않는다.
  async show(docId, located) {
    const n = ++this.seq, pg = this.host.querySelector('.ppage');
    pg.replaceChildren(Object.assign(document.createElement('p'), { className: 'muted', textContent: '원본 여는 중…' }));
    try {
      const doc = await loadDoc(docId); if (n !== this.seq) return;
      this.doc = doc; this.mark = located && located.match ? located.match : null; this.page = 0;
      if (this.mark) { const p = pageOfMatch(doc, this.mark); if (p == null) { this.mark = null; } else this.page = p; } // 브라우저 글꼴 기준으로 쪽을 다시 찾는다
      this.render(); return { rendered: true, page: this.page, highlighted: !!this.mark, context: this.context || '' };
    } catch (e) { if (n === this.seq) pg.replaceChildren(Object.assign(document.createElement('p'), { className: 'bad', textContent: '원본 표시 실패: ' + e.message })); return { rendered: false, error: e.message }; }
  }
  applyZoom() {
    const pg = this.host.querySelector('.ppage'); pg.style.width = this.zoom === 1 ? '' : (this.zoom * 100) + '%';
    this.host.querySelector('.zl').textContent = Math.round(this.zoom * 100) + '%';
    // 강조 위치로 문서 보기 영역 안에서만 스크롤한다(칸 머리글·판정 영역은 움직이지 않음).
    const view = this.host.querySelector('.pview'), first = pg.querySelector('.hl');
    if (first) requestAnimationFrame(() => { const v = view.getBoundingClientRect(), r = first.getBoundingClientRect();
      view.scrollTop += r.top - v.top - (v.height - r.height) / 2; view.scrollLeft += r.left - v.left - (v.width - r.width) / 2; });
  }
  render() {
    const doc = this.doc; if (!doc) return;
    const count = doc.pageCount(); this.page = Math.min(Math.max(this.page, 0), count - 1);
    this.host.querySelector('.pg').textContent = (this.page + 1) + ' / ' + count + '쪽';
    this.host.querySelector('[data-a=prev]').disabled = this.page <= 0; this.host.querySelector('[data-a=next]').disabled = this.page >= count - 1;
    const holder = this.host.querySelector('.ppage'); holder.replaceChildren();
    if (this.url) URL.revokeObjectURL(this.url);
    this.url = URL.createObjectURL(new Blob([doc.renderPageSvg(this.page)], { type: 'image/svg+xml' }));
    const img = document.createElement('img'); img.src = this.url; img.alt = 'HWP 원본 ' + (this.page + 1) + '쪽'; img.draggable = false; holder.append(img);
    const info = J(doc.getPageInfo(this.page)) || {}, m = this.mark;
    if (!m || !info.width || !info.height) return;
    const cell = m.cellContext; this.context = '';
    for (const run of (J(doc.getPageTextLayout(this.page)) || {}).runs || []) {
      if (run.secIdx !== m.sec) continue;
      if (cell ? !(run.parentParaIdx === cell.parentPara && run.controlIdx === cell.ctrlIdx && run.cellIdx === cell.cellIdx && run.cellParaIdx === cell.cellPara) : !(run.paraIdx === m.para && !run.cellPath)) continue;
      const s = Math.max(0, m.charOffset - run.charStart), e = Math.min(run.text.length, m.charOffset + m.length - run.charStart);
      if (s >= e || !Array.isArray(run.charX) || run.charX[e] == null) continue;
      this.context += run.text.slice(s, e);
      const x0 = run.x + run.charX[s], x1 = run.x + run.charX[e], el = document.createElement('span'); el.className = 'hl';
      Object.assign(el.style, { left: 100 * x0 / info.width + '%', top: 100 * run.y / info.height + '%', width: 100 * Math.max(x1 - x0, 4) / info.width + '%', height: 100 * run.h / info.height + '%' });
      holder.append(el);
    }
    this.applyZoom();
  }
}
