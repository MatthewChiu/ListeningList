import os
import glob
import json
import re
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
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )
    return json.loads(response.text)

def check_off_piece(composer_name, piece_title):
    """Finds a piece in a composer file and marks [ ] as [x]."""
    for filepath in glob.glob(f"{COMPOSERS_DIR}/*.md"):
        if composer_name.lower() in os.path.basename(filepath).lower():
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Replace unchecked with checked for target title
            pattern = re.compile(rf'(-\s+\[\s\]\s+.*{re.escape(piece_title)}.*)', re.IGNORECASE)
            updated_content = pattern.sub(lambda m: m.group(1).replace('- [ ]', '- [x]'), content)
            
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

if __name__ == "__main__":
    action = os.environ.get("AGENT_ACTION", "recommend")
    user_query = os.environ.get("USER_QUERY", None)
    
    if action == "mark_listened":
        composer = os.environ.get("COMPOSER_NAME", "")
        title = os.environ.get("PIECE_TITLE", "")
        check_off_piece(composer, title)
    else:
        rec = generate_recommendation(user_query)
        update_dashboard(rec)