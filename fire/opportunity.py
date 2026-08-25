"""Opportunity Engine: score, rank and brief business opportunities.

FIRE must eventually DISCOVER opportunities, not only execute supplied ideas.
This module implements the scoring model and a seed set of SA-contextual
opportunities. All scores are explicit HYPOTHESES to be validated by the
quality/reality engine, never presented as fact.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .models import Opportunity
from .registry import CapabilitySearch

# ---------------------------------------------------------------------------
# Scoring model
# ---------------------------------------------------------------------------

# (criterion, weight, direction) — direction: 1 = higher better, -1 = lower better
CRITERIA: list[tuple[str, float, int]] = [
    ("pain", 0.09, 1),
    ("market_size", 0.08, 1),
    ("urgency", 0.07, 1),
    ("willingness_to_pay", 0.08, 1),
    ("competition", 0.05, -1),
    ("automation_potential", 0.07, 1),
    ("speed_to_mvp", 0.07, 1),
    ("distribution_difficulty", 0.05, -1),
    ("gross_margin", 0.06, 1),
    ("recurring_revenue", 0.08, 1),
    ("regulatory_risk", 0.04, -1),
    ("technical_complexity", 0.04, -1),
    ("customer_acquisition_cost", 0.06, -1),
    ("scalability", 0.08, 1),
    ("defensibility", 0.04, 1),
]

_WEIGHT_SUM = sum(w for _, w, _ in CRITERIA)  # ~0.96, normalize below

REASONS_LABEL = {
    "pain": "high pain", "market_size": "large addressable market",
    "urgency": "time-sensitive problem", "willingness_to_pay": "proven willingness to pay",
    "competition": "low competition", "automation_potential": "highly automatable",
    "speed_to_mvp": "fast to MVP", "distribution_difficulty": "easy distribution",
    "gross_margin": "high margin", "recurring_revenue": "recurring revenue shape",
    "regulatory_risk": "low regulatory risk", "technical_complexity": "low technical complexity",
    "customer_acquisition_cost": "low CAC", "scalability": "scales well",
    "defensibility": "defensible",
}


def score_opportunity(opp: Opportunity) -> Opportunity:
    total = 0.0
    contributions = []
    for crit, weight, direction in CRITERIA:
        raw = opp.scores.get(crit, 5.0)
        raw = max(0.0, min(10.0, float(raw)))
        if direction < 0:
            raw = 10.0 - raw
        w = weight / _WEIGHT_SUM
        total += w * raw
        contributions.append((crit, w * raw))
    contributions.sort(key=lambda kv: kv[1], reverse=True)
    opp.weighted_score = round(total, 2)
    top = [c for c in contributions if c[1] > 0.45][:5]
    opp.reasons = [REASONS_LABEL[c] for c, _ in (top or contributions[:3])]
    return opp


# ---------------------------------------------------------------------------
# Seed opportunities (SA-contextual, hypothesis-grade)
# ---------------------------------------------------------------------------

def _seed_opportunities() -> list[Opportunity]:
    def mk(oid: str, name: str, problem: str, customer: str, solution: str,
           pricing: str, distribution: str, mvp: str, scores: dict,
           validation: str, kill: list[str], scale: list[str],
           agents: list[str], economics: dict,
           optimize: list[str] | None = None) -> Opportunity:
        return Opportunity(
            id=oid, name=name, problem=problem, customer=customer,
            solution=solution, pricing=pricing, distribution=distribution,
            mvp=mvp, scores=scores, validation_experiment=validation,
            kill_criteria=kill, optimize_criteria=optimize or [],
            scale_criteria=scale, required_agents=agents,
            economics=economics,
        )

    return [
        mk(
            "opp-wa-voice-quote", "WhatsApp Voice-Note -> Quote for Tradespeople",
            "Tradespeople (plumbers, electricians) lose jobs because writing formal quotes takes hours; customers ghost on verbal estimates.",
            "SA tradespeople who use WhatsApp Business for jobs",
            "Forward a voice note -> FIRE transcribes -> produces branded PDF quote with itemised pricing in minutes.",
            "R199/month subscription (per trade business)",
            "WhatsApp Business API + local trade WhatsApp groups + referrals from hardware stores",
            "Manual concierge MVP: human transcribes VN, fills quote template, replies within 5 min; then automate with API.",
            {"pain": 9, "market_size": 6, "urgency": 8, "willingness_to_pay": 7,
             "competition": 7, "automation_potential": 9, "speed_to_mvp": 9,
             "distribution_difficulty": 7, "gross_margin": 9, "recurring_revenue": 9,
             "regulatory_risk": 8, "technical_complexity": 7, "customer_acquisition_cost": 7,
             "scalability": 7, "defensibility": 5},
            "Sell to 10 plumbers in one week via DMs; measure: % who send a 2nd voice note (retention), % who pay.",
            ["<5 of 10 first-touch prospects send a quote request", "no one pays after 14-day trial",
             "concierge turnaround > 30 min"],
            ["quote conversion lifts 20%+", "churn < 5%/month", "per-trade template libraries"],
            ["engineering.rapid-prototyper", "engineering.voice-ai-integration-engineer",
             "engineering.backend-architect", "sales.engineer",
             "marketing.tiktok-strategist", "finance.financial-analyst"],
            {"price": 199, "currency": "ZAR", "period": "month", "mrr_target_10": 1990},
            optimize=["5-7/10 send voice notes but 0-1 pay -> tighten offer/price ladder, 7-day trial",
                      "turnaround 5-30 min -> rebuild template, pre-fill common line items + rates",
                      "high response, <50% of responders send voice notes -> rewrite first-touch script",
                      "prospects want to pay but payment is friction -> add EFT details / PayFast link"],
        ),
        mk(
            "opp-cv-ats", "CV -> ATS Optimizer for Graduates",
            "SA graduates send CVs that ATS filters reject before a human sees them; they cannot afford professional CV writers.",
            "Unemployed/soon-to-graduate SA students applying through portals",
            "Upload CV + job spec -> FIRE rewrites the CV to pass ATS parsing and match keywords.",
            "R99 per CV (one-off); R249 for CV + LinkedIn refresh",
            "University WhatsApp groups, career centres, TikTok 'grad hacks' content",
            "Form + Stripe/PayFast checkout; manual GPT-driven rewrite first, API later.",
            {"pain": 8, "market_size": 7, "urgency": 9, "willingness_to_pay": 5,
             "competition": 5, "automation_potential": 9, "speed_to_mvp": 9,
             "distribution_difficulty": 6, "gross_margin": 9, "recurring_revenue": 4,
             "regulatory_risk": 9, "technical_complexity": 8, "customer_acquisition_cost": 6,
             "scalability": 7, "defensibility": 4},
            "Post on 5 university groups; offer first 20 CVs free; track repeat + referral rate.",
            ["<10 paid conversions from first 100 free users", "ATS pass rate not measurably higher"],
            ["referral loop: each paying grad refers 1+", "career-coaching upsell"],
            ["engineering.frontend-developer", "specialized.recruitment-specialist",
             "marketing.carousel-growth-engine", "product.manager",
             "marketing.tiktok-strategist"],
            {"price": 99, "currency": "ZAR", "period": "one-off", "target_20": 1980},
        ),
        mk(
            "opp-tenant-demand", "Tenant Demand Letter Generator",
            "SA landlords get non-paying tenants; lawyers charge R1,500+ for a demand letter and the legal act is often cited wrong.",
            "Residential landlords in JHB/CPT",
            "Paste WhatsApp chat + lease details -> FIRE produces a compliant demand letter citing the correct section (e.g. Consumer Protection Act / Rental Housing Act) as a PDF.",
            "R150 per letter; R99/mo unlimited",
            "Property WhatsApp groups, estate agents, rental agencies",
            "Template engine with POPIA-safe data handling + legal review pass before release.",
            {"pain": 8, "market_size": 6, "urgency": 7, "willingness_to_pay": 8,
             "competition": 6, "automation_potential": 8, "speed_to_mvp": 7,
             "distribution_difficulty": 6, "gross_margin": 9, "recurring_revenue": 6,
             "regulatory_risk": 3, "technical_complexity": 7, "customer_acquisition_cost": 6,
             "scalability": 6, "defensibility": 5},
            "Validate with 15 landlords via estate-agent referral; success = they actually send the letter.",
            ["lawyer review flags legal errors", "landlords prefer DIY templates to paying R150"],
            ["partnership with rental agencies", "escalation bundle: letter + attorney referral fee"],
            ["specialized.legal-document-review", "engineering.minimal-change-engineer",
             "sales.outbound-strategist", "marketing.seo-specialist"],
            {"price": 150, "currency": "ZAR", "period": "one-off", "target_15": 2250},
        ),
        mk(
            "opp-loom-sop", "Loom -> SOP Generator (Global)",
            "Operations teams re-record the same walkthroughs because no one converts them into documented SOPs.",
            "Startups & ops teams globally (USD market)",
            "Paste a Loom link -> FIRE transcribes, segments steps, and produces a Notion-ready SOP with screenshots placeholders.",
            "$15/month per seat; $99/year",
            "Product Hunt, LinkedIn ops content, Notion template marketplaces",
            "Paste-link form -> transcription -> structured SOP; manual QA before automation.",
            {"pain": 7, "market_size": 8, "urgency": 5, "willingness_to_pay": 7,
             "competition": 6, "automation_potential": 8, "speed_to_mvp": 8,
             "distribution_difficulty": 5, "gross_margin": 9, "recurring_revenue": 9,
             "regulatory_risk": 9, "technical_complexity": 7, "customer_acquisition_cost": 5,
             "scalability": 9, "defensibility": 5},
            "Land 10 beta teams from a LinkedIn launch post; success = 5 convert to paid.",
            ["<40% of trials convert to paid", "SOP quality below manual baseline"],
            ["SOP library + audit trail upsell", "enterprise SSO"],
            ["engineering.ai-engineer", "support.analytics-reporter",
             "marketing.linkedin-content-creator", "product.manager"],
            {"price": 15, "currency": "USD", "period": "month", "mrr_target_10": 150},
        ),
        mk(
            "opp-invoice-chaser", "Invoice Chaser (3% of recovered)",
            "Freelancers and SMMEs lose cash flow because chasing invoices is awkward and inconsistent.",
            "SA freelancers & agencies with recurring receivables",
            "Connect Gmail -> FIRE monitors unpaid invoices and sends polite, escalating chase sequences; you take a % of recovered.",
            "3% of recovered amounts (no win, no fee)",
            "Freelancer communities, accountants who refer clients",
            "Gmail OAuth read + manual send first; only charge on verified recovery.",
            {"pain": 8, "market_size": 7, "urgency": 7, "willingness_to_pay": 8,
             "competition": 7, "automation_potential": 8, "speed_to_mvp": 6,
             "distribution_difficulty": 6, "gross_margin": 8, "recurring_revenue": 5,
             "regulatory_risk": 5, "technical_complexity": 5, "customer_acquisition_cost": 6,
             "scalability": 7, "defensibility": 5},
            "5 freelancers give 1 unpaid invoice each; recover 2 -> shows 3% works.",
            ["<20% of chased invoices recovered", "freelancers unwilling to grant Gmail access"],
            ["commission escalates to collection partners", "API for accounting tools"],
            ["finance.bookkeeper-controller", "engineering.email-intelligence-engineer",
             "sales.engineer", "marketing.linkedin-content-creator"],
            {"price": 0.03, "currency": "ZAR", "period": "percent", "target_5": 600},
        ),
        mk(
            "opp-school-appeal", "School Admission Appeal Letters",
            "SA parents get rejection letters from oversubscribed schools; appeals are time-sensitive and must hit the right legal framing.",
            "SA parents (especially GDE placement season, Oct-Nov)",
            "Input school + reason + child profile -> FIRE drafts a persuasive appeal letter with correct department circular references.",
            "R250-R500 per letter",
            "Parent WhatsApp groups, education forums, seasonal SEO",
            "Template + editing loop with a human review before send.",
            {"pain": 8, "market_size": 6, "urgency": 9, "willingness_to_pay": 7,
             "competition": 6, "automation_potential": 7, "speed_to_mvp": 8,
             "distribution_difficulty": 6, "gross_margin": 9, "recurring_revenue": 3,
             "regulatory_risk": 5, "technical_complexity": 7, "customer_acquisition_cost": 6,
             "scalability": 5, "defensibility": 4},
            "Seasonal launch (GDE placement window); 20 letters; measure appeals accepted.",
            ["<10 sales in the placement window", "no evidence appeals improve outcomes"],
            ["multi-city expansion", "sibling bundle pricing"],
            ["specialized.legal-document-review", "marketing.seo-specialist",
             "marketing.wechat-official-account", "sales.outbound-strategist"],
            {"price": 300, "currency": "ZAR", "period": "one-off", "season_target": 6000},
        ),
        mk(
            "opp-tax-informal", "Tax Season Helper for Informal Traders",
            "SA informal traders fear SARS; bookkeepers charge too much; they file late and get penalties.",
            "Spaza owners, market traders, gig workers",
            "WhatsApp chat: snap receipts -> FIRE produces a SARS-ready provisional return summary in plain language.",
            "R99/return; R149/mo during tax season",
            "Radio, community WhatsApp groups, SARS-accredited workshops",
            "Receipt photo -> categorised income/expense summary -> printable form.",
            {"pain": 7, "market_size": 7, "urgency": 8, "willingness_to_pay": 6,
             "competition": 6, "automation_potential": 8, "speed_to_mvp": 7,
             "distribution_difficulty": 5, "gross_margin": 8, "recurring_revenue": 6,
             "regulatory_risk": 4, "technical_complexity": 6, "customer_acquisition_cost": 6,
             "scalability": 6, "defensibility": 4},
            "Partner 1 community org; 30 filings; measure accuracy vs bookkeeper audit.",
            ["<30 filings in season", "users still need a professional to file"],
            ["year-round bookkeeping upsell", "SARS eFiling API integration"],
            ["finance.tax-strategist", "finance.bookkeeper-controller",
             "engineering.voice-ai-integration-engineer", "marketing.tiktok-strategist"],
            {"price": 99, "currency": "ZAR", "period": "one-off", "season_target": 2970},
        ),
        mk(
            "opp-salon-booking", "WhatsApp Booking Agent for Salons & Spas",
            "SA salons lose bookings after hours; no-shows cost them ~20-30% of slots; manual DMs are slow.",
            "Independent salons, barbershops, spas",
            "Client DMs 'book me Sat 10am' -> FIRE checks availability, confirms, sends reminder + deposit link.",
            "R299/mo per salon",
            "Salon industry WhatsApp groups, distributor partnerships",
            "Shared calendar + manual confirmation first; reminder automation day 1.",
            {"pain": 8, "market_size": 7, "urgency": 6, "willingness_to_pay": 6,
             "competition": 6, "automation_potential": 9, "speed_to_mvp": 7,
             "distribution_difficulty": 6, "gross_margin": 8, "recurring_revenue": 9,
             "regulatory_risk": 8, "technical_complexity": 6, "customer_acquisition_cost": 6,
             "scalability": 7, "defensibility": 5},
            "3 salons pilot for a month; measure no-show rate change and booking lift.",
            ["no-shows not reduced", "salons won't pay monthly"],
            ["multi-location chains", "deposit collection becomes the moat"],
            ["engineering.rapid-prototyper", "engineering.voice-ai-integration-engineer",
             "sales.engineer", "marketing.social-media-strategist"],
            {"price": 299, "currency": "ZAR", "period": "month", "mrr_target_10": 2990},
        ),
        mk(
            "opp-content-repurpose", "Content Repurposing Pipeline",
            "Founders record one podcast/long video and have no time to clip it into 10 platform-native posts.",
            "SA founders & creators (and global via USD)",
            "Drop a long video -> FIRE outputs 10 clips, captions, hooks, and a 30-day posting calendar.",
            "$29/mo or R349/mo",
            "LinkedIn/TikTok content marketing; affiliate with podcasters",
            "Concierge: human clips top 5 moments using AI transcript timestamps.",
            {"pain": 7, "market_size": 8, "urgency": 6, "willingness_to_pay": 6,
             "competition": 5, "automation_potential": 8, "speed_to_mvp": 8,
             "distribution_difficulty": 5, "gross_margin": 8, "recurring_revenue": 9,
             "regulatory_risk": 8, "technical_complexity": 6, "customer_acquisition_cost": 5,
             "scalability": 8, "defensibility": 4},
            "10 creators trial; success = 5 publish the calendar and renew.",
            ["creators don't publish (no engagement)", "clip quality below their edit bar"],
            ["team plans for agencies", "white-label for video agencies"],
            ["marketing.short-video-editing-coach", "marketing.tiktok-strategist",
             "engineering.ai-engineer", "marketing.linkedin-content-creator"],
            {"price": 349, "currency": "ZAR", "period": "month", "mrr_target_10": 3490},
        ),
        mk(
            "opp-spaza-ledger", "Spaza Shop Stock & Credit Ledger",
            "Spaza shops run on memory and notebooks; stock vanishes, credit customers are never chased, margins are guesswork.",
            "Spaza shop owners in townships",
            "Simple WhatsApp/number-keypad ledger: log sales, track credit, get reorder alerts in plain language.",
            "R99/mo per shop",
            "FMCG distributors who already visit shops weekly",
            "SMS/USSD-style flow first (no smartphone app needed); distributor partner does onboarding.",
            {"pain": 9, "market_size": 7, "urgency": 6, "willingness_to_pay": 4,
             "competition": 7, "automation_potential": 8, "speed_to_mvp": 6,
             "distribution_difficulty": 4, "gross_margin": 7, "recurring_revenue": 8,
             "regulatory_risk": 6, "technical_complexity": 6, "customer_acquisition_cost": 4,
             "scalability": 8, "defensibility": 5},
            "Distributor pilot: 20 shops; measure repeat usage after 30 days.",
            ["<30% weekly active after 30 days", "owners prefer notebooks (no trust)"],
            ["distributor prepaid bundles", "credit-scoring data asset"],
            ["finance.bookkeeper-controller", "engineering.rapid-prototyper",
             "sales.outbound-strategist", "specialized.chief-of-staff"],
            {"price": 99, "currency": "ZAR", "period": "month", "mrr_target_20": 1980},
        ),
        mk(
            "opp-medical-reminders", "No-Show Reminder for Small Medical Practices",
            "Private GPs and dental practices lose revenue to no-shows; reminder staff time is expensive.",
            "Independent GP/dental practices in JHB",
            "FIRE sends appointment reminders + collects confirmations via WhatsApp/SMS, with waitlist fill.",
            "R249/mo per practice",
            "Medical suppliers, practice manager associations, direct demos",
            "CSV import -> automated reminder flow; success metric = no-show % delta.",
            {"pain": 7, "market_size": 6, "urgency": 6, "willingness_to_pay": 7,
             "competition": 6, "automation_potential": 8, "speed_to_mvp": 7,
             "distribution_difficulty": 5, "gross_margin": 8, "recurring_revenue": 9,
             "regulatory_risk": 4, "technical_complexity": 6, "customer_acquisition_cost": 5,
             "scalability": 7, "defensibility": 5},
            "2 practices for 6 weeks; measure no-show rate before/after.",
            ["no-show rate unchanged", "POPIA consent friction blocks rollout"],
            ["POPIA-compliant cloud for practices", "regional practice networks"],
            ["specialized.healthcare-customer-service", "engineering.email-intelligence-engineer",
             "sales.engineer", "marketing.seo-specialist"],
            {"price": 249, "currency": "ZAR", "period": "month", "mrr_target_5": 1245},
        ),
        mk(
            "opp-tutoring-caps", "CAPS-Aligned Study Material Generator",
            "SA learners can't afford tutors; parents want curriculum-aligned summaries for exams.",
            "SA high-school learners & parents (Grades 10-12)",
            "Pick subject + topic -> FIRE generates CAPS-aligned notes, practice questions and memos.",
            "R49 per pack; R149/mo all subjects",
            "Schools (paid licensing), parent WhatsApp groups, exam-season SEO",
            "Quality gate: human subject-matter review of the first 50 packs before any automated release.",
            {"pain": 7, "market_size": 8, "urgency": 8, "willingness_to_pay": 5,
             "competition": 5, "automation_potential": 8, "speed_to_mvp": 7,
             "distribution_difficulty": 6, "gross_margin": 9, "recurring_revenue": 7,
             "regulatory_risk": 7, "technical_complexity": 7, "customer_acquisition_cost": 6,
             "scalability": 8, "defensibility": 5},
            "Exam-season pilot (Oct); 100 packs; parent reviews on accuracy.",
            ["content errors in any reviewed pack", "parents prefer buying past papers"],
            ["school licences", "tutor marketplace attachment"],
            ["specialized.corporate-training-designer", "product.manager", "marketing.seo-specialist",
             "engineering.rapid-prototyper"],
            {"price": 149, "currency": "ZAR", "period": "month", "mrr_target_50": 7450},
        ),
        mk(
            "opp-proposal-freelancer", "Freelancer Proposal Generator (Gig Platforms)",
            "Freelancers lose gigs because proposals are generic; writing 5/day is exhausting.",
            "SA freelancers on Upwork/Fiverr/legit SA platforms",
            "Paste the job post -> FIRE drafts a tailored proposal + quote that references the client's exact wording.",
            "R59 per proposal; R199/mo unlimited",
            "Freelancer communities, gig-economy WhatsApp groups",
            "Paste -> tailored proposal; A/B two templates to measure reply rate.",
            {"pain": 7, "market_size": 7, "urgency": 7, "willingness_to_pay": 5,
             "competition": 6, "automation_potential": 9, "speed_to_mvp": 9,
             "distribution_difficulty": 6, "gross_margin": 9, "recurring_revenue": 7,
             "regulatory_risk": 9, "technical_complexity": 8, "customer_acquisition_cost": 6,
             "scalability": 7, "defensibility": 4},
            "50 freelancers; measure reply-rate lift vs their baseline template.",
            ["reply rate unchanged", "freelancers stop renewing after 1 month"],
            ["platform API integrations", "interview-prep upsell"],
            ["sales.proposal-strategist", "engineering.frontend-developer",
             "marketing.growth-hacker", "product.manager"],
            {"price": 199, "currency": "ZAR", "period": "month", "mrr_target_30": 5970},
        ),
        mk(
            "opp-google-maps-reviews", "Google Maps Review Engine for Local SA Business",
            "Local businesses (restaurants, salons, garages) rank low because they have 4 reviews; competitors have 50.",
            "Local SA SMBs already advertising on Google Maps",
            "FIRE automates the ask: post-visit WhatsApp/SMS link that makes leaving a review a 10-second tap, and responds to every review.",
            "R149/mo per location",
            "Google Business Profile agencies, local SEO workshops",
            "Manual: teach owner to send review link; automate follow-up reminders.",
            {"pain": 7, "market_size": 7, "urgency": 6, "willingness_to_pay": 6,
             "competition": 5, "automation_potential": 9, "speed_to_mvp": 8,
             "distribution_difficulty": 6, "gross_margin": 9, "recurring_revenue": 9,
             "regulatory_risk": 8, "technical_complexity": 8, "customer_acquisition_cost": 6,
             "scalability": 7, "defensibility": 5},
            "10 businesses; measure review-count growth in 30 days vs baseline.",
            ["<+5 reviews/month avg", "owners won't share customer contact lists"],
            ["multi-location chains", "reputation bundle with listings management"],
            ["marketing.seo-specialist", "marketing.social-media-strategist",
             "sales.outbound-strategist", "engineering.minimal-change-engineer"],
            {"price": 149, "currency": "ZAR", "period": "month", "mrr_target_20": 2980},
        ),
    ]


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run_hunt(include_origin: str | None = None,
             search: CapabilitySearch | None = None) -> list[Opportunity]:
    """Score + rank all opportunities (optionally refresh agent team refs)."""
    opps = [score_opportunity(o) for o in _seed_opportunities()]
    if search is not None:
        for opp in opps:
            resolved = []
            for aid in opp.required_agents:
                if search.get(aid):
                    resolved.append(aid)
            # if any required agent unresolved, drop from list
            opp.required_agents = resolved
    opps.sort(key=lambda o: o.weighted_score, reverse=True)
    return opps


def top_reasons(opp: Opportunity) -> list[str]:
    return opp.reasons


def save_hunt_report(opps: list[Opportunity], out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [o.to_dict() for o in opps]
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path
