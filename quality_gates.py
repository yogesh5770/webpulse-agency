"""Deterministic Quality Gates — objective, measurable checks that run BEFORE
the Critic, so the LLM critic reasons about subjective quality (emotion,
hierarchy, storytelling, brand) on top of hard facts instead of being the only
judge.

HONESTY BOUNDARY (this matters): some checks are only truthful in a real
browser (rendered contrast, actual layout overflow, computed LCP/CLS). This
sandbox has no browser, so those are marked `requires_browser` and report what
the HTML/CSS *declares*, never a fabricated rendered number. When Playwright is
wired in a networked env, those slots fill with real measurements. Every score
this module returns today is one it actually computed from the static markup.

Each gate returns a dict: {name, passed, score(0-100 or None), critical(bool),
issues:[...], requires_browser(bool)}. `run_all` aggregates into a Website
Health Score and a deploy decision.
"""
from __future__ import annotations

import re
import logging

from bs4 import BeautifulSoup

import design_tokens
import diversity_engine

logger = logging.getLogger(__name__)


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html or "", "html.parser")


def _styles(soup: BeautifulSoup) -> str:
    """Concatenate all inline <style> CSS (our sites are single-file)."""
    return "\n".join(s.get_text() for s in soup.find_all("style"))


def _gate(name, passed, issues, score=None, critical=False, requires_browser=False, note=""):
    return {"name": name, "passed": bool(passed), "score": score,
            "critical": critical, "issues": issues,
            "requires_browser": requires_browser, "note": note}


def html_gate(html: str, soup: BeautifulSoup) -> dict:
    """Structural validity: doctype, single <title>, viewport, favicon,
    duplicate IDs, empty anchors. Critical — a broken document must not ship."""
    issues = []
    if "<!doctype html" not in html.lower():
        issues.append("missing <!DOCTYPE html>")
    if not soup.find("html"):
        issues.append("missing <html> element")
    if len(soup.find_all("title")) != 1:
        issues.append("must have exactly one <title>")
    if not soup.find("meta", attrs={"name": "viewport"}):
        issues.append("missing viewport meta (breaks mobile)")
    if not soup.find("link", rel=lambda v: v and "icon" in " ".join(v if isinstance(v, list) else [v]).lower()):
        issues.append("missing favicon link")
    # Duplicate IDs
    ids = [el.get("id") for el in soup.find_all(id=True)]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        issues.append(f"duplicate id(s): {', '.join(sorted(dupes))}")
    # Empty/broken anchors
    empty_links = [a for a in soup.find_all("a") if not a.get("href") or a.get("href").strip() in ("", "#")]
    if empty_links:
        issues.append(f"{len(empty_links)} anchor(s) with empty/# href")
    score = max(0, 100 - 20 * len(issues))
    return _gate("HTML", not issues, issues, score=score, critical=True)


def seo_gate(html: str, soup: BeautifulSoup) -> dict:
    """SEO essentials — all statically checkable. Scored, non-critical."""
    issues = []
    checks = 0
    passed = 0
    def chk(cond, msg):
        nonlocal checks, passed
        checks += 1
        if cond: passed += 1
        else: issues.append(msg)
    title = soup.find("title")
    chk(title and 10 <= len(title.get_text(strip=True)) <= 65, "title missing or not 10-65 chars")
    desc = soup.find("meta", attrs={"name": "description"})
    chk(desc and 50 <= len(desc.get("content", "")) <= 165, "meta description missing or not 50-165 chars")
    chk(soup.find("link", rel=lambda v: v and "canonical" in (v if isinstance(v, str) else " ".join(v))), "missing canonical link")
    chk(soup.find("meta", attrs={"property": re.compile("^og:")}), "missing Open Graph tags")
    chk(bool(re.search(r'application/ld\+json', html, re.I)), "missing JSON-LD structured data")
    h1s = soup.find_all("h1")
    chk(len(h1s) == 1, f"should have exactly one <h1> (found {len(h1s)})")
    chk(soup.find("html").get("lang") if soup.find("html") else False, "missing <html lang>")
    score = round(100 * passed / checks) if checks else 0
    return _gate("SEO", not issues, issues, score=score)


def _heading_order_ok(soup: BeautifulSoup) -> bool:
    levels = [int(h.name[1]) for h in soup.find_all(re.compile("^h[1-6]$"))]
    prev = 0
    for lv in levels:
        if prev and lv > prev + 1:
            return False
        prev = lv
    return True


