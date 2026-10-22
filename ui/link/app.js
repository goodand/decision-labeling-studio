// 사업명 ↔ 예산서 구획 연결 검수 화면. 유사·중복 라벨/판정 문구는 데이터에 없고 화면에도 표시하지 않는다.
import { HwpPane } from '/hwp-pane.js';

const $ = id => document.getElementById(id);
const el = (tag, props = {}, ...kids) => { const e = Object.assign(document.createElement(tag), props); e.append(...kids.flat().filter(k => k != null)); return e; };
const [data, votes0] = await Promise.all([fetch('/api/dataset').then(r => r.json()), fetch('/api/votes').then(r => r.json())]);
const votes = votes0 || {};
const paneA = new HwpPane($('a-pane')), paneB = new HwpPane($('b-pane'));
for (const side of ['a', 'b']) $(side + '-open').before($(side + '-pane').querySelector('.psearch')); // 기존 화면처럼 '원본 열기' 왼쪽에 원문 찾기
for (const side of ['a', 'b']) $(side + '-open-st').after($(side + '-pane').querySelector('.pbar')); // 쪽 이동·확대도 같은 줄로(헤더 높이 줄이기)
const ui = { b: null, mention: 0, seg: 0 };
const LOC_RULE = { label_unique: "'사업명' 칸에서 유일", global_unique: '문서 전체에서 유일', title_unique: '파일 제목이 유일', raw_prefix_unique: 'DB 원문 앞부분이 유일',
  label_unique_projection: "공백·가운뎃점 무시로 '사업명' 칸에서 유일", global_unique_projection: '공백·가운뎃점 무시로 문서 전체에서 유일', name_unique_projection: 'DB 원문 없음 · 구획 사업명이 공백·가운뎃점 무시로 유일' };

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

function locLine(L, shown, pane) {
  if (L.status === 'unrendered') return el('div', { className: 'loc bad', textContent: '원본 표시 불가 — ' + L.reason });
  if (L.status !== 'ok') return el('div', { className: 'locwrap' }, el('div', { className: 'loc bad', textContent: '위치 확인 불가 — ' + L.reason }),
    L.candidates && L.candidates.length && pane ? el('button', { type: 'button', className: 'cand', title: '확정 위치가 아니다. 파란 표시로 출현 위치를 차례로 보여 준다(↑↓).', textContent: `출현 ${L.candidates.length}곳 넘겨 보기 (확정 아님)`, onclick: () => pane.showCandidates(L.candidates, '출현 ' + L.candidates.length + '곳') }) : null);
  const norm = t => (t || '').replace(/\s+/g, '');
  if (shown && shown.highlighted && norm(shown.context) !== norm(L.query)) return el('div', { className: 'loc bad', textContent: `위치 확인 불가 — 강조 위치 글자("${shown.context}")가 찾은 표기와 다름` });
  if (shown && !shown.highlighted) return el('div', { className: 'loc bad', textContent: '위치 확인 불가 — 화면 글꼴 기준으로 위치를 다시 찾지 못함' });
  return el('div', { className: 'locwrap' }, el('div', { className: 'loc', textContent: `위치 확인: ${shown ? shown.page + 1 : '?'}쪽 · ${LOC_RULE[L.rule] || L.rule}` }),
    el('div', { className: 'ctx', title: '렌더링이 겹쳐 보여도 이 글자가 강조 위치의 실제 원문이다', textContent: '강조 위치 원문: ' + (shown && shown.context ? shown.context : '(없음)') }));
}

async function showA() {
  const b = biz(), m = b.mentions[ui.mention], d = data.docs[m.doc];
  $('a-tabs').replaceChildren(...b.mentions.map((x, i) => el('button', { type: 'button', className: 'tab' + (i === ui.mention ? ' on' : '') + (x.locate.status === 'ok' ? '' : ' bad'),
    title: '눌러서 이 행의 결과서/의견서 원본으로 전환', textContent: `${x.row_id} · ${x.role}`, onclick: () => { ui.mention = i; showA(); } })),
    b.mentions.length > 1 ? el('span', { className: 'muted', title: '탭(칩)을 누르면 원본이 바뀐다', textContent: `← 이 사업을 쓰는 행 ${b.mentions.length}개, 눌러서 원본 전환` }) : null);
  const meta = [el('div', {}, el('b', { textContent: '원래 표기: ' }), m.original),
    el('div', { className: m.scope || m.original !== b.search_name ? '' : 'opt' }, '정리된 이름: ', b.search_name, m.scope ? ' · 범위: ' + m.scope : ''), // 배치 2: 원래 표기와 같으면 뺀다
    m.administrative_metadata.length ? el('div', {}, '행정 표기: ', m.administrative_metadata.map(s => s.trim()).join(' | ')) : null,
    el('div', { className: 'muted opt', textContent: `${d.name} (${m.source_folder || ''} ${m.source_doc_year || ''})` })];
  $('a-open').title = `${d.name} (${m.source_folder || ''} ${m.source_doc_year || ''})`; // 배치 2에서 뺀 파일명은 버튼 툴팁으로
  $('a-meta').replaceChildren(...meta.filter(Boolean), el('div', { textContent: '위치 확인 중…', className: 'muted' }));
  resetOpen('a');
  const shown = await paneA.show(m.doc, m.locate.status === 'ok' ? m.locate : null);
  $('a-meta').replaceChildren(...meta.filter(Boolean), shown && shown.rendered === false ? el('div', { className: 'loc bad', textContent: '원본 표시 불가 — ' + shown.error }) : locLine(m.locate, shown, paneA));
}

