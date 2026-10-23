// node tests/link_layout.mjs <url> [width] [height] [png] — program_link 화면의 배치 회귀 검사(설치 없음: Edge 헤드리스 + DevTools 프로토콜).
// 검사: 기존 기능이 있는가, 칸 머리 버튼이 겹치거나 잘리지 않는가, A·B 원본 렌더링 영역의 위쪽·높이가 같은가, 칸 머리가 너무 길지 않은가.
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const [url, W = '1585', H = '900', png] = process.argv.slice(2);
const edge = process.env.EDGE_PATH || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const prof = fs.mkdtempSync(path.join(os.tmpdir(), 'link-layout-'));
const port = 9300 + Math.floor(Math.random() * 500);
const proc = spawn(edge, ['--headless=new', '--disable-gpu', '--hide-scrollbars', `--remote-debugging-port=${port}`, `--user-data-dir=${prof}`, 'about:blank'], { stdio: 'ignore' });
const sleep = t => new Promise(r => setTimeout(r, t));
let ws, id = 0; const pending = new Map();
const send = (method, params = {}) => new Promise((res, rej) => { const i = ++id; pending.set(i, { res, rej }); ws.send(JSON.stringify({ id: i, method, params })); });
const evalJs = async expr => { const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true }); if (r.exceptionDetails) throw Error(JSON.stringify(r.exceptionDetails).slice(0, 300)); return r.result.value; };
try {
  let target;
  for (let k = 0; k < 50 && !target; k++) { await sleep(200); try { target = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find(t => t.type === 'page'); } catch {} }
  ws = new WebSocket(target.webSocketDebuggerUrl); await new Promise(r => ws.onopen = r);
  ws.onmessage = m => { const d = JSON.parse(m.data); if (d.id && pending.has(d.id)) { const p = pending.get(d.id); pending.delete(d.id); d.error ? p.rej(Error(d.error.message)) : p.res(d.result); } };
  await send('Emulation.setDeviceMetricsOverride', { width: +W, height: +H, deviceScaleFactor: 1, mobile: false });
  await send('Page.enable'); await send('Runtime.enable');
  await send('Page.navigate', { url });
  for (let k = 0; k < 60; k++) { await sleep(500); if (await evalJs("!!document.querySelector('#a-pane .ppage img') && !!document.querySelector('#b-pane .ppage img') && !document.querySelector('.meta .muted:last-child')?.textContent.includes('확인 중')")) break; }
  await sleep(800);
  const m = await evalJs(`(() => {
    const R = e => e && e.getBoundingClientRect(), q = s => document.querySelector(s);
    const overlap = (a, b) => a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1;
    const out = { features: {}, panes: {} };
    for (const [k, s] of Object.entries({ list_toggle: '#toggle', list_search: '#query', list_filter: '#filter', a_search: '#a .psearch input', b_search: '#b .psearch input', a_open: '#a-open', b_open: '#b-open', a_page: '#a .pg', b_page: '#b .pg', a_zoom: '#a .zl', b_zoom: '#b .zl' }))
      out.features[k] = !!q(s) && R(q(s)).width > 0;
    for (const side of ['a', 'b']) {
      const sec = q('#' + side), view = q('#' + side + '-pane .pview');
      const ctrls = [...sec.querySelectorAll('button:not([hidden]), input, .pg, .zl, .scount')].filter(e => R(e).width > 0 && !e.closest('.pview') && (() => { const m = e.closest('.meta'); if (!m) return true; const a = R(e), b = R(m); return a.top >= b.top - 1 && a.bottom <= b.bottom + 1; })()); // 설명 영역 스크롤 밖으로 잘린 요소는 보이지 않으므로 겹침 대상 아님
      const pairs = []; for (let i = 0; i < ctrls.length; i++) for (let j = i + 1; j < ctrls.length; j++) if (!ctrls[i].contains(ctrls[j]) && !ctrls[j].contains(ctrls[i]) && overlap(R(ctrls[i]), R(ctrls[j]))) pairs.push((ctrls[i].textContent || ctrls[i].placeholder || ctrls[i].className).trim().slice(0, 12) + ' x ' + (ctrls[j].textContent || ctrls[j].placeholder || ctrls[j].className).trim().slice(0, 12));
      const clipped = ctrls.filter(e => e.scrollWidth > e.clientWidth + 1 && e.tagName === 'BUTTON').map(e => e.textContent.trim());
      out.panes[side] = { header_px: Math.round(R(view).top - R(sec).top), view_top: Math.round(R(view).top), view_h: Math.round(R(view).height), search_w: Math.round(R(sec.querySelector('.psearch input')).width), overlaps: pairs, clipped_buttons: clipped };
    }
    out.page_scroll_w = document.documentElement.scrollWidth; out.vw = innerWidth;
    // 검수 편의(Nielsen 점검 2026-10-22): 저장 후 다음, 범례, 선택지 한 줄, 목록의 판정 진행 표시
    const jb = [...document.querySelectorAll('#judge button')].map(b => b.textContent.trim());
    out.ux = { save_next: jb.includes('저장 후 다음'), legend: !!q('#legend'),
      choices_one_row: (() => { const t = [...document.querySelectorAll('#judge label.c')].map(l => Math.round(R(l).top)); return t.length > 0 && new Set(t).size === 1; })(),
      list_progress_first: (() => { const sm = q('#items button small'); return !!sm && /^판정/.test(sm.textContent.trim()); })(),
      shortcut_hint: !!q('#judge .keys'),
      choices_fit: (() => { const c = q('#judge .choices'); return !!c && R(c).right <= R(q('#judge')).right - 8 && c.scrollWidth <= c.clientWidth + 1; })() };
    return out; })()`);
  if (png) { const shot = await send('Page.captureScreenshot', { format: 'png' }); fs.writeFileSync(png, Buffer.from(shot.data, 'base64')); }
  const fails = [];
  for (const [k, v] of Object.entries(m.features)) if (!v) fails.push('기능 없음: ' + k);
  for (const s of ['a', 'b']) { const p = m.panes[s];
    if (p.overlaps.length) fails.push(`${s} 칸 컨트롤 겹침: ${p.overlaps.join(', ')}`);
    if (p.clipped_buttons.length) fails.push(`${s} 칸 버튼 글자 잘림: ${p.clipped_buttons.join(', ')}`);
    if (p.search_w < 120) fails.push(`${s} 칸 원문 찾기 입력칸이 좁음: ${p.search_w}px`);
    if (p.header_px > 230) fails.push(`${s} 칸 머리가 김: ${p.header_px}px`); }
  if (Math.abs(m.panes.a.view_top - m.panes.b.view_top) > 2) fails.push(`A·B 원본 위쪽 어긋남: ${m.panes.a.view_top} vs ${m.panes.b.view_top}`);
  if (Math.abs(m.panes.a.view_h - m.panes.b.view_h) > 2) fails.push(`A·B 원본 높이 다름: ${m.panes.a.view_h} vs ${m.panes.b.view_h}`);
  if (m.page_scroll_w > m.vw) fails.push('가로 스크롤 생김');
  for (const [k, v] of Object.entries(m.ux || {})) if (!v) fails.push('검수 편의 없음: ' + k);
  console.log(JSON.stringify(m, null, 1));
  console.log(fails.length ? 'FAIL\n- ' + fails.join('\n- ') : 'PASS');
  process.exitCode = fails.length ? 1 : 0;
} finally { try { ws && ws.close(); } catch {} proc.kill(); }
