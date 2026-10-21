// 사업명 ↔ 예산서 구획 연결 검수 화면. 유사·중복 라벨/판정 문구는 데이터에 없고 화면에도 표시하지 않는다.
import { HwpPane } from '/hwp-pane.js';

const $ = id => document.getElementById(id);
const el = (tag, props = {}, ...kids) => { const e = Object.assign(document.createElement(tag), props); e.append(...kids.flat().filter(k => k != null)); return e; };
const [data, votes0] = await Promise.all([fetch('/api/dataset').then(r => r.json()), fetch('/api/votes').then(r => r.json())]);
const votes = votes0 || {};
const paneA = new HwpPane($('a-pane')), paneB = new HwpPane($('b-pane'));
const ui = { b: null, mention: 0, seg: 0 };
const LOC_RULE = { label_unique: "'사업명' 칸에서 유일", global_unique: '문서 전체에서 유일', title_unique: '파일 제목이 유일', raw_prefix_unique: 'DB 원문 앞부분이 유일' };

const biz = () => data.businesses.find(b => b.id === ui.b);
const okCount = xs => xs.filter(x => x.locate.status === 'ok').length;

function renderList() {
  const done = data.businesses.filter(b => votes[b.id]).length;
  $('progress').textContent = `사업 ${done} / ${data.businesses.length} 판정`;
  const q = $('query').value.trim().toLowerCase(), f = $('filter').value;
  const shown = data.businesses.filter(b => {
    const hay = [b.id, b.search_name, ...b.mentions.flatMap(m => [m.original, m.row_id]), ...b.segments.flatMap(s => [s.사업명, String(s.회계연도), s.부처])].join(' ').toLowerCase();
    if (q && !q.split(/\s+/).every(t => hay.includes(t))) return false;
    if (f === 'todo') return !votes[b.id]; if (f === 'done') return !!votes[b.id];
    if (f === 'unloc') return [...b.mentions, ...b.segments].some(x => x.locate.status !== 'ok');
    return true;
  });
  $('items').replaceChildren(...(shown.length ? [] : [el('p', { className: 'none', textContent: '조건에 맞는 사업 없음' })]), ...shown.map(b => el('button', { type: 'button', className: b.id === ui.b ? 'on' : '', onclick: () => open(b.id) },
    `${b.id} ${b.search_name}`,
    el('small', { textContent: `표기 ${b.mentions.length} · 구획 ${b.segments.length} · 위치 A ${okCount(b.mentions)}/${b.mentions.length} B ${okCount(b.segments)}/${b.segments.length}${votes[b.id] ? ' · 판정: ' + votes[b.id].choice : ''}` }))));
}

function locLine(L, shown) {
  if (L.status === 'unrendered') return el('div', { className: 'loc bad', textContent: '원본 표시 불가 — ' + L.reason });
  if (L.status !== 'ok') return el('div', { className: 'loc bad', textContent: '위치 확인 불가 — ' + L.reason });
  const norm = t => (t || '').replace(/\s+/g, '');
  if (shown && shown.highlighted && norm(shown.context) !== norm(L.query)) return el('div', { className: 'loc bad', textContent: `위치 확인 불가 — 강조 위치 글자("${shown.context}")가 찾은 표기와 다름` });
  if (shown && !shown.highlighted) return el('div', { className: 'loc bad', textContent: '위치 확인 불가 — 화면 글꼴 기준으로 위치를 다시 찾지 못함' });
  return el('div', {}, el('div', { className: 'loc', textContent: `위치 확인: ${shown ? shown.page + 1 : '?'}쪽 · ${LOC_RULE[L.rule] || L.rule}` }),
    el('div', { className: 'ctx', title: '렌더링이 겹쳐 보여도 이 글자가 강조 위치의 실제 원문이다', textContent: '강조 위치 원문: ' + (shown && shown.context ? shown.context : '(없음)') }));
}

