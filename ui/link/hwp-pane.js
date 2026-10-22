// HWP 원본 패널 하나. rhwp 초기화·SVG 렌더·글자 run 하이라이트·문서 내 검색(Ctrl+F, Enter/Shift+Enter)은
// ui/conflict/rhwp-viewer.js(uncertain_review_v1 출처)의 방식을 따른다. A(결과서)·B(예산서) 두 개를 띄우므로 컨테이너 안에서만 동작한다.
import init, { HwpDocument } from '/rhwp/rhwp.js';
import { pageOfMatch } from '/hwp_locate.js';

const J = s => { try { return JSON.parse(s); } catch { return null; } };
let ready = null, activePane = null, selectingText = false;
// 원본에서 복사(rhwp-viewer.js L230-240 그대로, 단 두 패널의 텍스트 레이어 중 선택이 들어 있는 쪽을 찾는다)
document.addEventListener('pointerup', () => { selectingText = false });
document.addEventListener('pointercancel', () => { selectingText = false });
document.addEventListener('copy', event => {
  const selection = window.getSelection();
  if (!selection || selection.isCollapsed || !selection.rangeCount) return;
  const layer = [...document.querySelectorAll('.native-text-layer')].find(l => l.contains(selection.anchorNode));
  if (!layer || !layer.contains(selection.anchorNode) || !layer.contains(selection.focusNode)) return;
  const fragment = selection.getRangeAt(0).cloneContents();
  if (event.clipboardData) { event.clipboardData.setData('text/plain', fragment.textContent); event.preventDefault() }
});
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
// Ctrl+F: 마지막으로 만진 패널의 검색칸으로(없으면 첫 패널).
document.addEventListener('keydown', e => {
  if (!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== 'f' || !activePane) return;
  e.preventDefault(); const q = activePane.sbox.querySelector('input'); q.focus(); q.select();
}, true);

