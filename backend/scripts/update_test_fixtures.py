import os
import sys
import json
import re

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from scripts.update_policies_phase1 import EXPANDED_POLICIES

def update_fixtures():
    fixtures_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures.py"))
    with open(fixtures_path, "r", encoding="utf-8") as f:
        fixtures_text = f.read()

    # Find where TROUBLESHOOTING PLAYBOOKS start
    ts_marker = "# ── TS-001  General Method"
    ts_idx = fixtures_text.find(ts_marker)
    if ts_idx == -1:
        print("ERROR: Could not find TS-001 marker in fixtures.py")
        return

    pre_ts = fixtures_text[:ts_idx]
    post_ts = fixtures_text[ts_idx:]

    header_end = pre_ts.find("INITIAL_ARTICLES = [")
    if header_end == -1:
        print("ERROR: Could not find INITIAL_ARTICLES in fixtures.py")
        return

    header_text = pre_ts[:header_end] + "INITIAL_ARTICLES = [\n"

    new_articles = []
    for title, pdata in EXPANDED_POLICIES.items():
        code = title.split(" ")[0]
        # format content as python multi-line raw string or triple-quoted string
        content_repr = json.dumps(pdata["content"].strip())
        tags_repr = json.dumps(pdata["tags"])
        art_code = f"""    # ── {title} ─────────────────────────
    {{
        "title": {json.dumps(title)},
        "content": {content_repr},
        "category": {json.dumps(pdata["category"])},
        "tags": {tags_repr},
        "is_active": True,
        "tenant_id": "default"
    }},
"""
        new_articles.append(art_code)

    new_fixtures_text = header_text + "\n".join(new_articles) + "\n    " + post_ts
    with open(fixtures_path, "w", encoding="utf-8") as f:
        f.write(new_fixtures_text)

    print(f"Updated {fixtures_path} successfully.")

if __name__ == "__main__":
    update_fixtures()

