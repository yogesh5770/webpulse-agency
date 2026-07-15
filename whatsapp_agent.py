"""WhatsApp Customer Reply & Autonomous Update Agent.

This module acts when a customer replies to the WhatsApp outreach message.
It:
1. Loads the client's current website files and memory.json.
2. Formulates a rich prompt (Prompt Builder) containing system instructions,
   business profile, current memory, existing HTML code, and customer request.
3. Invokes the specialized Update Agent to modify the files.
4. Redeploys the updated website to the same Cloudflare Pages URL.
5. Saves a conversation log and drafts a WhatsApp response back to the customer.
"""
import json
import logging
from agent_router import chat_text
import site_store
import db
from deploy import deploy

logger = logging.getLogger(__name__)


def _strip_fences(text: str) -> str:
    import re
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```$", "", text)
    return text.strip()


def handle_customer_reply(place_id: str, message_text: str) -> str:
    """Process a customer's WhatsApp request, update the site, redeploy,
    and return the agent's message reply for the customer."""
    lead = db.get_lead(place_id)
    if not lead:
        return "ERROR: Lead not found."

    # Load existing site files from DB
    try:
        html_content = site_store.read_file(place_id, "index.html")
    except FileNotFoundError:
        return "ERROR: Site files do not exist."

    try:
        memory_raw = site_store.read_file(place_id, "memory.json")
        memory = json.loads(memory_raw)
    except Exception:
        memory = {
            "businessName": lead.get("name"),
            "industry": lead.get("category", "business"),
            "theme": "modern",
            "colors": [],
            "fonts": [],
            "deployment": "Cloudflare Pages",
            "liveUrl": lead.get("live_url", ""),
            "framework": "HTML5 / Vanilla JS",
            "lastVersion": 1,
            "features": []
        }

    # Increment site version
    memory["lastVersion"] = memory.get("lastVersion", 1) + 1

    # --- Prompt Builder ---
    system_instruction = (
        "You are the elite Update Agent of our AI Website Agency.\n"
        "Your role is to autonomously interpret a customer's request to modify their website, "
        "apply those changes surgically, update their configuration memory, and explain the changes.\n"
        "You must output a JSON object containing:\n"
        "1. updated_html: The complete, updated, valid HTML document.\n"
        "2. updated_memory: The updated memory dict (adjust theme, colors, fonts, or features if requested).\n"
        "3. reply_message: A friendly, brief WhatsApp message explaining that the changes are live.\n\n"
        "Rules:\n"
        "- Do not make breaking structural changes unless asked.\n"
        "- Maintain modern premium aesthetics, responsiveness, and accessibility.\n"
        "- The output must be valid JSON. Return ONLY raw JSON, no explanations or markdown fences."
    )

    prompt = (
        "### Client Website Data\n"
        f"Business Name: {lead.get('name')}\n"
        f"Category: {lead.get('category')}\n"
        f"Phone: {lead.get('phone')}\n"
        f"Address: {lead.get('address')}\n\n"
        "### Current Memory Config\n"
        f"{json.dumps(memory, indent=2)}\n\n"
        "### Customer Request\n"
        f"\"{message_text}\"\n\n"
        "### Existing index.html Content\n"
        f"{html_content}\n\n"
        "Generate the updated JSON containing updated_html, updated_memory, and reply_message."
    )

    try:
        response_raw = _strip_fences(
            chat_text(
                [
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=16000
            )
        )
        response = json.loads(response_raw)
        updated_html = response["updated_html"]
        updated_memory = response["updated_memory"]
        reply_message = response["reply_message"]
    except Exception as e:
        logger.error(f"Failed to parse update agent response: {e}")
        # Fallback if parsing fails or LLM outputs invalid format
        return f"I had trouble applying the changes automatically. Could you try rephrasing your request? (Error: {e})"

    if "<html" not in updated_html.lower():
        return "Failed to compile the new website correctly. No changes were applied."

    # Save changes to DB
    site_store.write_file(place_id, "index.html", updated_html)
    site_store.write_file(place_id, "memory.json", json.dumps(updated_memory, indent=2, ensure_ascii=False))

    # Trigger redeployment to the same URL
    try:
        workdir = site_store.materialize(place_id)
        live_url = deploy(workdir, name_hint=lead.get("name", ""), stable_key=place_id)
        # Update the liveUrl in memory too
        updated_memory["liveUrl"] = live_url
        site_store.write_file(place_id, "memory.json", json.dumps(updated_memory, indent=2, ensure_ascii=False))

        # Append to message log/history in lead
        conversation_history = lead.get("message", "") + f"\n\nCustomer: {message_text}\nAgency: {reply_message}"
        db.update_lead(place_id, live_url=live_url, message=conversation_history, status="published")

        # Send real message
        if lead.get("phone"):
            from outreach import send_whatsapp_message
            send_whatsapp_message(lead["phone"], reply_message)
    except Exception as e:
        logger.error(f"Redeploy/Send failed: {e}")
        return f"We applied your changes, but encountered an error during deployment. Please try again shortly!"

    return reply_message
