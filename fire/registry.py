"""Agent Registry: discover -> parse -> index -> search.

Transforms the Markdown agent library (GitHub-canonical) into structured
metadata and provides capability search with lazy/on-demand retrieval.

No agent is loaded into memory unless a mission actually needs it.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Iterable, Optional

from .models import AgentRecord, RegistryStats
from .config import load_config, paths

# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u2190-\u21FF\u2B50\u2728]"
)
FRONTMATTER_RE = re.compile(r"^---\s*$")
KV_RE = re.compile(r"^([A-Za-z_][\w]*)\s*:\s*(.*)$")
BULLET_RE = re.compile(r"^[\s]*[-*+•]+\s+(.*)$")
NUM_BULLET_RE = re.compile(r"^\s*\d+[.)]\s+(.*)$")
HEADER_RE = re.compile(r"^(#{2,4})\s+(.*)$")

STAGES = [
    "discover", "validate", "design", "build", "launch", "sell", "operate", "optimize",
]

STAGE_KEYWORDS: dict[str, list[str]] = {
    "discover": ["market intelligence", "trend research", "opportunity research",
                 "horizon scanning", "exploratory", "investigation"],
    "validate": ["validate", "validation", "feedback loop", "experiment", "hypothesis",
                 "evidence-based", "a/b", "ab test", "assumption", "proof"],
    "design": ["ux", "wireframe", "storyboard", "aesthetic", "typography",
               "brand identity", "visual identity", "layout", "design system"],
    "build": ["mvp", "prototype", "prototyping", "implementation", "implementing",
              "coding", "development", "engineering", "architecture"],
    "launch": ["launch", "go-to-market", "gtm", "release", "rollout", "deploy",
               "distribution", "ship"],
    "sell": ["outbound", "pipeline", "proposal", "pitch", "discovery call",
             "quota", "close the deal", "sales process", "lead gen"],
    "operate": ["incident", "triage", "on-call", "reliability", "monitoring",
                "maintenance", "operations", "stability", "sre"],
    "optimize": ["optimize", "seo", "growth", "conversion", "retention",
                 "performance", "efficiency", "improvement"],
}

TOOLS: dict[str, re.Pattern] = {
    "python": re.compile(r"\bpython\b"),
    "typescript": re.compile(r"\btypescript\b"),
    "javascript": re.compile(r"\bjavascript\b"),
    "react": re.compile(r"\breact\b"),
    "next.js": re.compile(r"next\.?js", re.I),
    "node.js": re.compile(r"\bnode\.?js\b", re.I),
    "go": re.compile(r"\bgo(lang)?\b"),
    "rust": re.compile(r"\brust\b"),
    "aws": re.compile(r"\baws\b"),
    "gcp": re.compile(r"\bgcp\b|\bgoogle cloud\b", re.I),
    "azure": re.compile(r"\bazure\b"),
    "docker": re.compile(r"\bdocker\b"),
    "kubernetes": re.compile(r"\bkubernetes\b|\bk8s\b", re.I),
    "sql": re.compile(r"\bsql\b"),
    "postgres": re.compile(r"\bpostgres(ql)?\b", re.I),
    "mysql": re.compile(r"\bmysql\b", re.I),
    "mongodb": re.compile(r"\bmongodb\b", re.I),
    "redis": re.compile(r"\bredis\b"),
    "openai": re.compile(r"\bopenai\b", re.I),
    "claude": re.compile(r"\bclaude\b", re.I),
    "gpt": re.compile(r"\bgpt[-\d]*\b", re.I),
    "llm": re.compile(r"\bllm\b|\blarge language model", re.I),
    "langchain": re.compile(r"\blangchain\b", re.I),
    "twilio": re.compile(r"\btwilio\b", re.I),
    "whatsapp": re.compile(r"\bwhatsapp\b", re.I),
    "telegram": re.compile(r"\btelegram\b", re.I),
    "stripe": re.compile(r"\bstripe\b", re.I),
    "payment": re.compile(r"\bpayments?\b", re.I),
    "notion": re.compile(r"\bnotion\b", re.I),
    "zapier": re.compile(r"\bzapier\b", re.I),
    "salesforce": re.compile(r"\bsalesforce\b", re.I),
    "hubspot": re.compile(r"\bhubspot\b", re.I),
    "shopify": re.compile(r"\bshopify\b", re.I),
    "wordpress": re.compile(r"\bwordpress\b", re.I),
    "figma": re.compile(r"\bfigma\b", re.I),
    "unity": re.compile(r"\bunity\b", re.I),
    "unreal": re.compile(r"\bunreal\b", re.I),
    "godot": re.compile(r"\bgodot\b", re.I),
    "blender": re.compile(r"\bblender\b", re.I),
    "swift": re.compile(r"\bswift\b", re.I),
    "kotlin": re.compile(r"\bkotlin\b", re.I),
    "flutter": re.compile(r"\bflutter\b", re.I),
    "react-native": re.compile(r"\breact native\b", re.I),
    "terraform": re.compile(r"\bterraform\b", re.I),
    "ansible": re.compile(r"\bansible\b", re.I),
    "grafana": re.compile(r"\bgrafana\b", re.I),
    "prometheus": re.compile(r"\bprometheus\b", re.I),
    "snowflake": re.compile(r"\bsnowflake\b", re.I),
    "bigquery": re.compile(r"\bbigquery\b", re.I),
    "dbt": re.compile(r"\bdbt\b", re.I),
    "airflow": re.compile(r"\bairflow\b", re.I),
    "quickbooks": re.compile(r"\bquickbooks\b", re.I),
    "xero": re.compile(r"\bxero\b", re.I),
    "fastapi": re.compile(r"\bfastapi\b", re.I),
    "flask": re.compile(r"\bflask\b", re.I),
    "django": re.compile(r"\bdjango\b", re.I),
    "rails": re.compile(r"\brails\b", re.I),
    "c++": re.compile(r"\bc\+\+\b"),
    "c#": re.compile(r"\bc#\b"),
    "java": re.compile(r"\bjava\b"),
    "solidity": re.compile(r"\bsolidity\b"),
    "contract": re.compile(r"\bsmart contract", re.I),
    "ethereum": re.compile(r"\bethereum\b", re.I),
}

# canonical section map: normalized header -> key
SECTION_ALIASES = {
    "identity memory": "identity",
    "your identity memory": "identity",
    "your identity": "identity",
    "core mission": "mission",
    "your core mission": "mission",
    "critical rules": "rules",
    "critical rules you must follow": "rules",
    "your critical rules": "rules",
    "success metrics": "metrics",
    "your success metrics": "metrics",
    "workflow": "workflow",
    "workflow process": "workflow",
    "your workflow": "workflow",
    "your workflow process": "workflow",
    "advanced capabilities": "capabilities",
    "core capabilities": "capabilities",
    "your core capabilities": "capabilities",
    "technical deliverables": "deliverables",
    "your technical deliverables": "deliverables",
    "communication style": "communication",
    "your communication style": "communication",
    "learning memory": "learning",
    "your learning memory": "learning",
    "learning": "learning",
}

RISK_BY_DEPT = {
    "security": "high",
    "healthcare": "high",
    "finance": "high",
    "engineering": "medium",
    "specialized": "medium",
    "paid-media": "medium",
    "testing": "low",
    "design": "low",
    "marketing": "low",
    "support": "low",
    "product": "low",
    "sales": "low",
    "project-management": "low",
    "academic": "low",
    "gis": "medium",
    "game-development": "low",
    "spatial-computing": "low",
}

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "with",
    "is", "are", "was", "were", "be", "been", "you", "your", "our", "we",
    "it", "that", "this", "these", "those", "from", "by", "as", "at", "into",
    "can", "will", "would", "should", "has", "have", "had", "do", "does",
    "not", "no", "but", "if", "then", "than", "so", "all", "any", "how",
    "what", "when", "where", "who", "why", "which", "their", "there", "here",
    "about", "between", "using", "use", "used", "via", "across", "within",
    "able", "expert", "specialist", "specialized", "professional", "proven",
    "deep", "delivering", "deliver", "drive", "drives", "driven", "help",
    "helps", "helping", "high", "quality", "world", "class", "world-class",
    "every", "each", "other", "also", "very", "just", "even", "well", "make",
    "making", "get", "gets", "create", "creating", "build", "building",
    "through", "over", "under", "out", "up", "down", "off", "again",
}


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Lowercase, strip punctuation/emoji, collapse whitespace."""
    text = EMOJI_RE.sub(" ", text)
    text = re.sub(r"[`*#_~>|]", " ", text)
    text = re.sub(r"[^A-Za-z0-9\s'-]", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def _normalize_header(text: str) -> str:
    return _normalize(text).replace("-", " ")


def _parse_frontmatter(text: str) -> dict:
    """Parse YAML-ish frontmatter between leading '---' fences."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    meta: dict = {}
    current_key: Optional[str] = None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        m = KV_RE.match(line)
        if m:
            current_key, val = m.group(1), m.group(2).strip()
            val = val.strip("\"'")
            meta[current_key] = val
        elif current_key and line.strip():
            # continuation line -> append to previous value
            prev = str(meta.get(current_key, ""))
            meta[current_key] = (prev + " " + line.strip()).strip()
    return meta


def _split_into_sections(text: str) -> dict:
    """Split agent body into canonical sections.

    ## headers start/stop sections. Unknown ## headers close the current
    section; ### / #### sub-headers keep the current section open (they are
    sub-structure inside a section) unless they match a known alias.
    """
    sections: dict[str, list[str]] = {}
    current: Optional[str] = None
    for line in text.splitlines():
        hm = HEADER_RE.match(line)
        if hm:
            level = len(hm.group(1))
            key = SECTION_ALIASES.get(_normalize_header(hm.group(2)))
            if key:
                current = key
                sections.setdefault(key, [])
            elif level == 2:
                current = None
            continue
        if current:
            sections[current].append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items()}


def _extract_bullets(section_text: str) -> list[str]:
    if not section_text:
        return []
    out = []
    for line in section_text.splitlines():
        m = BULLET_RE.match(line) or NUM_BULLET_RE.match(line)
        if m:
            item = m.group(1).strip()
            item = re.sub(r"^[\s]*", "", item)
            item = re.sub(r"\s*:.*$", "", item)  # keep phrase before colon
            item = EMOJI_RE.sub(" ", item).strip()
            item = re.sub(r"[`*#]", "", item).strip()
            if len(item) > 3:
                out.append(item)
    return out


def _clean_capabilities(items: Iterable[str], limit: int = 12) -> list[str]:
    seen = set()
    out = []
    for it in items:
        key = _normalize(it)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(it.strip())
        if len(out) >= limit:
            break
    return out


def _extract_tools(text: str) -> list[str]:
    found = []
    for name, pattern in TOOLS.items():
        if pattern.search(text):
            found.append(name)
    return sorted(set(found))


def _extract_stages(text: str) -> list[str]:
    low = text.lower()
    stages = []
    for stage, kws in STAGE_KEYWORDS.items():
        if any(kw in low for kw in kws):
            stages.append(stage)
    return stages


def _extract_io(description: str) -> tuple[list, list]:
    """Extract inputs/outputs from patterns like 'Transforms X into Y'."""
    m = re.search(r"(?:transforms|turns|converts|translate|converts)\s+(.+?)\s+into\s+(.+)",
                  description, re.I)
    if m:
        return [m.group(1).strip()], [m.group(2).strip()]
    m2 = re.search(r"specializ(?:es|ing)\s+in\s+(.+?)[. ]", description, re.I)
    if m2:
        return [m2.group(1).strip()], []
    return [], []


def _slug_of(filename: str) -> str:
    return Path(filename).stem


def parse_agent_file(path: Path, department: str) -> Optional[AgentRecord]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    if not text.strip().startswith("---"):
        return None

    meta = _parse_frontmatter(text)
    name = meta.get("name") or path.stem.replace("-", " ").title()
    desc = meta.get("description", "")

    # agent_id: department.core-slug (strip department prefix from filename)
    slug = _slug_of(path.name)
    core = slug
    prefix = f"{department}-"
    if core.startswith(prefix):
        core = core[len(prefix):]
    agent_id = f"{department}.{core}"

    sections = _split_into_sections(text)

    caps = []
    for key in ("mission", "capabilities", "deliverables"):
        caps.extend(_extract_bullets(sections.get(key, "")))
    caps = _clean_capabilities(caps)

    metrics = _extract_bullets(sections.get("metrics", ""))

    full_text = meta.get("description", "") + "\n" + text
    tools = _extract_tools(full_text)
    stages = _extract_stages(full_text)
    inputs, outputs = _extract_io(desc)
    if not inputs and sections.get("identity"):
        inputs = _extract_bullets(sections["identity"])[:2]

    risk = RISK_BY_DEPT.get(department, "medium")
    if department in ("specialized", "support", "engineering", "finance") and any(
        k in full_text.lower() for k in ("compliance", "regulatory", "privacy", "popia", "gdpr")
    ):
        risk = "high"

    record = AgentRecord(
        agent_id=agent_id,
        name=name,
        department=department,
        slug=slug,
        description=desc,
        emoji=meta.get("emoji", ""),
        vibe=meta.get("vibe", ""),
        capabilities=caps,
        success_metrics=metrics,
        inputs=inputs,
        outputs=outputs,
        tools=tools,
        lifecycle_stages=stages or ["build"],
        risk_level=risk,
        source_path=str(path),
        sections=sections,
    )
    return record


# ---------------------------------------------------------------------------
# Discovery + build
# ---------------------------------------------------------------------------

def discover_agents(library_root: Path) -> list[Path]:
    """Find all candidate agent files (md with frontmatter) under library root."""
    candidates = []
    for path in library_root.rglob("*.md"):
        rel = path.relative_to(library_root)
        parts = rel.parts
        if not parts:
            continue
        if parts[0] in ("integrations", "strategy", "examples", "scripts", ".github"):
            continue
        if path.name in ("README.md", "CONTRIBUTING.md", "CONTRIBUTING_zh-CN.md",
                         "SECURITY.md", "LICENSE"):
            continue
        if len(parts) < 2:
            continue
        candidates.append(path)
    return candidates


def build_registry(cfg: dict | None = None) -> tuple[list[AgentRecord], RegistryStats]:
    cfg = cfg or load_config()
    p = paths(cfg)
    lib = p["agent_library"]
    records: list[AgentRecord] = []
    stats = RegistryStats()

    for path in discover_agents(lib):
        dept = path.relative_to(lib).parts[0]
        rec = parse_agent_file(path, dept)
        if rec is None:
            stats.agents_without_frontmatter += 1
            continue
        records.append(rec)
        stats.departments[dept] = stats.departments.get(dept, 0) + 1
        for stage in rec.lifecycle_stages:
            stats.stages[stage] = stats.stages.get(stage, 0) + 1
        for tool in rec.tools:
            stats.tools[tool] = stats.tools.get(tool, 0) + 1

    records.sort(key=lambda r: r.agent_id)
    stats.total_agents = len(records)

    p["registry_file"].parent.mkdir(parents=True, exist_ok=True)
    p["registry_file"].write_text(
        json.dumps([r.to_dict() for r in records], indent=2),
        encoding="utf-8",
    )
    stats.index_file = str(p["registry_file"])
    return records, stats


def load_registry(cfg: dict | None = None) -> list[AgentRecord]:
    """Load records from the canonical registry index (or build if missing)."""
    cfg = cfg or load_config()
    p = paths(cfg)
    if p["registry_file"].exists():
        data = json.loads(p["registry_file"].read_text(encoding="utf-8"))
        return [AgentRecord(**d) for d in data]
    records, _ = build_registry(cfg)
    return records


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def tokenize(text: str) -> list[str]:
    toks = []
    for t in re.findall(r"[A-Za-z0-9][A-Za-z0-9'\-]*", _normalize(text)):
        if t not in STOPWORDS:
            toks.append(t)
    return toks


# lightweight query expansion: synonyms + prefix matching
SYNONYMS: dict[str, list[str]] = {
    "voice": ["voice", "speech", "audio", "spoken", "narration"],
    "quote": ["quote", "quoting", "quotation", "estimate", "estimates", "pricing"],
    "service": ["service", "services", "servicing"],
    "whatsapp": ["whatsapp", "messaging"],
    "tradespeople": ["tradespeople", "tradesperson", "plumber", "electrician",
                     "handyman", "contractor"],
    "mvp": ["mvp", "prototype", "prototyping", "prototyper"],
    "build": ["build", "building", "develop", "development", "implement"],
    "south": ["south", "african", "africa", "sa"],
    "pdf": ["pdf", "document", "documents", "report"],
    "chat": ["chat", "conversation", "chatbot"],
    "legal": ["legal", "law", "compliance", "regulatory", "contract"],
    "finance": ["finance", "financial", "money", "cash"],
    "marketing": ["marketing", "campaign", "social"],
    "sales": ["sales", "selling", "outbound"],
}


class CapabilitySearch:
    """Inverted-index capability search over the agent registry."""

    def __init__(self, records: list[AgentRecord]):
        self.records = records
        self.docs: dict[str, AgentRecord] = {r.agent_id: r for r in records}
        self.doc_terms: dict[str, set] = {}
        self.postings: dict[str, set] = {}
        self._build()
        self.sorted_terms = sorted(self.postings.keys())

    def _build(self):
        for rec in self.records:
            corpus = " ".join([
                rec.name, rec.description, rec.department,
                " ".join(rec.capabilities),
                " ".join(rec.tools),
                " ".join(rec.inputs), " ".join(rec.outputs),
            ])
            terms = set(tokenize(corpus))
            self.doc_terms[rec.agent_id] = terms
            for t in terms:
                self.postings.setdefault(t, set()).add(rec.agent_id)
            # boost name terms
            for t in tokenize(rec.name):
                self.doc_terms[rec.agent_id].add(t)
                self.postings.setdefault(t, set()).add(rec.agent_id)

    def _expand(self, term: str) -> list[str]:
        """Query-term expansion: synonyms + prefix matches (min 3 chars)."""
        out = [term]
        out.extend(SYNONYMS.get(term, []))
        if len(term) >= 3:
            import bisect
            lo = bisect.bisect_left(self.sorted_terms, term)
            for i in range(lo, len(self.sorted_terms)):
                cand = self.sorted_terms[i]
                if not cand.startswith(term):
                    break
                if cand != term:
                    out.append(cand)
        return out

    def idf(self, term: str) -> float:
        n = len(self.records)
        df = len(self.postings.get(term, ()))
        if df == 0:
            return 0.0
        return math.log((n + 1) / (df + 1)) + 1.0

    def search(self, query: str, top: int = 10, department: str | None = None,
               min_score: float = 0.0) -> list[dict]:
        terms = tokenize(query)
        if not terms:
            return []
        scores: dict[str, float] = {}
        matched: dict[str, list[str]] = {}
        seen_expanded: dict[str, set] = {}
        for t in terms:
            expanded = self._expand(t)
            seen_expanded[t] = set(expanded)
            for et in expanded:
                widf = self.idf(et)
                if widf <= 0:
                    continue
                for doc_id in self.postings.get(et, ()):
                    if department and self.docs[doc_id].department != department:
                        continue
                    scores[doc_id] = scores.get(doc_id, 0.0) + widf
                    if t not in matched.setdefault(doc_id, []):
                        matched[doc_id].append(t)
        # small boost for exact-name hits
        for doc_id in scores:
            name_terms = self.doc_terms[doc_id] & set(terms)
            scores[doc_id] += 0.4 * len(name_terms)

        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        out = []
        for doc_id, score in ranked[:top]:
            if score < min_score:
                continue
            rec = self.docs[doc_id]
            out.append({
                "agent_id": doc_id,
                "name": rec.name,
                "department": rec.department,
                "emoji": rec.emoji,
                "score": round(score, 3),
                "matched_terms": sorted(set(matched[doc_id])),
                "capabilities": rec.capabilities[:5],
                "tools": rec.tools,
                "risk_level": rec.risk_level,
                "source_path": rec.source_path,
            })
        return out

    def get(self, agent_id: str) -> Optional[AgentRecord]:
        return self.docs.get(agent_id)

    def snapshot_meta(self) -> dict:
        return {
            "indexed": len(self.records),
            "terms": len(self.postings),
        }
