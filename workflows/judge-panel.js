export const meta = {
  name: 'judge-panel',
  description: 'Speculative parallelism — generate N independent approaches to a wide-solution-space problem from DISTINCT strategies, score them with parallel judges, then synthesize from the winner while grafting the best ideas from the runners-up. For design / architecture / strategy / hard trade-off decisions where one-attempt-iterated would miss better framings. (R5)',
  whenToUse: 'When the solution space is broad and the first idea is unlikely to be the best — design, architecture, strategy, hard decisions. Contrast: adversarial-review reviews an EXISTING change; judge-panel GENERATES options.',
  phases: [
    { title: 'Generate', detail: 'N approaches, each committed to a distinct strategy lens' },
    { title: 'Judge', detail: 'parallel judges score every approach per criterion' },
    { title: 'Synthesize', detail: 'winner + grafted runner-up ideas → one recommendation' },
  ],
}

// args: { problem: string, strategies?: (string|{key,brief})[], panel?: number, criteria?: string[] }
const problem = (args && args.problem) || 'the problem described in the conversation context'
const PANEL = (args && args.panel) || 3
const criteria = (args && Array.isArray(args.criteria) && args.criteria.length)
  ? args.criteria
  : ['correctness / feasibility', 'simplicity', 'robustness', 'fit to existing context']

const DEFAULT_STRATEGIES = [
  { key: 'mvp-first',  brief: 'simplest thing that works — minimize scope and moving parts; ship-ability over completeness' },
  { key: 'risk-first', brief: 'minimize downside and failure modes — defensive, reversible; assume things go wrong' },
  { key: 'user-first', brief: 'best end-user / developer experience — optimize for whoever lives with this daily' },
  { key: 'long-game',  brief: 'best 2-year outcome — extensibility, maintainability, no lock-in, even at higher upfront cost' },
]
const strategies = (args && Array.isArray(args.strategies) && args.strategies.length)
  ? args.strategies.map((s, i) => (typeof s === 'string' ? { key: `strategy-${i + 1}`, brief: s } : s))
  : DEFAULT_STRATEGIES

const APPROACH_SCHEMA = {
  type: 'object',
  required: ['strategy', 'summary', 'plan', 'tradeoffs'],
  properties: {
    strategy: { type: 'string' },
    summary: { type: 'string', description: 'one-line thesis' },
    plan: { type: 'array', items: { type: 'string' }, description: 'concrete ordered steps' },
    tradeoffs: { type: 'string' },
    key_ideas: { type: 'array', items: { type: 'string' }, description: 'ideas worth stealing even if this approach loses' },
  },
}

const SCORE_SCHEMA = {
  type: 'object',
  required: ['scores', 'best_index', 'why'],
  properties: {
    scores: {
      type: 'array',
      items: {
        type: 'object',
        required: ['index', 'total'],
        properties: {
          index: { type: 'integer' },
          total: { type: 'number', description: '0-10 on this criterion' },
          notes: { type: 'string' },
        },
      },
    },
    best_index: { type: 'integer' },
    why: { type: 'string' },
  },
}

phase('Generate')
const chosen = Array.from({ length: PANEL }, (_, i) => strategies[i % strategies.length])
const approaches = (await parallel(chosen.map((s, i) => () =>
  agent(
    `Propose a COMPLETE approach to this problem:\n\n${problem}\n\n` +
    `Your strategy lens: ${s.key} — ${s.brief}.\n` +
    `Commit FULLY to this lens; do not hedge toward the other strategies. Read whatever context you need. ` +
    `Return a concrete ordered plan, the honest trade-offs, and the few ideas worth stealing even if this approach loses.`,
    { label: `approach:${s.key}#${i + 1}`, phase: 'Generate', schema: APPROACH_SCHEMA },
  ),
))).filter(Boolean)

phase('Judge')
const approachesText = approaches.map((a, i) =>
  `### Approach ${i} [${a.strategy}]\n${a.summary}\nPlan: ${(a.plan || []).join('; ')}\nTrade-offs: ${a.tradeoffs}`,
).join('\n\n')
const judges = (await parallel(criteria.map((c) => () =>
  agent(
    `Judge these ${approaches.length} approaches on ONE criterion: "${c}".\n\n${approachesText}\n\n` +
    `Score each approach 0-10 on THIS criterion only (use the approach index), pick the best index for this criterion, and explain. ` +
    `Be discriminating — do not tie everything.`,
    { label: `judge:${c}`, phase: 'Judge', schema: SCORE_SCHEMA },
  ),
))).filter(Boolean)

phase('Synthesize')
const totals = approaches.map(() => 0)
for (const j of judges) {
  for (const s of j.scores || []) {
    if (typeof s.index === 'number' && s.index >= 0 && s.index < totals.length) {
      totals[s.index] += (s.total || 0)
    }
  }
}
let winner = 0
for (let i = 1; i < totals.length; i++) {
  if (totals[i] > totals[winner]) winner = i
}

const graftLines = approaches
  .map((a, i) => (i === winner ? '' : `- [${a.strategy}] ${(a.key_ideas || []).join('; ')}`))
  .filter(Boolean)
  .join('\n')

const recommendation = await agent(
  `You are the synthesizer. By panel score the winner is Approach ${winner} [${approaches[winner] && approaches[winner].strategy}].\n\n` +
  `Winner detail:\n${JSON.stringify(approaches[winner], null, 2)}\n\n` +
  `Runner-up ideas worth grafting:\n${graftLines || '(none)'}\n\n` +
  `Produce ONE synthesized recommendation: take the winner as the base, graft any runner-up idea that STRICTLY improves it, ` +
  `and state the final ordered plan plus the single biggest risk to watch.`,
  { label: 'synthesize', phase: 'Synthesize' },
)

return { winner, strategy: approaches[winner] && approaches[winner].strategy, totals, approaches, judges, recommendation }
