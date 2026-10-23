<!-- mdse:start -->
## MDSE project workflow

This repository uses an `.mdse/` model. Read relevant context before engineering
changes, using MDSE's read-only tools or `mdse context .mdse --json`.

Before answering project questions, read the overview and architecture. For an
existing work item, inspect its status, requirements, design, constraints,
decisions and relevant tasks before editing code. Status fields, not file
existence, describe progress. Check existing work items, accepted decisions and
product non-goals before proposing new work; extend rather than duplicate them.
Treat onboarded instances as reconstructed evidence to review, not settled intent.

Use the mdse skill for the requested operation. Load canonical instructions
with `get_operation` through MCP or `mdse operations show NAME --json`.
The usual workflow is requirements → analysis (when needed) → design-and-taskify
→ implement → verify → reconcile. Validate with `mdse validate .mdse`.
Keep model evidence and implementation aligned; do not invent verification
results, silently delete model instances, or treat workflow retrieval as execution.
Small non-behavioral edits need not start a new engineering work item.
Do not write prose documents under `.mdse/`; it holds typed instances only.
Use the reviewed compact workflow to archive rather than directly deleting
instances. Use resume to continue pending work, and record actual execution and
verification evidence before updating delivery status.
<!-- mdse:end -->
