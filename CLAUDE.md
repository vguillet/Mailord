<!-- mdse:start -->
## mdse Project model

This repository's engineering project is represented as a **Project model**: typed JSON
instances under `.mdse/`. Prefer reading the model over re-deriving context from source.
Use `mdse context .mdse` (or `--work-item <slug>`) for a lean initial view,
then open exact typed instances when an operation needs their full content.

**Before answering questions about this project:** read `.mdse/model/overview.mdse-overview`
and `.mdse/model/architecture.mdse-architecture`. For a specific work item, read
`.mdse/work-items/<slug>/workitem.mdse-workitem` for its `status`, then the requirements,
design, decisions and tasks underneath it as needed. Status fields are authoritative —
do not infer progress from file existence.

**Before writing or editing code for an existing work item:** read that work item's
`design.mdse-design` and the relevant `Task` instances — they carry the contracts,
conventions and constraints the implementation must respect.

**Load the model before proposing anything new.** The model persists and accumulates —
new work extends it rather than starting over. Check `Project.workItems`, accepted
decisions, active constraints and `Product.nonGoals` before proposing a work item,
requirement or design; extend what exists instead of duplicating it, and surface any
contradiction rather than writing over it. An instance marked
`"provenance": "onboarded"` was reconstructed from the codebase by `/mdse:onboard`
rather than specified by a person — treat it as a reading to verify, not settled intent.

**All development in this repository MUST go through the mdse workflow:**
`/mdse:requirements` → `/mdse:analysis` (optional) → `/mdse:design-and-taskify` →
`/mdse:implement --task <N>` → `/mdse:verify` → `/mdse:reconcile`. Run `/mdse:help` for
the full command reference. The only exception is a small, well-scoped edit to an
existing work item — a bug fix, a copy change, a one-file tweak that changes no
contract, requirement or architecture decision — which may be made directly, following
the conventions already recorded for the relevant workspace at
`.mdse/model/workspaces/`. When in doubt whether an edit qualifies, it doesn't — run it
through the workflow.

**Picking work back up after a break:** run `/mdse:resume` instead of manually
re-running implement for each leftover task — it finds every pending or in-progress
task and drives it through to verify and reconcile automatically.

**Rules:**
- Do not freehand development beyond a small, well-scoped edit (see above) — run it
  through the mdse workflow instead of writing code or specs ad hoc.
- Do not write prose documents into `.mdse/` — it holds typed instances only.
- Do not delete an instance directly — set its lifecycle status, or use the
  reviewed `/mdse:compact` workflow so the exact original enters cold history.
- Do not hand-edit an instance into a shape that violates its schema. Validate with
  `mdse validate .mdse` after writing.
<!-- mdse:end -->