async function showA() {
  const b = biz(), m = b.mentions[ui.mention], d = data.docs[m.doc];
  $('a-tabs').replaceChildren(...b.mentions.map((x, i) => el('button', { type: 'button', className: 'tab' + (i === ui.mention ? ' on' : '') + (x.locate.status === 'ok' ? '' : ' bad'),
    textContent: `${x.row_id} · ${x.role}`, onclick: () => { ui.mention = i; showA(); } })));
  const meta = [el('div', {}, el('b', { textContent: '원래 표기: ' }), m.original),
    el('div', {}, '정리된 이름: ', b.search_name, m.scope ? ' · 범위: ' + m.scope : ''),
    m.administrative_metadata.length ? el('div', {}, '행정 표기: ', m.administrative_metadata.map(s => s.trim()).join(' | ')) : null,
    el('div', { className: 'muted', textContent: `${d.name} (${m.source_folder || ''} ${m.source_doc_year || ''})` })];
  $('a-meta').replaceChildren(...meta.filter(Boolean), el('div', { textContent: '위치 확인 중…', className: 'muted' }));
  resetOpen('a');
  const shown = await paneA.show(m.doc, m.locate.status === 'ok' ? m.locate : null);
  $('a-meta').replaceChildren(...meta.filter(Boolean), shown && shown.rendered === false ? el('div', { className: 'loc bad', textContent: '원본 표시 불가 — ' + shown.error }) : locLine(m.locate, shown));
}

async function showB() {
  const b = biz();
  if (!b.segments.length) { $('b-meta').textContent = '연결된 예산서 구획 없음'; return; }
  const s = b.segments[ui.seg], d = data.docs[s.doc];
  $('b-tabs').replaceChildren(...b.segments.map((x, i) => el('button', { type: 'button', className: 'tab' + (i === ui.seg ? ' on' : '') + (x.locate.status === 'ok' ? '' : ' bad'),
    title: x.사업명, textContent: `${x.회계연도} ${x.레벨명}${votes[b.id + '/' + x.id] ? ' ✓' : ''}`, onclick: () => { ui.seg = i; showB(); renderJudge(); } })));
  const body = s.content.filter(c => c.목적 || c.내용);
  const meta = [el('div', {}, el('b', { textContent: `[${s.회계연도}] ${s.부처} · ${s.레벨명} · ` }), s.사업명),
    el('div', {}, '상위 세부사업: ', s.세부사업명 || '-', ' · 구조_id ', String(s.구조_id), s.dup_rows ? ` (연결 결과에 같은 구획 ${s.dup_rows + 1}번 나옴, 한 번만 표시)` : ''),
    el('div', { className: 'muted', textContent: d.name }),
    body.length ? el('details', {}, el('summary', { textContent: '목적·내용 (DB)' }), body.map(c => el('pre', { textContent: [c.목적 && '목적: ' + c.목적, c.내용 && '내용: ' + c.내용].filter(Boolean).join('\n') })))
      : el('div', { className: 'muted', textContent: '목적·내용 없음(DB). 세부사업은 같은 파일의 내역사업 구획에 본문이 있을 수 있음.' })];
  $('b-meta').replaceChildren(...meta, el('div', { textContent: '위치 확인 중…', className: 'muted' }));
  resetOpen('b');
  const shown = await paneB.show(s.doc, s.locate.status === 'ok' ? s.locate : null);
  $('b-meta').replaceChildren(...meta, shown && shown.rendered === false ? el('div', { className: 'loc bad', textContent: '원본 표시 불가 — ' + shown.error }) : locLine(s.locate, shown));
}

