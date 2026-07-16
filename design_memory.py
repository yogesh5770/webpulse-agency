import db
import site_store
import json
import logging

logger = logging.getLogger(__name__)

def get_recent_designs(limit: int = 20) -> list[dict]:
    """Retrieve Design DNA dicts of recent published sites from DB."""
    designs = []
    try:
        leads = [l for l in db.all_leads() if l.get("status") == "published"]
        # Sort by updated_at desc
        leads.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
        
        for l in leads[:limit]:
            pid = l.get("place_id")
            try:
                dna_str = site_store.read_file(pid, "design_dna.json")
                if dna_str:
                    designs.append(json.loads(dna_str))
            except Exception:
                # Handle cases where design_dna.json was not saved in older sites
                continue
    except Exception as e:
        logger.warning(f"Error loading design history from database: {e}")
    return designs

def is_too_similar(new_design: dict, history: list[dict] = None) -> bool:
    """Compare a new design blueprint against history for duplicate layouts."""
    if history is None:
        history = get_recent_designs(20)
    
    if not history:
        return False
        
    for past in history:
        # Check similarity score
        match_count = 0
        keys_to_compare = ["theme", "hero_component", "font_family", "animation_pack"]
        for k in keys_to_compare:
            if new_design.get(k) == past.get(k):
                match_count += 1
                
        # Compare section order
        if new_design.get("section_order") == past.get("section_order"):
            match_count += 1
            
        # If 4 or more visual aspects match, it's too similar
        if match_count >= 4:
            return True
            
    return False