async function showB() {
  const b = biz();
  if (!b.segments.length) { $('b-meta').textContent = '연결된 예산서 구획 없음'; return; }
  const s = b.segments[ui.seg], d = data.docs[s.doc];
  $('b-tabs').replaceChildren(...b.segments.map((x, i) => el('button', { type: 'button', className: 'tab' + (i === ui.seg ? ' on' : '') + (x.locate.status === 'ok' ? '' : ' bad'),
    title: x.사업명, textContent: `${x.회계연도} ${x.레벨명}${votes[b.id + '/' + x.id] ? ' ✓' : ''}`, onclick: () => { ui.seg = i; showB(); renderJudge(); } })),
    b.segments.length > 1 ? el('span', { className: 'muted', title: '탭(칩)을 누르면 원본이 바뀐다', textContent: '← 눌러서 구획 전환' }) : null);
  const body = s.content.filter(c => c.목적 || c.내용);
  const meta = [el('div', {}, el('b', { textContent: `[${s.회계연도}] ${s.부처} · ${s.레벨명} · ` }), s.사업명),
    el('div', { className: 'opt' }, '상위 세부사업: ', s.세부사업명 || '-', ' · 구조_id ', s.merged_구조_ids.join(', '), s.merged_구조_ids.length > 1 ? ` (같은 파일·이름·레벨 노드 ${s.merged_구조_ids.length}개를 한 탭으로 합침)` : ''),
    el('div', { className: 'muted opt', textContent: d.name }),
    body.length ? el('details', {}, el('summary', { textContent: '목적·내용 (DB)' }), body.map(c => el('pre', { textContent: [c.목적 && '목적: ' + c.목적, c.내용 && '내용: ' + c.내용].filter(Boolean).join('\n') })))
      : el('div', { className: 'muted opt', textContent: s.레벨명 === '세부사업' ? '목적·내용 없음(DB). 세부사업은 같은 파일의 내역사업 구획에 본문이 있을 수 있음.' : '목적·내용 없음(DB). 이 구획의 본문은 원본에서 직접 확인.' })];
  $('b-open').title = `${d.name}
상위 세부사업: ${s.세부사업명 || '-'} · 구조_id ${s.구조_id}`; // 배치 2에서 뺀 줄은 버튼 툴팁으로
  $('b-meta').replaceChildren(...meta, el('div', { textContent: '위치 확인 중…', className: 'muted' }));
  resetOpen('b');
  const shown = await paneB.show(s.doc, s.locate.status === 'ok' ? s.locate : null);
  $('b-meta').replaceChildren(...meta, shown && shown.rendered === false ? el('div', { className: 'loc bad', textContent: '원본 표시 불가 — ' + shown.error }) : locLine(s.locate, shown, paneB));
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
    choiceSet(b.id, '사업 전체 판정 — 결과서의 이 사업이 오른쪽 구획 전체와 같은 사업인가'),
    s ? choiceSet(b.id + '/' + s.id, `선택한 탭의 구획만 따로 판정 (선택): [${s.회계연도} ${s.레벨명}] ${s.사업명}`) : null,
    s ? el('p', { className: 'muted', textContent: '구획마다 결론이 다를 때만 쓴다. 예: 연도별로 일부 구획만 같은 사업이면 사업 전체는 부분일치, 구획별로 일치/불일치. 다른 구획은 B의 탭을 눌러 바꾼 뒤 판정한다.' }) : null,
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
// 칸 머리 배치 A/B 비교(?layout=1|2). 데이터·판정은 같고 칸 머리 배치만 다르다.
const setLayout = n => { document.body.classList.remove('layout-1', 'layout-2'); document.body.classList.add('layout-' + n); $('layout').textContent = '배치 ' + n;
  const u = new URL(location.href); u.searchParams.set('layout', n); history.replaceState(null, '', u); };
setLayout(new URLSearchParams(location.search).get('layout') === '2' ? 2 : 1);
$('layout').onclick = () => setLayout(document.body.classList.contains('layout-1') ? 2 : 1);
for (const side of ['a', 'b']) { $(side + '-open').onclick = () => openSource(side, 'file'); $(side + '-dir').onclick = () => openSource(side, 'directory'); }

function open(id) { ui.b = id; ui.mention = 0; ui.seg = 0; history.replaceState(null, '', '#' + id); renderList(); renderJudge(); showA(); showB(); }
addEventListener('hashchange', () => { const id = location.hash.slice(1); if (id !== ui.b && data.businesses.some(b => b.id === id)) open(id); });
open(data.businesses.some(b => b.id === location.hash.slice(1)) ? location.hash.slice(1) : data.businesses[0].id);
