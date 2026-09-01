import os
import glob
import json
import re
import requests
from datetime import datetime
from google import genai
from google.genai import types

# Fetch API key safely
api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
client = genai.Client(api_key=api_key)

DOCS_DIR = "docs"
COMPOSERS_DIR = os.path.join(DOCS_DIR, "composers")


def get_all_pieces():
    """Scans all composer markdown files for checked and unchecked pieces."""
    pieces = {"checked": [], "unchecked": []}

    for filepath in glob.glob(f"{COMPOSERS_DIR}/*.md"):
        composer = os.path.basename(filepath).replace(".md", "").replace("_", " ")
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                match = re.search(r'-\s+\[([ xX])\]\s+(.+)', line)
                if match:
                    is_checked = match.group(1).lower() == 'x'
                    title = match.group(2).strip()
                    item = {"composer": composer, "title": title, "filepath": filepath}
                    if is_checked:
                        pieces["checked"].append(item)
                    else:
                        pieces["unchecked"].append(item)
    return pieces


def generate_recommendation(prompt_override=None):
    pieces = get_all_pieces()

    if prompt_override:
        prompt = f"""
        User request: "{prompt_override}"
        Unchecked pieces available in collection: {json.dumps(pieces['unchecked'])}
        Checked pieces: {json.dumps(pieces['checked'])}

        Select or suggest ONE classical piece matching the user request.
        Return ONLY JSON matching this format:
        {{
          "composer": "Composer Name",
          "title": "Piece Title",
          "why": "2 sentences explaining why to listen to this work today and what movement/feature to pay attention to.",
          "movement": "Recommended movement (optional)"
        }}
        """
    else:
        prompt = f"""
        Act as a master classical music curator. Select ONE piece from the unchecked list below.
        Unchecked options: {json.dumps(pieces['unchecked'])}

        If unchecked list is sparse, you may suggest a new piece from classical repertoire.
        Return ONLY JSON matching this format:
        {{
          "composer": "Composer Name",
          "title": "Piece Title",
          "why": "2 sentences explaining why to listen to this work today.",
          "movement": "Recommended movement (optional)"
        }}
        """

    response = client.models.generate_content(
        model='gemini-3.6-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )
    return json.loads(response.text)


def parse_listening_request(prompt_text):
    """Uses the model to turn a free-text request into a composer + piece title."""
    pieces = get_all_pieces()
    existing_composers = sorted(set(p["composer"] for p in pieces["checked"] + pieces["unchecked"]))

    prompt = f"""
    The user wants to add a new piece to their classical listening list.
    Their request: "{prompt_text}"

    Existing composer pages in their collection: {json.dumps(existing_composers)}
    (Reuse an existing composer name exactly if it matches, otherwise use the standard
    English spelling of the composer's name.)

    Identify the composer and the specific piece (with catalog/opus number if applicable).
    Return ONLY JSON matching this format:
    {{
      "composer": "Composer Name",
      "title": "Piece Title, Op. XX"
    }}
    """

    response = client.models.generate_content(
        model='gemini-3.6-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )
    return json.loads(response.text)


def _composer_filepath(composer_name):
    """Finds an existing composer file case-insensitively, else builds a new path."""
    for filepath in glob.glob(f"{COMPOSERS_DIR}/*.md"):
        if composer_name.lower() == os.path.basename(filepath).replace(".md", "").replace("_", " ").lower():
            return filepath
    safe_name = re.sub(r'\s+', '_', composer_name.strip())
    return os.path.join(COMPOSERS_DIR, f"{safe_name}.md")


def add_listening(prompt_text):
    """Parses a free-text request into a piece and appends it (unchecked) to the
    right composer file, creating the file and linking it from index.md if new."""
    parsed = parse_listening_request(prompt_text)
    composer = parsed["composer"]
    title = parsed["title"]

    os.makedirs(COMPOSERS_DIR, exist_ok=True)
    filepath = _composer_filepath(composer)
    is_new_file = not os.path.exists(filepath)

    if is_new_file:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"# {composer} Listenings\n\n## Works\n- [ ] {title}\n")
    else:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        if title.lower() in content.lower():
            parsed["already_existed"] = True
            return parsed
        if not content.endswith("\n"):
            content += "\n"
        content += f"- [ ] {title}\n"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

    if is_new_file:
        index_path = os.path.join(DOCS_DIR, "index.md")
        if os.path.exists(index_path):
            with open(index_path, "r", encoding="utf-8") as f:
                index_content = f.read()
            link_line = f"- [{composer} Page](./composers/{os.path.basename(filepath)})\n"
            if link_line not in index_content:
                # Insert after the first line that already links to a composer page,
                # or right after the title if none exist yet.
                lines = index_content.splitlines(keepends=True)
                insert_at = 1
                for i, line in enumerate(lines):
                    if line.strip().startswith("- [") and "Page](" in line:
                        insert_at = i + 1
                lines.insert(insert_at, link_line)
                with open(index_path, "w", encoding="utf-8") as f:
                    f.writelines(lines)

    parsed["already_existed"] = False
    parsed["is_new_composer"] = is_new_file
    return parsed


def check_off_piece(composer_name, piece_title):
    """Finds a piece in a composer file and marks [ ] as [x], appending today's date."""
    today = datetime.now().strftime("%-m/%-d/%y")
    for filepath in glob.glob(f"{COMPOSERS_DIR}/*.md"):
        if composer_name.lower() in os.path.basename(filepath).lower():
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            pattern = re.compile(rf'(-\s+\[\s\]\s+.*{re.escape(piece_title)}.*)', re.IGNORECASE)
            if not pattern.search(content):
                continue

            def _mark(m):
                return m.group(1).replace('- [ ]', '- [x]') + f"\n    {today}"

            updated_content = pattern.sub(_mark, content, count=1)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(updated_content)
            return True
    return False


def update_dashboard(rec):
    """Updates index.md and history.md."""
    today = datetime.now().strftime("%Y-%m-%d")

    # 1. Append to history.md
    history_entry = f"\n### {today} — {rec['composer']}: {rec['title']}\n"
    history_entry += f"- **Insight:** {rec['why']}\n"
    if rec.get("movement"):
        history_entry += f"- **Key Movement:** {rec['movement']}\n"

    history_path = os.path.join(DOCS_DIR, "history.md")
    with open(history_path, "a", encoding="utf-8") as f:
        f.write(history_entry)

    # 2. Update home index.md block
    index_path = os.path.join(DOCS_DIR, "index.md")
    with open(index_path, "r", encoding="utf-8") as f:
        content = f.read()

    new_block = f"### 🌟 Latest Recommendation ({today})\n"
    new_block += f"**{rec['composer']}** — *{rec['title']}*\n\n"
    new_block += f"> {rec['why']}\n"

    if "### 🌟 Latest Recommendation" in content:
        content = re.sub(r'### 🌟 Latest Recommendation.*', new_block, content, flags=re.DOTALL)
    else:
        content += f"\n\n{new_block}"

    with open(index_path, "w", encoding="utf-8") as f:
        f.write(content)


def notify_discord(message):
    """Sends the result back to Discord. Prefers editing the original deferred
    interaction reply (for slash commands); falls back to a plain incoming
    webhook (for the unattended daily cron post); else just prints."""
    app_id = os.environ.get("DISCORD_APPLICATION_ID")
    interaction_token = os.environ.get("DISCORD_INTERACTION_TOKEN")
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")

    try:
        if app_id and interaction_token:
            url = f"https://discord.com/api/v10/webhooks/{app_id}/{interaction_token}/messages/@original"
            resp = requests.patch(url, json={"content": message}, timeout=10)
            resp.raise_for_status()
        elif webhook_url:
            resp = requests.post(webhook_url, json={"content": message}, timeout=10)
            resp.raise_for_status()
        else:
            print(message)
    except requests.RequestException as e:
        print(f"Failed to notify Discord: {e}")
        print(message)


if __name__ == "__main__":
    action = os.environ.get("AGENT_ACTION", "recommend")
    user_query = os.environ.get("USER_QUERY", "").strip()

    try:
        if action == "recommend":
            rec = generate_recommendation(user_query or None)
            update_dashboard(rec)
            msg = f"🎼 **{rec['composer']} — {rec['title']}**"
            if rec.get("movement"):
                msg += f"\n*Movement:* {rec['movement']}"
            msg += f"\n\n{rec['why']}"
            notify_discord(msg)

        elif action == "add":
            if not user_query:
                notify_discord("⚠️ Tell me what piece to add, e.g. `/add Rachmaninoff's 2nd piano concerto`.")
            else:
                parsed = add_listening(user_query)
                if parsed.get("already_existed"):
                    msg = f"**{parsed['title']}** by **{parsed['composer']}** is already on your list."
                else:
                    msg = f"➕ Added **{parsed['title']}** by **{parsed['composer']}** to your listening list."
                    if parsed.get("is_new_composer"):
                        msg += " (new composer page created)"
                notify_discord(msg)

        elif action == "checkoff":
            composer = os.environ.get("COMPOSER_NAME", "").strip()
            title = os.environ.get("PIECE_TITLE", "").strip()
            if not composer or not title:
                notify_discord("⚠️ Need both a composer and a title to check something off.")
            else:
                success = check_off_piece(composer, title)
                if success:
                    notify_discord(f"✅ Marked **{title}** ({composer}) as listened.")
                else:
                    notify_discord(f"Couldn't find an unchecked **{title}** under **{composer}** — check the spelling?")
        else:
            notify_discord(f"⚠️ Unknown action: {action}")

    except Exception as e:
        notify_discord(f"⚠️ Something went wrong: {e}")
        raise