export class HwpPane {
  constructor(host) {
    this.host = host; this.doc = null; this.page = 0; this.mark = null; this.url = null; this.seq = 0; this.zoom = 1;
    this.hits = []; this.hitIndex = -1; this.query = ''; this.context = '';
    activePane ??= this;
    host.addEventListener('pointerdown', () => { activePane = this; });
    host.addEventListener('focusin', () => { activePane = this; });
    host.innerHTML = '<div class="pbar"><button type="button" data-a="prev" aria-label="이전 쪽">◀</button><span class="pg">-</span><button type="button" data-a="next" aria-label="다음 쪽">▶</button>'
      + '<span class="zoom"><button type="button" data-a="out" aria-label="축소">−</button><span class="zl">100%</span><button type="button" data-a="in" aria-label="확대">+</button><button type="button" data-a="fit">폭 맞춤</button></span></div>'
      + '<div class="psearch"><input type="search" placeholder="원문 찾기 (Ctrl+F)" aria-label="원문 찾기" autocomplete="off"><button type="button" data-a="sprev" aria-label="이전 결과">↑</button><button type="button" data-a="snext" aria-label="다음 결과">↓</button><span class="scount" role="status"></span></div>'
      + '<div class="pview"><div class="ppage"></div></div>';
    this.bar = host.querySelector('.pbar'); // 쪽 이동·확대 막대도 화면이 옮길 수 있어 참조로 들고 있는다
    this.sbox = host.querySelector('.psearch'); // 화면이 이 상자를 다른 곳(원본 열기 왼쪽)으로 옮길 수 있어 참조로 들고 있는다
    this.sbox.addEventListener('focusin', () => { activePane = this; });
    const q = this.sbox.querySelector('input'); let timer = null;
    host.querySelector('[data-a=prev]').onclick = () => { this.page--; this.render(); };
    host.querySelector('[data-a=next]').onclick = () => { this.page++; this.render(); };
    const setZoom = z => { this.zoom = Math.min(4, Math.max(0.5, z)); this.applyZoom(); };
    host.querySelector('[data-a=in]').onclick = () => setZoom(this.zoom * 1.25);
    host.querySelector('[data-a=out]').onclick = () => setZoom(this.zoom / 1.25);
    host.querySelector('[data-a=fit]').onclick = () => setZoom(1);
    q.oninput = () => { clearTimeout(timer); timer = setTimeout(() => this.search(q.value), 180); };
    q.onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); clearTimeout(timer); if (q.value.trim() !== this.query) this.search(q.value); else this.moveHit(e.shiftKey ? -1 : 1); } else if (e.key === 'Escape') q.blur(); };
    this.sbox.querySelector('[data-a=sprev]').onclick = () => this.moveHit(-1);
    this.sbox.querySelector('[data-a=snext]').onclick = () => this.moveHit(1);
    this.updateCount();
    // 휠: 쪽 안에서는 스크롤, 위/아래 끝에서 굴리면 앞/뒤 쪽(rhwp-viewer.js L212-229 그대로, 대상만 이 패널)
    const view = host.querySelector('.pview'); let wheelBusy = false;
    view.addEventListener('wheel', event => {
      if (!this.doc) return;
      event.stopPropagation();
      if (wheelBusy) { event.preventDefault(); return; }
      if (selectingText) return;
      const viewport = event.currentTarget;
      const atBottom = viewport.scrollTop + viewport.clientHeight >= viewport.scrollHeight - 3;
      const atTop = viewport.scrollTop <= 3;
      const forward = event.deltaY > 0 && atBottom && this.page < this.doc.pageCount() - 1;
      const backward = event.deltaY < 0 && atTop && this.page > 0;
      if (!forward && !backward) return;
      event.preventDefault(); wheelBusy = true; this.page += forward ? 1 : -1; this.render('wheel');
      const image = host.querySelector('.ppage img');
      const position = () => { viewport.scrollTop = forward ? 0 : viewport.scrollHeight - viewport.clientHeight };
      image.addEventListener('load', position, { once: true });
      if (image.complete) position();
      setTimeout(() => { wheelBusy = false }, 450);
    }, { passive: false });
    host.querySelector('.ppage').addEventListener('pointerdown', event => { selectingText = !!event.target.closest('.native-text-layer') });
  }
  // Author: chatgpt_gpt6 (rhwp-viewer.js L15-42). Copy native text, never OCR or normalized text. doc/page/textObserver만 패널 소속으로 바꿈.
  renderSelectableText(holder, info) {
    if (!info.width || !info.height) return;
    const runs = (J(this.doc.getPageTextLayout(this.page))?.runs || []).filter(r => r.text);
    const layer = document.createElement('div'); layer.className = 'native-text-layer';
    Object.assign(layer.style, { position: 'absolute', left: '0', top: '0', width: `${info.width}px`, height: `${info.height}px`, transformOrigin: 'top left', pointerEvents: 'none', zIndex: '4', userSelect: 'text' });
    const canvas = document.createElement('canvas'), ctx = canvas.getContext('2d');
    let previous = null;
    for (const run of runs) {
      if (![run.x, run.y, run.w, run.h].every(Number.isFinite)) continue;
      if (previous) {
        const sameLine = Math.abs(run.y - previous.y) < Math.min(run.h, previous.h) * 0.4;
        const sameCell = JSON.stringify(run.cellPath) === JSON.stringify(previous.cellPath) && run.parentParaIdx === previous.parentParaIdx;
        const separator = document.createElement('span');
        separator.textContent = sameLine && sameCell ? '' : '\n';
        Object.assign(separator.style, { position: 'absolute', whiteSpace: 'pre', color: 'transparent', fontSize: '1px' }); layer.append(separator);
      }
      const span = document.createElement('span'); span.className = 'native-text-run'; span.textContent = run.text;
      const size = run.fontSize || run.h;
      Object.assign(span.style, { position: 'absolute', left: `${run.x}px`, top: `${run.y}px`, height: `${run.h}px`, fontFamily: run.fontFamily || 'serif', fontSize: `${size}px`, fontWeight: run.bold ? 'bold' : 'normal', fontStyle: run.italic ? 'italic' : 'normal', lineHeight: `${run.h}px`, whiteSpace: 'pre', color: 'transparent', cursor: 'text', pointerEvents: 'auto', userSelect: 'text', transformOrigin: 'left top' });
      ctx.font = `${run.italic ? 'italic ' : ''}${run.bold ? 'bold ' : ''}${size}px "${run.fontFamily || 'serif'}"`;
      const measured = ctx.measureText(run.text).width;
      if (measured > 0 && run.w > 0) span.style.transform = `scaleX(${run.w / measured})`;
      layer.append(span); previous = run;
    }
    holder.append(layer);
    const resize = () => { layer.style.transform = `scale(${holder.clientWidth / info.width})` };
    this.textObserver = new ResizeObserver(resize); this.textObserver.observe(holder); resize();
  }
  // located: {match} 이면 그 위치의 쪽으로 가서 강조. 아니면 1쪽을 보여 주고 강조하지 않는다.
  async show(docId, located) {
    const n = ++this.seq, pg = this.host.querySelector('.ppage');
    pg.replaceChildren(Object.assign(document.createElement('p'), { className: 'muted', textContent: '원본 여는 중…' }));
    this.hits = []; this.hitIndex = -1; this.query = ''; this.context = ''; this.sbox.querySelector('input').value = ''; this.updateCount();
    try {
      const doc = await loadDoc(docId); if (n !== this.seq) return;
      this.doc = doc; this.mark = located && located.match ? located.match : null; this.page = 0;
      if (this.mark) { const p = pageOfMatch(doc, this.mark); if (p == null) this.mark = null; else this.page = p; } // 브라우저 글꼴 기준으로 쪽을 다시 찾는다
      this.render('show'); return { rendered: true, page: this.page, highlighted: !!this.mark, context: this.context };
    } catch (e) { if (n === this.seq) pg.replaceChildren(Object.assign(document.createElement('p'), { className: 'bad', textContent: '원본 표시 실패: ' + e.message })); return { rendered: false, error: e.message }; }
  }
  search(text) {
    this.query = text.trim(); this.hits = []; this.hitIndex = -1;
    if (this.doc && this.query) {
      let ms = []; try { ms = J(this.doc.searchAllText(this.query, false, true)) || []; } catch (e) { this.sbox.querySelector('.scount').textContent = '검색 오류: ' + e.message; return; }
      for (const m of ms) { const p = pageOfMatch(this.doc, m); if (p != null) this.hits.push({ page: p, match: m }); }
      if (this.hits.length) { this.hitIndex = 0; this.page = this.hits[0].page; }
    }
    this.updateCount(); this.render(this.hits.length ? 'search' : null);
  }
  moveHit(step) {
    if (!this.hits.length) { this.search(this.sbox.querySelector('input').value); return; }
    this.hitIndex = (this.hitIndex + step + this.hits.length) % this.hits.length; this.page = this.hits[this.hitIndex].page;
    this.updateCount(); this.render('search');
  }
  // 확정되지 않은 출현 위치들을 검색 결과처럼(파란 표시) 넘겨 보게 한다. 확정 하이라이트(주황)와 구분된다.
  showCandidates(list, label) {
    if (!this.doc) return;
    this.hits = list.map(m => ({ page: pageOfMatch(this.doc, m), match: m })).filter(h => h.page != null);
    this.hitIndex = this.hits.length ? 0 : -1; this.query = label || '출현 위치';
    this.sbox.querySelector('input').value = ''; this.sbox.querySelector('input').placeholder = (label || '출현 위치') + ' 넘겨 보기';
    if (this.hits.length) this.page = this.hits[0].page;
    this.updateCount(); this.render('search');
  }
  updateCount() {
    const n = this.hits.length;
    this.sbox.querySelector('.scount').textContent = n ? `${this.hitIndex + 1} / ${n}건` : this.query ? '결과 없음' : '';
    this.sbox.querySelector('[data-a=sprev]').disabled = !n; this.sbox.querySelector('[data-a=snext]').disabled = !n;
  }
  applyZoom(focus) {
    const pg = this.host.querySelector('.ppage'); pg.style.width = this.zoom === 1 ? '' : (this.zoom * 100) + '%';
    this.bar.querySelector('.zl').textContent = Math.round(this.zoom * 100) + '%';
    // 강조 위치(검색 중이면 현재 검색 결과)로 문서 보기 영역 안에서만 스크롤한다.
    const view = this.host.querySelector('.pview'), first = (focus === 'search' && pg.querySelector('.sh.cur')) || pg.querySelector('.hl');
    if (first) requestAnimationFrame(() => { const v = view.getBoundingClientRect(), r = first.getBoundingClientRect();
      view.scrollTop += r.top - v.top - (v.height - r.height) / 2; view.scrollLeft += r.left - v.left - (v.width - r.width) / 2; });
  }
  // 한 위치(match)를 이 쪽의 글자 run 좌표로 강조하고, 강조한 실제 글자를 돌려준다.
  draw(holder, info, runs, m, cls) {
    const cell = m.cellContext; let text = '';
    for (const run of runs) {
      if (run.secIdx !== m.sec) continue;
      if (cell ? !(run.parentParaIdx === cell.parentPara && run.controlIdx === cell.ctrlIdx && run.cellIdx === cell.cellIdx && run.cellParaIdx === cell.cellPara) : !(run.paraIdx === m.para && !run.cellPath)) continue;
      const s = Math.max(0, m.charOffset - run.charStart), e = Math.min(run.text.length, m.charOffset + m.length - run.charStart);
      if (s >= e || !Array.isArray(run.charX) || run.charX[e] == null) continue;
      text += run.text.slice(s, e);
      const x0 = run.x + run.charX[s], x1 = run.x + run.charX[e], el = document.createElement('span'); el.className = cls;
      Object.assign(el.style, { left: 100 * x0 / info.width + '%', top: 100 * run.y / info.height + '%', width: 100 * Math.max(x1 - x0, 4) / info.width + '%', height: 100 * run.h / info.height + '%' });
      holder.append(el);
    }
    return text;
  }
  render(focus) {
    const doc = this.doc; if (!doc) return;
    const count = doc.pageCount(); this.page = Math.min(Math.max(this.page, 0), count - 1);
    this.bar.querySelector('.pg').textContent = (this.page + 1) + ' / ' + count + '쪽';
    this.bar.querySelector('[data-a=prev]').disabled = this.page <= 0; this.bar.querySelector('[data-a=next]').disabled = this.page >= count - 1;
    const holder = this.host.querySelector('.ppage'); holder.replaceChildren(); this.textObserver?.disconnect();
    if (this.url) URL.revokeObjectURL(this.url);
    this.url = URL.createObjectURL(new Blob([doc.renderPageSvg(this.page)], { type: 'image/svg+xml' }));
    const img = document.createElement('img'); img.src = this.url; img.alt = 'HWP 원본 ' + (this.page + 1) + '쪽'; img.draggable = false; holder.append(img);
    const info = J(doc.getPageInfo(this.page)) || {};
    if (!info.width || !info.height) return;
    const runs = (J(doc.getPageTextLayout(this.page)) || {}).runs || [];
    if (this.mark) { const t = this.draw(holder, info, runs, this.mark, 'hl'); if (focus === 'show') this.context = t; }
    this.hits.forEach((h, i) => { if (h.page === this.page) this.draw(holder, info, runs, h.match, 'sh' + (i === this.hitIndex ? ' cur' : '')); });
    this.renderSelectableText(holder, info); // 글자 드래그 → Ctrl+C 복사
    this.applyZoom(focus);
  }
}
