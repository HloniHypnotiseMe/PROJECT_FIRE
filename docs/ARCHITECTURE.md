# PROJECT FIRE — Architecture

## 1. Deployment topology

```
                    GITHUB (canonical)
                       |
                AGENT LIBRARY (agents/agency-agents, MIT)
                       |
                FIRE REGISTRY (registry/agent_registry.json)
                       |
                CAPABILITY INDEX (inverted index over 270 agents)
                       |
                 MISSION INPUT (Command Kernel)
                       |
               AGENT SELECTION (capability search)
                       |
            ONLY REQUIRED AGENTS (lazy materialization)
                       |
                   EXECUTION (workflow)
                       |
                EVALUATION (Reality Engine: GO/REVISE/NO-GO)
                       |
                  MEMORY (events + missions)
                       |
                  IMPROVEMENT (lessons feed next run)
```

- **GitHub** holds the code + the canonical agent library. Thousands of agent definitions can exist remotely.
- **Local laptop** is a development/control/cache node. It never hosts a permanent 200-agent runtime.
- **Runtime** activates agents on demand: `fire materialize` copies only the selected agents into a team pack (observed: 6 of 270).

## 2. Modules

| Module | Responsibility |
|---|---|
| `fire/registry.py` | Parse Markdown frontmatter + sections into `AgentRecord`; build inverted index; TF-IDF search with synonym/prefix expansion; write `agent_registry.json`. |
| `fire/kernel.py` | `parse_objective` (intent/departments/stages/constraints) → `assemble_team` (orchestrator + one executor per relevant dept + quality gate) → `build_workflow` (phase × agent steps). |
| `fire/opportunity.py` | 15 weighted criteria (normalised weights sum ≈ 1); direction handling for inverse criteria; 14 seed opportunities; ranking + reasons; hunt report. |
| `fire/quality.py` | Reality Engine: artifact checks (exists, size, required sections, forbidden claims, citations) → GO/REVISE/NO-GO; opportunity gate (min score 6.5). |
| `fire/memory.py` | Append-only JSONL event log + mission lifecycle (start/update/read) + lessons. |
| `fire/revenue.py` | Per-engine MRR/ARR/profit/margin; portfolio aggregation; R1M/day capacity scenario (engines_needed = target / avg daily). |
| `fire/dashboard.py` | Dependency-free static HTML control room (inline CSS) showing registry, missions, ranking, revenue, capacity. |
| `fire/cli.py` | `registry build|stats · search · mission · team · materialize · hunt · evaluate · revenue · dashboard · status` |

## 3. Key design decisions

1. **Filenames are facts, not guesses.** The registry derives `agent_id` from the actual file (`engineering-rapid-prototyper.md` → `engineering.rapid-prototyper`), so the earlier `cp software-engineer.md` failure class is eliminated by construction.
2. **One index, many consumers.** The registry JSON is the single source of truth for search, team assembly, dashboard, and reports.
3. **Independent evaluation.** Executors and the reality gate are separate paths; the gate defaults to "NEEDS WORK" and requires evidence.
4. **R1M/day is a model, not a claim.** The revenue engine prints it as `CAPACITY TARGET — not realised revenue`.

## 4. Roadmap (beyond v0.1)

- GitHub provisioning script (`scripts/push_to_github.sh`) — needs a PAT or `gh` auth on the user's machine.
- Agent dependency graph + DAG-based orchestration instead of linear workflow.
- LLM-backed objective parser (current parser is deterministic rules).
- Real LLM execution layer that runs each agent prompt against a model and returns artifacts to the quality gate.
- Web control room with live mission tracking.
