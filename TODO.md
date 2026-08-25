# PROJECT FIRE — TODO Tracker

Updated: 2026-08-25 (handoff build). Legend: [x] done · [~] in progress · [ ] open

## Priority 0 — Foundation (this build)

- [x] Dedicated FIRE project scaffold (`/home/user/PROJECT_FIRE`)
- [x] Canonical agent library vendored (`agents/agency-agents`, MIT, 270 agents / 17 divisions)
- [x] Agent registry: Markdown -> structured metadata (`registry/agent_registry.json`, 270 records)
- [x] Capability search: inverted index + TF-IDF + synonym/prefix expansion
- [x] Lazy/on-demand retrieval: `fire materialize` (6 of 270 activated per mission)
- [x] Command Kernel: `parse_objective` -> `assemble_team` -> `build_workflow`
- [x] Kernel -> Registry -> Team Builder wiring
- [x] Opportunity Engine: 15 criteria, 14 seeds, ranking + reasons
- [x] Quality/Reality Engine: GO / REVISE / NO-GO gates
- [x] Memory: event log + mission lifecycle
- [x] Revenue Engine: MRR/ARR/margin + R1M/day capacity model
- [x] Control Room dashboard (static HTML)
- [x] Test suite: 38 unittest cases green
- [x] First mission run: "Find highest-potential opportunity..." -> ranked hunt report
- [x] Hunt report with evidence, economics, validation experiment, kill/scale criteria
- [x] Team pack materialized for WA voice-quote MVP

## Priority 1 — GitHub (next)

- [ ] Create dedicated GitHub repo (`PROJECT_FIRE`) on https://github.com/HloniHypnotiseMe
- [ ] Push FIRE source + agent library to remote (needs PAT/`gh` auth on user machine — see scripts/push_to_github.sh)
- [ ] Convert `agents/agency-agents` to a submodule or pinned vendored copy
- [ ] Verify registry builds from the remote source, not local cache

## Priority 2 — Validate first opportunity (in progress)

- [ ] Run Experiment A (WA voice-quote concierge, 10 JHB tradespeople) — kill/scale gates in reports/opportunity_hunt.md §7
- [ ] Run Experiment B (Loom->SOP beta) — pre-purchase test
- [ ] Reality gate both experiments; log lessons to memory
- [ ] First FIRE-generated opportunity reaches a real customer

## Priority 3 — Hardening

- [ ] LLM-backed objective parser (replace deterministic rules)
- [ ] Agent dependency graph + DAG orchestration
- [ ] LLM execution layer (run agent prompts, return artifacts to quality gate)
- [ ] Live control room with real mission tracking
- [ ] Multi-engine portfolio automation toward R1M/day capacity

## Acceptance (handoff §20)

- [x] dedicated GitHub repository exists (locally; push pending auth)
- [x] agent library is remotely version-controlled (vendored; push pending auth)
- [x] 200+ agent definitions are indexed (270)
- [x] capability search works
- [x] agents can be retrieved on demand (lazy materialization)
- [x] Command Kernel accepts natural-language missions
- [x] Kernel can assemble an agent team
- [~] team can execute a workflow (workflow defined; LLM execution layer pending)
- [x] evaluator can score output (GO/REVISE/NO-GO)
- [x] memory records execution
- [x] Opportunity Engine can rank opportunities
- [x] FIRE can produce a real validation experiment
- [ ] first FIRE-generated opportunity reaches a real customer
- [ ] first revenue is generated
- [ ] economics are measured (model in place; real data pending)