def accessibility_gate(html: str, soup: BeautifulSoup) -> dict:
    """Static a11y checks. Rendered contrast + keyboard focus need a browser and
    are reported separately as requires_browser (not faked)."""
    issues = []
    imgs = soup.find_all("img")
    no_alt = [i for i in imgs if i.get("alt") is None]
    if no_alt:
        issues.append(f"{len(no_alt)} <img> without alt attribute")
    inputs = soup.find_all(["input", "select", "textarea"])
    unlabeled = [i for i in inputs if not (i.get("aria-label") or i.get("id") and soup.find("label", attrs={"for": i.get("id")}))]
    if unlabeled:
        issues.append(f"{len(unlabeled)} form field(s) without a label/aria-label")
    if not _heading_order_ok(soup):
        issues.append("heading hierarchy skips levels")
    bad_aria = [t.name for t in soup.find_all(attrs={"role": ""})]
    if bad_aria:
        issues.append("empty role attribute present")
    # scored on the static checks
    total = 4
    fails = len(issues)
    score = max(0, round(100 * (total - fails) / total))
    g = _gate("Accessibility", not issues, issues, score=score)
    g["browser_note"] = "rendered color contrast and keyboard focus order require a browser (not measured here)"
    return g


def performance_gate(html: str, soup: BeautifulSoup) -> dict:
    """Static performance signals. Real LCP/CLS need a browser (reported separately)."""
    issues = []
    imgs = soup.find_all("img")
    not_lazy = [i for i in imgs if i.get("loading") != "lazy" and i is not (imgs[0] if imgs else None)]
    if len(not_lazy) > 1:
        issues.append(f"{len(not_lazy)} below-fold <img> not lazy-loaded")
    scripts = soup.find_all("script", src=True)
    blocking = [s for s in scripts if not (s.get("defer") or s.get("async") or s.get("type") == "module")]
    if blocking:
        issues.append(f"{len(blocking)} render-blocking <script> (add defer/async)")
    kb = len(html.encode("utf-8")) / 1024
    if kb > 250:
        issues.append(f"HTML document is {kb:.0f}KB (>250KB); consider trimming")
    fonts = re.findall(r'fonts\.googleapis\.com', html)
    if fonts and "preconnect" not in html:
        issues.append("Google Fonts used without <link rel=preconnect>")
    score = max(40, 100 - 15 * len(issues))
    g = _gate("Performance", len(issues) <= 1, issues, score=score)
    g["browser_note"] = "LCP, CLS, and total transfer size require a browser/Lighthouse (not measured here)"
    return g


# Motion durations we consider tasteful (ms). Matches build_constraints.
_MOTION_MIN, _MOTION_MAX = 100, 800


def motion_gate(html: str, soup: BeautifulSoup) -> dict:
    """Deterministic motion rules — far better than asking an LLM 'are animations good?'."""
    issues = []
    css = " ".join(s.get_text() for s in soup.find_all("style"))
    has_anim = ("transition" in css) or ("@keyframes" in css) or ("animation" in css)
    if has_anim and "prefers-reduced-motion" not in css:
        issues.append("animations present but no prefers-reduced-motion fallback")
    # durations
    durs = [float(m) * (1000 if m2 == "s" else 1)
            for m, m2 in re.findall(r'(\d*\.?\d+)(m?s)', css)]
    out_of_range = [d for d in durs if d and (d < _MOTION_MIN or d > _MOTION_MAX)]
    if out_of_range:
        issues.append(f"{len(out_of_range)} animation duration(s) outside {_MOTION_MIN}-{_MOTION_MAX}ms")
    # layout-thrashing props in transitions/animations
    if re.search(r'transition\s*:[^;]*\b(width|height|top|left|margin)\b', css):
        issues.append("transition animates layout properties (use transform/opacity for GPU)")
    score = max(50, 100 - 15 * len(issues))
    return _gate("Motion", not issues, issues, score=score)


def design_system_gate(html: str, soup: BeautifulSoup, tokens: dict | None) -> dict:
    """Enforce the design tokens: the site's CSS must not drift off-system.
    This is what makes the constraints we set actually binding, not advisory."""
    if not tokens:
        return _gate("DesignSystem", True, [], score=100, note="no tokens provided; skipped")
    issues = []
    css = " ".join(s.get_text() for s in soup.find_all("style"))
    # radius drift: count distinct border-radius pixel values; a system should be small
    radii = set(re.findall(r'border-radius\s*:\s*(\d+)px', css))
    if len(radii) > 4:
        issues.append(f"{len(radii)} distinct border-radius values (visual drift; consolidate to the token scale)")
    # font families: at most 2 (heading + body) per constraints
    fams = set(re.findall(r"font-family\s*:\s*'([^',;]+)'", css))
    if len(fams) > 3:
        issues.append(f"{len(fams)} font families used (max 2 per design system)")
    # spacing: flag many odd (non-8px-grid) paddings as drift
    pads = [int(x) for x in re.findall(r'padding[^:]*:\s*(\d+)px', css)]
    off_grid = [p for p in pads if p and p % 4 != 0]
    if len(off_grid) > 5:
        issues.append(f"{len(off_grid)} paddings off the 4/8px spacing grid")
    score = max(50, 100 - 15 * len(issues))
    return _gate("DesignSystem", not issues, issues, score=score)


