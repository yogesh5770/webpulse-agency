"""Free-form builder orchestrator: design → build → elevate → critique → improve.

This is the "work like a design studio" path. Instead of filling a template:
  1. ai_web_designer writes a bespoke design brief + design tokens for THIS business.
  2. ai_web_builder hand-codes the full single-file website from the brief.
  3. visual_editor runs ONE elevation pass: takes the good build and makes it
     exceptional (hero, spacing, motion, mobile, conversion), staying on-token.
  4. ai_website_critic scores the real HTML and names weak sections.
  5. ai_web_builder revises ONLY the weak sections; re-critique; repeat.
  6. Keep the best-scoring version; stop once it clears the quality bar.

Also emits a DESIGN.md-style reasoning doc so the system documents WHY it made
each decision, like an accountable design team.

Returns (html, artifacts) where artifacts holds the brief, reasoning, final
critique, and score history for storage/inspection.
"""
import logging

from ai_web_designer import design_brief
from ai_web_builder import build_site, revise_sections
from ai_website_critic import critique, PUBLISH_THRESHOLD
from visual_editor import elevate
from design_reasoning import build_reasoning
import diversity_engine
import design_intelligence
import quality_gates
import self_review

logger = logging.getLogger(__name__)

# Token economy: 2 revision rounds is the sweet spot — the first pass fixes
# almost everything the critic finds; a third round rarely moves the score
# enough to justify resending the whole document again.
MAX_ROUNDS = 2


def build(business: dict, avoid_hint: str = "", elevate_pass: bool = True,
          recent_designs: list | None = None, learn: bool = True) -> tuple[str, dict]:
    """Run the full free-form pipeline for one business.

    elevate_pass: run the Visual Editor elevation pass after the build. On by
    default; callers can disable it to save tokens on a quick draft.
    recent_designs: fingerprints of recently built sites. The Diversity Engine
    uses them to steer this design away from repeating recent choices. When not
    provided, we pull them from the Design Intelligence store automatically.
    learn: read a soft learned prior from Design Intelligence and record this
    site back into it. Diversity always wins over the prior.
    """
    industry = business.get("category", "")
    # If the caller didn't supply recent designs, pull them from memory so both
    # diversity and learning work out of the box.
    if recent_designs is None and learn:
        recent_designs = design_intelligence.recent_fingerprints(industry)

    # Stage 0 — steer BEFORE designing: a soft learned prior (what has scored
    # well) AND a diversity push (don't repeat recent work). Diversity is placed
    # LAST so it has the final word — a prior is a hint, never a law.
    parts = [avoid_hint]
    if learn:
        parts.append(design_intelligence.prior_hint(industry))
    if recent_designs:
        parts.append(diversity_engine.divergence_hint(recent_designs, industry))
    hint = " ".join(p for p in parts if p).strip()

    # Stage 1 — design
    brief = design_brief(business, avoid_hint=hint)
    logger.info("Design brief ready: %s", brief.get("art_direction", "")[:120])

    # Stage 2 — build
    html = build_site(brief, business)

    # Stage 3 — elevation pass (good -> exceptional, one coherent on-token pass)
    if elevate_pass:
        html = elevate(html, brief, business)

    # Stage 3.5 — deterministic quality gates run BEFORE the critic, so the
    # LLM critic reasons about subjective quality on top of objective facts
    # instead of being the only judge.
    tokens = brief.get("design_tokens")
    gates = quality_gates.run_gates(html, tokens=tokens, recent=recent_designs, brief=brief)
    logger.info("Quality gates: health=%s deployable=%s", gates.get("overall_health"), gates["deployable"])

    # Stage 4 — critique (fed the objective gate summary)
    review = critique(html, brief, None, gate_summary=gates["summary"])
    best_html, best_review = html, review
    history = [review.get("overall_score", 0)]
    logger.info("Critic round 0: overall=%s", review.get("overall_score"))

    # Early exit: if the elevated build already clears the bar, we're done.
    if review.get("overall_score", 0) >= PUBLISH_THRESHOLD and not review.get("weak_sections"):
        logger.info("Build cleared the bar; skipping revision.")


    # Stage 5 — targeted improvement loop. Trigger when the subjective score is
    # low OR when a critical gate failed (a broken/inaccessible/non-mobile site
    # must not ship regardless of how pretty the critic finds it).
    round_no = 0
    while ((review.get("overall_score", 0) < PUBLISH_THRESHOLD or gates["critical_failed"])
           and (review.get("weak_sections") or gates["critical_failed"])
           and round_no < MAX_ROUNDS):
        round_no += 1
        # Send the affected sections back, plus any critical gate issues, so the
        # revision fixes real defects, not just aesthetics. Gate issues are
        # shaped like the critic's weak_sections so revise_sections can consume
        # both uniformly.
        targets = list(review.get("weak_sections") or [])
        for gname in gates["critical_failed"]:
            issues = gates["gates"][gname]["issues"]
            targets.append({
                "section": "global",
                "problem": f"{gname} gate failed: " + "; ".join(issues),
                "fix": f"Fix these objective {gname} defects so the gate passes.",
            })
        html = revise_sections(html, brief, business, targets)
        gates = quality_gates.run_gates(html, tokens=tokens, recent=recent_designs)
        review = critique(html, brief, None, gate_summary=gates["summary"])
        history.append(review.get("overall_score", 0))
        logger.info("Critic round %s: overall=%s health=%s", round_no,
                    review.get("overall_score"), gates.get("overall_health"))
        if review.get("overall_score", 0) > best_review.get("overall_score", 0):
            best_html, best_review = html, review
        if review.get("overall_score", 0) >= PUBLISH_THRESHOLD and not gates["critical_failed"]:
            break

    too_similar, sim_score = diversity_engine.is_too_similar(
        brief.get("design_tokens"), recent_designs or [])
    # Deploy rule: any critical gate failure blocks deploy, regardless of the
    # subjective score. Otherwise, publish-ready needs the score AND the gates.
    deployable = gates["deployable"] and best_review.get("overall_score", 0) >= PUBLISH_THRESHOLD

    # Stage 6 — SELF_REVIEW: an honest reflection grounded in the gate results
    # and critic verdict, capturing the *why* behind the build for storage.
    self_review_data = self_review.generate(brief, gates, best_review)

    artifacts = {
        "brief": brief,
        "design_tokens": brief.get("design_tokens"),
        "reasoning": build_reasoning(brief, business),
        "review": best_review,
        "score_history": history,
        "final_score": best_review.get("overall_score", 0),
        "quality_gates": {
            "health": gates["health"],
            "overall_health": gates.get("overall_health"),
            "critical_failed": gates["critical_failed"],
            "summary": gates["summary"],
            "quality_budget": gates.get("quality_budget")
        },
        "self_review": self_review_data,
        "deployable": deployable,
        "published_ready": deployable,
        "diversity": {"too_similar": too_similar, "max_similarity": sim_score},
    }

    # Learn: record this finished site so future builds get smarter. Signal is
    # the critic today; swap to real analytics when available (see module doc).
    if learn:
        design_intelligence.record(business, brief, artifacts, signal_source="critic")

    return best_html, artifacts
