// Translate the existing editor/view models at the FastAPI boundary.
const request = async (path, method = 'GET', data) => {
  const token = globalThis.sessionStorage?.getItem('cqa_api_token');
  const r = await fetch('/api' + path, {method, headers: {
    'Content-Type': 'application/json', ...(token ? {Authorization: 'Bearer ' + token} : {})
  }, body: data === undefined ? undefined : JSON.stringify(data)});
  let json;
  try { json = await r.json(); } catch { throw Error('Invalid server response'); }
  if (!r.ok) {
    const detail = json.detail ?? json.error;
    const error = Error(typeof detail === 'string' ? detail : detail?.message || JSON.stringify(detail) || `HTTP ${r.status}`);
    error.status = r.status;
    throw error;
  }
  return json;
};
const checklist = c => ({...c, criteria: c.criteria.map(x => ({...x,
  id: x.criterion_id, type: x.critical_rule ? 'critical' : x.answer_type,
  scale: x.allowed_scores || []
}))});
const checklistBody = c => ({name: c.name, rounding_decimals: c.rounding_decimals ?? 2,
  criteria: c.criteria.map(x => ({criterion_id: x.id, name: x.name,
    description: x.description, weight: x.weight, section: x.section,
    answer_type: x.type === 'scale' ? 'scale' : 'boolean',
    critical_rule: x.type === 'critical', allow_na: x.allow_na,
    min_score: x.type === 'scale' ? (x.scale.length ? Math.min(...x.scale) : x.min_score ?? 0) : 0,
    max_score: x.type === 'scale' ? (x.scale.length ? Math.max(...x.scale) : x.max_score ?? 1) : 1,
    allowed_scores: x.type === 'scale' && x.scale.length ? x.scale : null
  }))});
const evaluation = e => {
  if (e.status !== 'completed') throw Error(e.error || 'Оценка ещё не завершена.');
  const sections = {};
  for (const c of e.criteria) {
    const s = sections[c.section] ||= {weight: 0, points: 0};
    if (c.applicable) { s.weight += c.original_weight; s.points += c.final_score / c.max_score * c.original_weight; }
  }
  return {...e, reviewed: e.criteria.some(c => c.final_score !== c.original_score || c.applicable !== c.original_applicable),
    section_scores: Object.fromEntries(Object.entries(sections).map(([k,s]) => [k, s.weight ? s.points / s.weight * 100 : null])),
    criteria: e.criteria.map(c => ({...c, weight: c.original_weight, answer: c.answer === 'N/A' ? 'NA' : c.answer}))};
};
export const api = {
  list: async () => {
    const [rows, appeals] = await Promise.all([request('/conversations'), request('/appeals')]);
    return rows.map(r => ({...r, status: appeals.some(a => a.evaluation_id === r.evaluation_id && a.status === 'submitted') ? 'appealed' :
      appeals.some(a => a.evaluation_id === r.evaluation_id) ? 'reviewed' : r.status}));
  },
  history: id => request('/conversations/' + encodeURIComponent(id) + '/evaluations'),
  conversation: id => request('/conversations/' + encodeURIComponent(id)),
  evaluate: async id => evaluation(await request('/evaluate/' + encodeURIComponent(id), 'POST', {})),
  evaluation: async id => evaluation(await request('/evaluations/' + encodeURIComponent(id))),
  checklists: async () => {
    const rows = await request('/checklists');
    return {checklists: rows.map(checklist), active_id: rows.filter(c => c.is_active).at(-1)?.id};
  },
  saveChecklist: async (id, value) => checklist(await request('/checklists/' + id, 'PUT', checklistBody(value))),
  appeals: async () => (await request('/appeals')).map(a => ({...a, appeal_id: String(a.id),
    status: a.status === 'submitted' ? 'appealed' : 'reviewed',
    review: a.reviewer_decision ? {original_answer: a.original_score, reviewer_answer: a.reviewed_score, reason: a.review_reason} : null})),
  appeal: value => request('/appeals', 'POST', value),
  review: (id, value) => request('/appeals/' + id + '/review', 'POST', {
    decision: value.decision, reason: value.reason,
    ...(value.decision === 'changed' ? {new_score: value.new_score === 'NA' ? null : value.new_score === 'YES' ? 1 : value.new_score === 'NO' ? 0 : Number(value.new_score), applicable: value.new_score !== 'NA'} : {})
  }),
  import: value => request('/conversations/import', 'POST', value),
  importGroup: group_id => request('/datasets/import', 'POST', {group_id})
};
