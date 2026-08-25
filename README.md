# PROJECT FIRE

> An AI-native business operating system. It discovers, evaluates, validates, designs, builds, launches, sells, operates, and optimizes multiple AI-enabled businesses — and treats revenue as a first-class system variable.

**North star:** R1,000,000/day system capacity — modeled as *number of revenue engines × average daily revenue per engine*, not one magical product. This is a capacity target, **not claimed revenue**.

## Architecture (canonical)

```
GITHUB = canonical agent library + FIRE source
LOCAL  = development / control / cache node
RUNTIME = on-demand (lazy) agent activation
```

Only the agents a mission actually needs are loaded. A 270-agent library is indexed; a mission typically activates 5–8.

```
MISSION → objective parse → capability search → agent selection (lazy)
  → team assembly → workflow → execution → evaluation (GO/REVISE/NO-GO)
  → economic result → memory → improved next execution
```

## Quickstart

```bash
cd PROJECT_FIRE
pip install -r requirements.txt        # stdlib-only: nothing required

# 1. Index the agent library (Markdown -> structured registry)
python -m fire registry build
python -m fire registry stats

# 2. Capability search (returns ONLY relevant agents)
python -m fire search "voice quoting tradespeople south africa whatsapp"

# 3. Mission → objective → team → workflow
python -m fire mission "Find the highest-potential business opportunity that can be validated quickly in South Africa and has a credible path toward scalable recurring revenue."

# 4. Lazy-activate a team pack (copies only the selected agents)
python -m fire materialize "Build an MVP for a WhatsApp voice-note to PDF quote service priced at R199/month"

# 5. Opportunity hunt (scored & ranked, with kill/scale criteria)
python -m fire hunt

# 6. Quality / reality gate
python -m fire evaluate reports/opportunity_hunt.md

# 7. Revenue model + capacity scenario
python -m fire revenue

# 8. Control room dashboard (static HTML, no deps)
python -m fire dashboard
```

## Repository layout

```
PROJECT_FIRE/
├── fire/                  # the operating system
│   ├── registry.py        # discover -> parse -> index -> capability search
│   ├── kernel.py          # NL missions -> objective -> team -> workflow
│   ├── opportunity.py     # 15-criterion scoring, seed hunt, ranking
│   ├── quality.py         # Reality Engine: GO / REVISE / NO-GO
│   ├── memory.py          # JSONL event + mission log
│   ├── revenue.py         # MRR/ARR/margin + R1M/day capacity model
│   ├── dashboard.py       # control room HTML generator
│   └── cli.py             # command interface
├── agents/agency-agents/  # canonical agent library (git submodule-ready; MIT)
├── registry/              # agent_registry.json (built index)
├── memory/                # events + missions (auto-created)
├── reports/               # hunt reports (opportunity_hunt.json / .md)
├── artifacts/teams/       # lazily materialized team packs
├── control_room/          # generated dashboard
├── experiments/voice_quote/  # Experiment A validation kit (manual concierge)
├── tests/                 # 40 unittest cases
├── config/fire.json
└── docs/ARCHITECTURE.md
```

## Rules of the system

1. **No bullshit amplification.** Every claim is either evidence-cited or explicitly tagged *hypothesis*. The Reality Engine gates all outputs.
2. **Lazy activation.** Agents are retrieved on demand from the remote library; nothing runs that a mission doesn't need.
3. **GitHub is canonical.** This repo is designed to live on GitHub; the laptop is only the control node.
4. **Revenue is data.** Every workflow reports economics back to the Revenue Engine and memory.

## Testing

```bash
python -m unittest discover -s tests -v
```

## License & provenance

FIRE is original code (MIT). The agent library under `agents/agency-agents/` is the MIT-licensed `msitarzewski/agency-agents` project (its LICENSE is preserved in place).
