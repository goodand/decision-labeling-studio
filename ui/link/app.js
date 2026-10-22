// 사업명 ↔ 예산서 구획 연결 검수 화면. 유사·중복 라벨/판정 문구는 데이터에 없고 화면에도 표시하지 않는다.
import { HwpPane } from '/hwp-pane.js';

const $ = id => document.getElementById(id);
const el = (tag, props = {}, ...kids) => { const e = Object.assign(document.createElement(tag), props); e.append(...kids.flat().filter(k => k != null)); return e; };
const [data, votes0] = await Promise.all([fetch('/api/dataset').then(r => r.json()), fetch('/api/votes').then(r => r.json())]);
const votes = votes0 || {};
// 사업 전체 판정은 사람이 입력하지 않는다: 구획 판정에서 서버가 설정 규칙(aggregate_rules)으로 계산한 표시용 값(저장 안 함)
let derived = await fetch('/api/derived').then(r => r.json());
const refreshDerived = async () => { derived = await fetch('/api/derived').then(r => r.json()); };
// 판정 단위 = 탭. 같은 이름 세부·내역 병합(segments_run_007)이면 여러 구획이 한 탭. 탭 판정 상태(이어받기·충돌)는 서버 계산값.
const tabsOf = b => b.tabs || b.segments.map(s => ({ id: s.id, members: [s.id] }));
const tabOfSeg = (b, sid) => tabsOf(b).find(t => t.members.includes(sid));
const tabState = (b, tid) => ((derived[b.id] || {}).tabs || {})[tid] || { status: 'none', members: {} };
const segDone = b => tabsOf(b).filter(t => tabState(b, t.id).choice).length;
const complete = b => tabsOf(b).length > 0 && segDone(b) === tabsOf(b).length;
const paneA = new HwpPane($('a-pane')), paneB = new HwpPane($('b-pane'));
for (const side of ['a', 'b']) $(side + '-open').before($(side + '-pane').querySelector('.psearch')); // 기존 화면처럼 '원본 열기' 왼쪽에 원문 찾기
for (const side of ['a', 'b']) $(side + '-open-st').after($(side + '-pane').querySelector('.pbar')); // 쪽 이동·확대도 같은 줄로(헤더 높이 줄이기)
const ui = { b: null, mention: 0, seg: 0 };
const LOC_RULE = { label_unique: "'사업명' 칸에서 유일", global_unique: '문서 전체에서 유일', title_unique: '파일 제목이 유일', raw_prefix_unique: 'DB 원문 앞부분이 유일',
  label_unique_projection: "공백·가운뎃점 무시로 '사업명' 칸에서 유일", global_unique_projection: '공백·가운뎃점 무시로 문서 전체에서 유일', name_unique_projection: 'DB 원문 없음 · 구획 사업명이 공백·가운뎃점 무시로 유일' };

const biz = () => data.businesses.find(b => b.id === ui.b);
const okCount = xs => xs.filter(x => x.locate.status === 'ok').length;

