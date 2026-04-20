# Nexus-Sprint Stage 5 — P7 Severity-Routed Fix Loop Patch

**Target file (local, external skill):** `~/.claude/skills/nexus-sprint/SKILL.md`

The Nexus-Sprint skill ships as part of gstack and is **not** installed by this
repo's `install.sh` — its canonical source evolves independently. This patch
adds a `P7`-style severity-routed fix loop (inspired by `manager-orchestrator`)
to Stage 5 (TEST). Apply manually, and re-apply if gstack updates overwrite it.

## Find this block

```markdown
## Stage 5: TEST

1. OMC verification:
   - Run test suite via `verifier` agent
   - Check build, lint, type errors

2. Browser QA (auto-triggered if FRONTEND detected):
   - Call `Skill(skill: "qa")` with the staging/dev URL
   - Browser tests: smoke, happy path, edge cases, regression

3. Fix-verify loop (bounded):
   - If tests fail → route to `executor` or `build-fixer`
   - Max 3 fix attempts per issue
   - After 3 failures → escalate to user

---
```

## Replace with

```markdown
## Stage 5: TEST

1. OMC verification:
   - Run test suite via `verifier` agent
   - Check build, lint, type errors

2. Browser QA (auto-triggered if FRONTEND detected):
   - Call `Skill(skill: "qa")` with the staging/dev URL
   - Browser tests: smoke, happy path, edge cases, regression

3. **P7 severity-routed fix loop** (bounded, max 3 cycles):

   After QA/verification produces findings, do NOT hand off to a generic fixer.
   Parse the finding set, route each item to the specialist owning that domain,
   then re-verify.

   ```
   cycle = 0
   while cycle < 3:
     findings = parse_findings(qa_output)   # list of {category, severity, file, message}
     blockers = [f for f in findings if f.severity in ("CRITICAL","HIGH")]
     if not blockers: break

     # Route each blocker to the right specialist (parallel where independent)
     for f in blockers:
       agent = route(f)   # see table below
       Agent(subagent_type=agent, prompt=describe(f))

     # Re-verify
     run verifier + qa again
     cycle += 1

   if cycle == 3 and blockers_still_exist:
     escalate to user with finding summary
   ```

   **Severity → mandatory action:**
   - `CRITICAL` — block SHIP stage, loop until resolved or escalated
   - `HIGH`     — block SHIP stage, loop until resolved
   - `MEDIUM`   — loop once, then ship with tracked TODO
   - `LOW`      — log only, ship unblocked

   **Category → specialist routing table:**
   - `UI | FRONTEND | DESIGN | A11Y` → `nexus-designer` (or `volt-nextjs-developer` for Next.js code)
   - `API | BACKEND | PERFORMANCE` → `volt-performance-engineer`
   - `DB | SCHEMA | MIGRATION` → `nexus-architect`
   - `SECURITY | AUTH | INJECTION` → `volt-security-auditor`
   - `TYPE | TSC | LINT` → `volt-typescript-pro`
   - `TEST | COVERAGE | FLAKY` → `nexus-qa-tester`
   - `BUG | LOGIC | CRASH` → `nexus-debugger`
   - default → `nexus-debugger`

   **Parallelization rule:** if two blockers touch disjoint file scopes
   (e.g., `src/components/**` vs `src/api/**`), dispatch the routed agents in
   a single message with multiple Agent tool calls. If they overlap, run
   sequentially in the order CRITICAL → HIGH.

   **Emit a cycle log** to `.omc/plans/test-cycles.json` with: cycle number,
   finding count by severity, specialists invoked, elapsed time. This is the
   input to REFLECT and to comad-evolve's 5-axis filter.

---
```