function choiceSet(key, title) {
  const v = votes[key] || {}, name = 'c-' + key;
  const note = el('textarea', { placeholder: '부분일치·판단불가는 어느 연도·범위·구획인지 적는다', value: v.note || '' });
  const msg = el('div', { className: v.choice ? 'saved' : '', textContent: v.choice ? `저장됨: ${v.choice} · ${v.saved_at}` : '' });
  const radios = Object.entries(data.choices).map(([val, label]) => el('label', { className: 'c' }, el('input', { type: 'radio', name, value: val, checked: v.choice === val }), ' ' + label));
  const save = el('button', { type: 'button', textContent: '저장', onclick: async () => {
    const choice = (document.querySelector(`input[name="${CSS.escape(name)}"]:checked`) || {}).value;
    if (!choice) { msg.className = 'err'; msg.textContent = '선택지를 고르세요'; return; }
    if (data.note_required_for.includes(choice) && !note.value.trim()) { msg.className = 'err'; msg.textContent = choice + '는 설명이 필요합니다'; note.focus(); return; }
    const [bid, sid] = key.split('/');
    const res = await fetch('/api/votes', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ business_id: bid, segment_id: sid || null, choice, note: note.value }) });
    const out = await res.json();
    if (!res.ok) { msg.className = 'err'; msg.textContent = '저장 실패: ' + out.error; return; }
    votes[key] = out; msg.className = 'saved'; msg.textContent = `저장됨: ${out.choice} · ${out.saved_at}`; renderList(); if (sid) showBTabsOnly();
  } });
  return el('fieldset', {}, el('legend', { textContent: title }), radios, note, el('div', {}, save), msg);
}
function showBTabsOnly() { const b = biz(); document.querySelectorAll('#b-tabs .tab').forEach((t, i) => { t.textContent = `${b.segments[i].회계연도} ${b.segments[i].레벨명}${votes[b.id + '/' + b.segments[i].id] ? ' ✓' : ''}`; }); }

function renderJudge() {
  const b = biz(), s = b.segments[ui.seg];
  $('judge').replaceChildren(el('h2', { textContent: b.id + ' ' + b.search_name }), el('div', { className: 'q', textContent: data.question }),
    choiceSet(b.id, '사업 전체 판정'),
    s ? choiceSet(b.id + '/' + s.id, `이 구획만 판정 (선택): ${s.회계연도} ${s.레벨명} ${s.사업명}`) : null,
    el('p', { className: 'muted', textContent: '판정은 연결 결과 파일과 별도의 votes 파일에만 저장된다.' }));
}

function resetOpen(side) { $(side + '-dir').hidden = true; $(side + '-open-st').textContent = ''; }
async function openSource(side, target) {
  const b = biz(), docId = side === 'a' ? b.mentions[ui.mention].doc : b.segments[ui.seg]?.doc, st = $(side + '-open-st');
  st.className = 'st'; st.textContent = '요청 중…';
  try {
    const res = await fetch('/api/open-source', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ doc: docId, target }) });
    const out = await res.json(); if (!res.ok) throw Error(out.error || '열기 실패');
    st.textContent = (target === 'file' ? '원본' : '폴더') + ' 열기 요청 보냄'; st.title = out.path;
  } catch (e) { st.className = 'st bad'; st.textContent = (target === 'file' ? '원본을 열 수 없음: ' : '폴더를 열 수 없음: ') + e.message; if (target === 'file') $(side + '-dir').hidden = false; }
}
$('query').oninput = renderList; $('filter').onchange = renderList;
$('toggle').onclick = () => document.body.classList.toggle('collapsed');
for (const side of ['a', 'b']) { $(side + '-open').onclick = () => openSource(side, 'file'); $(side + '-dir').onclick = () => openSource(side, 'directory'); }

function open(id) { ui.b = id; ui.mention = 0; ui.seg = 0; history.replaceState(null, '', '#' + id); renderList(); renderJudge(); showA(); showB(); }
addEventListener('hashchange', () => { const id = location.hash.slice(1); if (id !== ui.b && data.businesses.some(b => b.id === id)) open(id); });
open(data.businesses.some(b => b.id === location.hash.slice(1)) ? location.hash.slice(1) : data.businesses[0].id);