function renderList() {
  const done = data.businesses.filter(complete).length;
  $('progress').textContent = `사업 ${done} / ${data.businesses.length} 판정`;
  const q = $('query').value.trim().toLowerCase(), f = $('filter').value;
  const shown = data.businesses.filter(b => {
    const hay = [b.id, b.search_name, ...b.mentions.flatMap(m => [m.original, m.row_id]), ...b.segments.flatMap(s => [s.사업명, String(s.회계연도), s.부처])].join(' ').toLowerCase();
    if (q && !q.split(/\s+/).every(t => hay.includes(t))) return false;
    if (f === 'todo') return !complete(b); if (f === 'done') return complete(b);
    if (f === 'unloc') return [...b.mentions, ...b.segments].some(x => x.locate.status !== 'ok');
    return true;
  });
  $('items').replaceChildren(...(shown.length ? [] : [el('p', { className: 'none', textContent: '조건에 맞는 사업 없음' })]), ...shown.map(b => el('button', { type: 'button', className: b.id === ui.b ? 'on' : '', onclick: () => open(b.id) },
    `${b.id} ${b.search_name}`,
    el('small', { textContent: `표기 ${b.mentions.length} · 구획 ${b.segments.length} · 위치 A ${okCount(b.mentions)}/${b.mentions.length} B ${okCount(b.segments)}/${b.segments.length} · 판정 ${segDone(b)}/${tabsOf(b).length}탭${derived[b.id] && derived[b.id].result ? ' → ' + derived[b.id].result : ''}` }))));
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
  renderBTabs();
  const body = s.content.filter(c => c.목적 || c.내용);
  const tb = tabOfSeg(b, s.id);
  const meta = [el('div', {}, el('b', { textContent: `[${s.회계연도}] ${s.부처} · ${s.레벨명} · ` }), s.사업명),
    s.via_former_name ? el('div', { className: 'merged-note', textContent: '옛 이름 표기로 연결된 구획(' + ((s.사업명.match(/[(（](舊[^)）]*)[)）]/) || [])[1] || '舊 명칭') + ') — 결과서 표기와 예산서 현재 이름이 다름' }) : null,
    tb.members.length > 1 ? el('div', { className: 'merged-note', title: '내부 번호 ' + tb.members.map(id => b.segments.find(x => x.id === id).merged_구조_ids.join(',')).join(' / '),
      textContent: `합친 구획: 같은 이름 세부·내역 병합${tb.scope_same ? ' · 범위 같음' : ''}${tb.admin_siblings.length ? ' (나머지 내역 = ' + tb.admin_siblings.join(', ') + ' 등 운영경비)' : ''}` }) : null,
    el('div', { className: 'opt' }, s.레벨명 === '세부사업' ? '예산서 파일의 세부사업(최상위 사업)' : '소속 세부사업: ' + (s.세부사업명 || '-')),
    el('div', { className: 'muted opt', textContent: d.name }),
    body.length ? el('details', {}, el('summary', { textContent: '목적·내용 (DB)' }), body.map(c => el('pre', { textContent: [c.목적 && '목적: ' + c.목적, c.내용 && '내용: ' + c.내용].filter(Boolean).join('\n') })))
      : el('div', { className: 'muted opt', textContent: s.레벨명 === '세부사업' ? '목적·내용 없음(DB). 세부사업은 같은 파일의 내역사업 구획에 본문이 있을 수 있음.' : '목적·내용 없음(DB). 이 구획의 본문은 원본에서 직접 확인.' })];
  $('b-open').title = `${d.name}
${s.레벨명 === '세부사업' ? '세부사업(최상위)' : '소속 세부사업: ' + (s.세부사업명 || '-')}`; // 배치 2에서 뺀 줄은 버튼 툴팁으로
  $('b-meta').replaceChildren(...meta.filter(Boolean), el('div', { textContent: '위치 확인 중…', className: 'muted' }));
  resetOpen('b');
  const shown = await paneB.show(s.doc, s.locate.status === 'ok' ? s.locate : null);
  $('b-meta').replaceChildren(...meta.filter(Boolean), shown && shown.rendered === false ? el('div', { className: 'loc bad', textContent: '원본 표시 불가 — ' + shown.error }) : locLine(s.locate, shown, paneB));
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
    votes[key] = out; await refreshDerived(); msg.className = 'saved'; msg.textContent = `저장됨: ${out.choice} · ${out.saved_at}`; renderList(); if (sid) showBTabsOnly(); renderJudge(); // 계산된 사업 전체 결과를 바로 갱신
  } });
  return el('fieldset', {}, el('legend', { textContent: title }), radios, note, el('div', {}, save), msg);
}
function renderBTabs() {
  const b = biz(), cur = tabOfSeg(b, b.segments[ui.seg].id);
  const tabBtns = tabsOf(b).map(t => { const segs = t.members.map(id => b.segments.find(x => x.id === id)), x = segs[0], st = tabState(b, t.id);
    return el('button', { type: 'button', className: 'tab' + (t === cur ? ' on' : '') + (segs.some(y => y.locate.status === 'ok') ? '' : ' bad'),
      title: `${x.사업명}${t.members.length > 1 ? '\n같은 이름 세부·내역을 한 구획으로 합침' : ''}\n(내부 번호 ${segs.flatMap(y => y.merged_구조_ids).join(', ')})`,
      textContent: `${x.회계연도} ${t.members.length > 1 ? '세부·내역' : x.레벨명}${segs.some(y => y.via_former_name) ? ' (옛 이름)' : ''}${st.status === 'conflict' ? ' ⚠' : st.choice ? ' ✓' : ''}`,
      onclick: () => { ui.seg = b.segments.indexOf(x); showB(); renderJudge(); } }); });
  // 합친 탭 안에서 원본 위치를 세부/내역 중 골라 본다(판정은 탭 하나)
  const sub = cur.members.length > 1 ? cur.members.map(id => { const y = b.segments.find(z => z.id === id), i = b.segments.indexOf(y);
    return el('button', { type: 'button', className: 'tab sub' + (i === ui.seg ? ' on' : ''), title: y.레벨명 + ' 위치로 원본 이동', textContent: y.레벨명 + ' 위치', onclick: () => { ui.seg = i; showB(); } }); }) : [];
  $('b-tabs').replaceChildren(...[...tabBtns, ...sub, tabsOf(b).length > 1 ? el('span', { className: 'muted', title: '탭(칩)을 누르면 원본이 바뀐다', textContent: '← 눌러서 구획 전환' }) : null].filter(Boolean));
}
function showBTabsOnly() { renderBTabs(); }
function _oldShowBTabsOnly() { const b = biz(); document.querySelectorAll('#b-tabs .tab').forEach((t, i) => { t.textContent = `${b.segments[i].회계연도} ${b.segments[i].레벨명}${votes[b.id + '/' + b.segments[i].id] ? ' ✓' : ''}`; }); }

