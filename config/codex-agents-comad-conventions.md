<!-- COMAD-WORKER-CONVENTIONS-START -->

---

## comad-world Worker Conventions

You may be dispatched as a parallel worker by **comad-parallel** (Korean: 품앗이). When you are, Claude has already designed the signatures, requirements, and gates — your job is to **write the actual implementation code**, then satisfy the conventions below. These are not optional polish: comad-parallel runs automated gates after you finish, and a worker that ignores them gets flagged `missing`/`blocking` and sent back for rework.

### 1. Implementation fidelity (the core contract)
- Implement **to the provided signatures and requirements**. Do not change the public interface Claude gave you.
- **Never swap the specified library/framework** for an alternative, and never invent an API that doesn't exist — verify with `docs-researcher` if unsure.
- **No stubs, no `TODO`, no `throw new Error("not implemented")`** in the delivered path. If a requirement is genuinely ambiguous, implement the most reasonable interpretation and note it in your report — do not leave a hole.

### 2. Strong gates before you report done
- Your code must pass the task's gates — typically `tsc --noEmit` → build → test. Run them yourself before reporting success.
- Treat lint warnings as failures (`--max-warnings=0` philosophy). Clean output, not "it compiles."

### 3. QA evidence (comad-parallel `qa-gate` checks this)
- When the task involves verifiable behavior, write a `.qa-evidence.json` at the project root with `verdict: "PASS"` and the gate commands you actually ran filled in (build / typecheck / unit_tests with real pass/fail counts).
- Helper, if present: `python3 ~/.claude/skills/comad-qa-evidence/bin/init-qa-evidence.py --scope "<task>" --profile smoke` to seed it, then populate real results and set `verdict=PASS`. A missing or `PENDING` file fails the gate.

### 4. Commit convention (feeds comad's T6 self-evolve capture)
- When done, create a git commit prefixed `feat:` or `fix:` (e.g. `feat(auth): add JWT session middleware`). comad's Stop hook harvests these prefixes into the learning pipeline — an un-prefixed or absent commit is invisible to it.

### 5. Destructive-command prohibition (comad-parallel `destroy-check` greps your output)
- You run as a separate process, so Claude's pre-tool-use guard does **not** protect you. Never emit any of these — they hard-fail the job:
  `rm -rf /`, `rm -rf ~`, `rm -rf $HOME`, `git push --force`, `git reset --hard <ref>`, `git branch -D` on protected branches, `git clean -fd`, `DROP DATABASE/SCHEMA`, `TRUNCATE DATABASE`, `kubectl delete ns/node`, `docker system prune -a`, `mkfs.*`, fork bombs.
- Scope every destructive-ish action to the task's own working files. When in doubt, leave it for Claude to integrate.

> These conventions are the Codex-side mirror of comad-world's `CLAUDE.md`.
<!-- COMAD-WORKER-CONVENTIONS-END -->