def mobile_gate(html: str, soup: BeautifulSoup) -> dict:
    """Static mobile checks. Real overflow/tap-target rendering needs a browser."""
    issues = []
    vp = soup.find("meta", attrs={"name": "viewport"})
    if not (vp and "width=device-width" in vp.get("content", "")):
        issues.append("missing responsive viewport meta")
    # fixed pixel widths wider than a phone are a red flag
    css = " ".join(s.get_text() for s in soup.find_all("style"))
    # match `width:NNNpx` but NOT `max-width`/`min-width` (those are breakpoints)
    wide = [int(w) for w in re.findall(r'(?<![-\w])width\s*:\s*(\d{3,})px', css) if int(w) > 480]
    if wide:
        issues.append(f"{len(wide)} fixed width(s) >480px (risk horizontal scroll on mobile)")
    has_mq = "@media" in css
    if not has_mq:
        issues.append("no @media queries (layout may not adapt to mobile)")
    score = max(40, 100 - 20 * len(issues))
    g = _gate("Mobile", not issues, issues, score=score)
    g["browser_note"] = "actual horizontal-scroll and rendered tap-target size require a browser (not measured here)"
    return g


def diversity_gate(tokens: dict | None, recent: list | None, brief: dict | None = None) -> dict:
    """Wrap the Diversity Engine as a gate. Too-similar is a soft-critical fail."""
    try:
        import diversity_engine
        too_similar, sim = diversity_engine.is_too_similar(tokens, recent or [], new_brief=brief)
        score = int(round((1 - sim) * 100))
        return _gate("Diversity", not too_similar,
                     [f"{int(sim*100)}% similar to a recent design"] if too_similar else [],
                     score=score)
    except Exception as e:
        return _gate("Diversity", True, [], score=100, note=f"skipped: {e}")


# Which gates block deployment outright vs. only lower the health score.
_CRITICAL = {"HTML", "Accessibility", "Mobile"}


def run_gates(html: str, tokens: dict | None = None, recent: list | None = None, brief: dict | None = None) -> dict:
    """Run every deterministic gate and return a Website Health Score.

    The Critic runs AFTER this and receives the summary, so its subjective
    judgment sits on top of objective facts instead of standing alone.
    """
    if not html or len(html) < 200:
        return {"deployable": False, "critical_failed": ["HTML"],
                "health": {}, "gates": {"HTML": _gate("HTML", False, ["empty/short document"], 0)},
                "summary": "HTML: FAIL (empty document)"}

    soup = BeautifulSoup(html, "html.parser")
    gates = {
        "HTML": html_gate(html, soup),
        "SEO": seo_gate(html, soup),
        "Accessibility": accessibility_gate(html, soup),
        "Performance": performance_gate(html, soup),
        "Motion": motion_gate(html, soup),
        "DesignSystem": design_system_gate(html, soup, tokens),
        "Mobile": mobile_gate(html, soup),
        "Diversity": diversity_gate(tokens, recent, brief=brief),
    }
    # Only average gates that produced a real numeric score. A gate with
    # score=None is browser-dependent (couldn't be measured statically) and
    # must not be counted as a zero — that would fabricate a bad number.
    health = {name: g["score"] for name, g in gates.items() if g["score"] is not None}
    critical_failed = [n for n in _CRITICAL if not gates[n]["passed"]]
    # one-line context string for the Critic
    summary = " | ".join(
        f"{n}: {'PASS' if g['passed'] else 'FAIL'} ({g['score']})"
        for n, g in gates.items()
    )
    
    budget = check_quality_budget(gates)
    
    return {
        "deployable": not critical_failed and budget["passed"],
        "critical_failed": critical_failed,
        "health": health,
        "overall_health": round(sum(health.values()) / len(health)) if health else None,
        "gates": gates,
        "summary": summary,
        "quality_budget": budget
    }


def check_quality_budget(gates: dict) -> dict:
    """Evaluate site quality against the target categories budget (total 100)."""
    vis = round((gates.get("DesignSystem", {}).get("score", 100) or 100) * 0.25)
    ux = round((gates.get("Motion", {}).get("score", 100) or 100) * 0.20)
    perf = round((gates.get("Performance", {}).get("score", 100) or 100) * 0.15)
    a11y = round((gates.get("Accessibility", {}).get("score", 100) or 100) * 0.15)
    seo = round((gates.get("SEO", {}).get("score", 100) or 100) * 0.15)
    orig = round((gates.get("Diversity", {}).get("score", 100) or 100) * 0.10)
    
    total = vis + ux + perf + a11y + seo + orig
    
    # Budget threshold: overall total score >= 85, no major failures
    passed = (
        total >= 85
        and vis >= 18
        and ux >= 14
        and perf >= 10
        and a11y >= 10
        and seo >= 10
    )
    
    return {
        "passed": passed,
        "total_score": total,
        "breakdown": {
            "visual_quality": vis,
            "ux": ux,
            "performance": perf,
            "accessibility": a11y,
            "seo": seo,
            "originality": orig
        }
    }
