export const meta = {
  name: 'term-validation-loop',
  description: '불안정 용어(T09, T15) 후보를 haiku 2회 독립 설명 + 규칙 판정으로 검증하고, 실패 시 웹 검색으로 후보 재작성 (최대 3라운드)',
  phases: [
    { title: 'Explain', detail: '후보마다 haiku 2명 독립 설명', model: 'haiku' },
    { title: 'Rewrite', detail: '전부 실패한 용어는 웹 검색으로 새 후보' },
  ],
}

const RULES = {
  T09: {
    intended: '각 명령이 원본 쓰기·네트워크·프로세스 실행 같은 부수 효과를 하는지 선언한 표시',
    must: [['부수 효과', '부수효과', '부작용', 'side effect', 'side-effect'], ['선언', '표시', '표기', '나타', '명시']],
    must_not: ['시각 효과', '애니메이션', '특수 효과', '이펙트', 'feature flag', '기능 플래그', '켜고 끌'],
  },
  T15: {
    intended: '개발 흐름의 관문(검사)에서 실패했을 때 어느 개발 단계로 돌아가 다시 할지 정한 규칙 (롤백/체크포인트 복구가 아님)',
    must: [['실패', '문제', '오류', '반례', '통과하지', '만족하지', '충족하지'], ['이전 단계', '앞 단계', '돌아', '재수행', '다시', '되돌', '회귀']],
    must_not: ['롤백', '복원', '복구', '이전 상태', '실행 취소', 'undo', '되돌리기 기능', '체크포인트', '이전 시점'],
  },
}
let candidates = {
  T09: ['부수효과 선언', '부수효과 플래그'],
  T15: ['관문 실패 시 재작업 단계', '단계 회귀 규칙', '검사 실패 시 돌아갈 개발 단계'],
}

function judge(expl, rule) {
  const t = (expl || '').toLowerCase()
  const why = []
  for (const g of rule.must) if (!g.some(w => t.includes(w.toLowerCase()))) why.push('누락:' + g.slice(0, 3).join('|'))
  for (const w of rule.must_not) if (t.includes(w.toLowerCase())) why.push('오해:' + w)
  return { ok: why.length === 0, why }
}

const EXPLAIN = {
  type: 'object',
  properties: { explanation: { type: 'string' } },
  required: ['explanation'],
}
const CANDS = {
  type: 'object',
  properties: { candidates: { type: 'array', items: { type: 'string' } }, sources: { type: 'array', items: { type: 'string' } } },
  required: ['candidates'],
}

const explainPrompt = term => `아래 용어의 뜻을 한국어 1~2문장으로 설명하세요. 추가 맥락은 없습니다. 도구는 쓰지 말고, 이 용어를 처음 본 사람이 가장 자연스럽게 이해할 뜻으로 설명하세요. 모르면 추측해서라도 설명하세요.\n\n용어: ${term}`

const history = []
const winners = {}
for (let round = 1; round <= 3; round++) {
  const pending = Object.keys(RULES).filter(id => !winners[id])
  if (!pending.length) break
  log(`라운드 ${round}: ${pending.map(id => id + '=' + candidates[id].join(', ')).join(' / ')}`)
  const jobs = pending.flatMap(id => candidates[id].map(term => ({ id, term })))
  const results = await pipeline(jobs, job =>
    parallel([0, 1].map(k => () =>
      agent(explainPrompt(job.term), { label: `R${round} ${job.term} #${k + 1}`, phase: 'Explain', model: 'haiku', effort: 'low', schema: EXPLAIN })
    )).then(samples => {
      const judged = samples.map(s => ({ explanation: s ? s.explanation : null, ...(s ? judge(s.explanation, RULES[job.id]) : { ok: false, why: ['응답 없음'] }) }))
      return { round, ...job, samples: judged, pass: judged.every(j => j.ok) }
    })
  )
  for (const r of results.filter(Boolean)) history.push(r)
  for (const id of pending) {
    const win = results.filter(Boolean).find(r => r.id === id && r.pass)
    if (win) { winners[id] = win.term; log(`${id} 채택: ${win.term}`) }
  }
  const failed = pending.filter(id => !winners[id])
  if (!failed.length || round === 3) break
  phase('Rewrite')
  const rewrites = await parallel(failed.map(id => () => {
    const tried = history.filter(h => h.id === id).map(h => `- ${h.term}: ${h.samples.map(s => (s.explanation || '').slice(0, 80) + ' [' + s.why.join(',') + ']').join(' / ')}`).join('\n')
    return agent(`한국어 소프트웨어 용어 이름을 새로 제안하는 작업입니다. WebSearch로 업계 표준 용어(영문·한국어)를 찾아 근거로 쓰세요.\n\n의도한 뜻: ${RULES[id].intended}\n이 뜻이 맥락 없이도 바로 전달되는 짧은 이름(한국어, 필요하면 괄호 영문)을 3개 제안하세요. 아래 오해를 피해야 합니다: ${RULES[id].must_not.join(', ')}\n\n이미 실패한 이름과 잘못 이해된 설명:\n${tried}`,
      { label: `후보 재작성 ${id}`, phase: 'Rewrite', schema: CANDS })
  }))
  failed.forEach((id, i) => { if (rewrites[i] && rewrites[i].candidates.length) candidates[id] = rewrites[i].candidates.slice(0, 3) })
}

return { winners, unresolved: Object.keys(RULES).filter(id => !winners[id]), history }
