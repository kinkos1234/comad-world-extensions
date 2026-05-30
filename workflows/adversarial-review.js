export const meta = {
  name: 'adversarial-review',
  description: 'Adversarial review panel — N skeptics each try to BREAK the current diff through a distinct lens (correctness / security / edge), majority-vote a verdict, and write .second-opinion.md. R2 default mechanism for adversarial-by-default verification.',
  whenToUse: 'Before claiming a substantial code change is done/ready. Pairs with adversarial-review-gate and qa-evidence checks.second_opinion.',
  phases: [
    { title: 'Attack', detail: 'N skeptics each try to break the diff via a distinct lens' },
    { title: 'Synthesize', detail: 'aggregate findings → verdict → write .second-opinion.md' },
  ],
}

// args: { repo?: string, target?: string, panel?: number }
const repo = (args && args.repo) || '.'
const target = (args && args.target) || 'the uncommitted git diff (run: git diff HEAD)'
const PANEL = (args && args.panel) || 3

const LENSES = [
  { key: 'correctness', brief: 'logic errors, off-by-one, wrong assumptions, unhandled null/undefined, race conditions, broken control flow, incorrect error handling' },
  { key: 'security',    brief: 'injection (SQL/NoSQL/cmd), auth/authz gaps, secret leakage, unsafe deserialization, SSRF, path traversal, missing input validation' },
  { key: 'edge',        brief: 'boundary conditions, empty/huge inputs, concurrency, failure & rollback paths, resource leaks, idempotency, partial-failure states' },
]

const FINDING_SCHEMA = {
  type: 'object',
  required: ['lens', 'blocking', 'findings', 'summary'],
  properties: {
    lens: { type: 'string' },
    blocking: { type: 'boolean', description: 'true if a REAL defect that should block merge was found' },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        required: ['severity', 'title', 'where', 'why'],
        properties: {
          severity: { type: 'string', enum: ['blocker', 'major', 'minor', 'nit'] },
          title: { type: 'string' },
          where: { type: 'string', description: 'file:line' },
          why: { type: 'string', description: 'concrete failure path' },
        },
      },
    },
    summary: { type: 'string' },
  },
}

phase('Attack')
const assignments = Array.from({ length: PANEL }, (_, i) => LENSES[i % LENSES.length])
const reviews = (await parallel(assignments.map((lens, i) => () =>
  agent(
    `You are an adversarial reviewer. Your ONLY goal is to BREAK the code change in repo "${repo}" — review ${target}.\n` +
    `Lens: ${lens.key}. Hunt specifically for: ${lens.brief}.\n` +
    `Read the ACTUAL change (run git diff, open the changed files). Cite file:line and a real failure path for every finding. ` +
    `Do NOT praise; do NOT restate what the code does. If you genuinely cannot break it on this lens, return blocking=false with an empty findings list and say what you checked. ` +
    `Be skeptical by default, but never invent issues that aren't real.`,
    { label: `attack:${lens.key}#${i + 1}`, phase: 'Attack', schema: FINDING_SCHEMA, agentType: 'Explore' },
  ),
))).filter(Boolean)

phase('Synthesize')
const blockingVotes = reviews.filter((r) => r.blocking).length
const allFindings = reviews.flatMap((r) => r.findings || [])
const blockers = allFindings.filter((f) => f.severity === 'blocker')
const majors = allFindings.filter((f) => f.severity === 'major')

let verdict = 'APPROVED'
if (blockers.length) verdict = 'BLOCKS'
else if (blockingVotes * 2 >= reviews.length || majors.length) verdict = 'REQUEST_CHANGES'

const lines = []
lines.push('---')
lines.push('schema_version: 1')
lines.push(`reviewer: adversarial-review (panel of ${reviews.length})`)
lines.push(`topic: ${target}`)
lines.push(`verdict: ${verdict}`)
lines.push('---')
lines.push('')
lines.push(`# Adversarial Review — verdict: ${verdict}`)
lines.push('')
lines.push(`Panel of ${reviews.length}; ${blockingVotes} voted blocking. Blockers: ${blockers.length}, majors: ${majors.length}.`)
lines.push('')
for (const r of reviews) {
  lines.push(`## ${r.lens} ${r.blocking ? '🔴' : '🟢'}`)
  lines.push(r.summary || '')
  for (const f of r.findings || []) {
    lines.push(`- **[${f.severity}] ${f.title}** (${f.where}) — ${f.why}`)
  }
  lines.push('')
}
const markdown = lines.join('\n')

// Workflow scripts have no filesystem access — delegate the write to a scribe agent.
const scribe = await agent(
  `Use the Write tool to create the file "${repo}/.second-opinion.md" with EXACTLY this content, then reply "written":\n\n${markdown}`,
  { label: 'scribe:.second-opinion.md', phase: 'Synthesize' },
)

return { verdict, panel: reviews.length, blockingVotes, blockers: blockers.length, majors: majors.length, findings: allFindings, markdown, scribe }