function derivedBox(b) {
  const d = derived[b.id] || {}, R = (data.aggregate_rules || { rules: [] }).rules.find(r => r.id === d.rule);
  const text = d.result ? `${d.result} — 규칙 ${d.rule}: ${R ? R.when : ''}${d.detail && d.detail.판단불가_구획 ? ' (판단불가 구획 ' + d.detail.판단불가_구획.length + '개)' : ''}`
    : d.rule === 'incomplete' ? `미완료 — 판정 안 한 구획 ${d.detail.미판정_구획.length}개`
    : d.rule === 'undefined' ? `계산 불가 — 규칙에 없는 조합(${d.detail.판정_조합.join('+')}). 규칙은 설정 파일에서 정한다` : '계산 전';
  return el('div', { className: 'derived' }, el('b', { textContent: '사업 전체 (구획 판정에서 자동 계산, 입력 안 함): ' }), text,
    el('div', { className: 'muted', textContent: `규칙 ${d.rules_version || '-'} · 저장되지 않는 표시용 값` }));
}
function renderJudge() {
  const b = biz(), s = b.segments[ui.seg], t = s && tabOfSeg(b, s.id), st = t ? tabState(b, t.id) : null;
  $('judge').replaceChildren(...[el('h2', { textContent: b.id + ' ' + b.search_name }), el('div', { className: 'q', textContent: data.question }),
    s ? choiceSet(b.id + '/' + t.id, `[${s.회계연도} ${t.members.length > 1 ? '세부·내역' : s.레벨명}] ${s.사업명} — 결과서의 사업과 같은 사업인가?`) : null,
    st && st.status === 'inherited' ? el('p', { className: 'muted', textContent: '합친 구획의 이전 판정을 이어받음: ' + Object.entries(st.members).map(([k, v]) => k + ' ' + v).join(', ') }) : null,
    st && (st.status === 'conflict' || st.status === 'resolved') ? el('p', { className: st.status === 'conflict' ? 'err' : 'muted', textContent: (st.status === 'conflict' ? '판정 충돌 — 합치기 전 구획 판정이 다름(지우지 않음): ' : '이전 충돌을 새 판정으로 정리함. 이전 기록: ') + Object.entries(st.members).map(([k, v]) => k + ' ' + v).join(', ') + (st.status === 'conflict' ? '. 위에서 다시 판정해 저장하면 정리된다.' : '') }) : null,
    el('p', { className: 'muted', textContent: `모든 탭(구획)을 판정해야 사업이 완료된다. 지금 ${segDone(b)}/${tabsOf(b).length}탭 판정. 다른 구획은 B의 탭을 눌러 바꾼다.` }),
    derivedBox(b),
    votes[b.id] ? el('p', { className: 'muted', textContent: `이전 방식 기록(사람이 직접 입력한 사업 전체 판정, 보존만 함): ${votes[b.id].choice} · ${votes[b.id].saved_at}` }) : null,
    el('p', { className: 'muted', textContent: '판정은 연결 결과 파일과 별도의 votes 파일에만 저장된다.' })].filter(Boolean)); // 빈 줄(null)이 'null' 글자로 보이지 않게
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
setLayout(new URLSearchParams(location.search).get('layout') === '1' ? 1 : 2); // 2026-10-22 사용자: 둘 다 통과, 가독성으로 배치 2 기본
$('layout').onclick = () => setLayout(document.body.classList.contains('layout-1') ? 2 : 1);
for (const side of ['a', 'b']) { $(side + '-open').onclick = () => openSource(side, 'file'); $(side + '-dir').onclick = () => openSource(side, 'directory'); }

function open(id) { ui.b = id; ui.mention = 0; ui.seg = 0; history.replaceState(null, '', '#' + id); renderList(); renderJudge(); showA(); showB(); }
addEventListener('hashchange', () => { const id = location.hash.slice(1); if (id !== ui.b && data.businesses.some(b => b.id === id)) open(id); });
open(data.businesses.some(b => b.id === location.hash.slice(1)) ? location.hash.slice(1) : data.businesses[0].id);
