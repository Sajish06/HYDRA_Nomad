"""Typed and deterministic acceptance criteria catalog and test generator.

Catalog items for static web tasks:
1. file_exists
2. html_valid_structure (parses without errors, balanced basic tags)
3. html_has_tag (tag, min_count)
4. html_title_nonempty
5. html_text_contains (text)
6. html_form_has_labeled_inputs (inputs have matching label, wrapping label, or aria-label)
7. html_has_meta_viewport (<meta name="viewport" ...>)
8. html_no_external_resources (no http(s) src/href to third-party hosts)
9. css_present (<style> or <link rel="stylesheet">)
10. js_no_eval (no eval(...) or Function(...))
11. links_resolve_locally (relative <a> href targets exist in workspace)
12. no_sensitive_values (no vault sensitive token/value appears in workspace files)
13. manual_review (unmapped criteria, NEVER passes automated check)

Generated test code uses ONLY the standard library (html.parser, pathlib, urllib.parse).
"""

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from backend.config import settings
from backend.logging import logger

VALID_CATALOG_TYPES = {
    "file_exists",
    "html_valid_structure",
    "html_has_tag",
    "html_title_nonempty",
    "html_text_contains",
    "html_form_has_labeled_inputs",
    "html_has_meta_viewport",
    "html_no_external_resources",
    "css_present",
    "js_no_eval",
    "links_resolve_locally",
    "no_sensitive_values",
    "manual_review",
}


class Criterion(BaseModel):
    id: str
    catalog_type: str
    target_file: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)
    description: str

    def is_valid_catalog(self) -> bool:
        return self.catalog_type in VALID_CATALOG_TYPES


def normalize_criterion(raw: Dict[str, Any], index: int) -> Criterion:
    """Normalize any raw criterion dict into a typed Criterion. Unmapped -> manual_review."""
    cid = str(raw.get("id") or f"crit_{index:02d}")
    ctype = str(raw.get("catalog_type") or raw.get("criterion_type") or raw.get("type", "")).strip().lower()
    target = raw.get("target_file") or raw.get("file")
    desc = raw.get("description") or raw.get("desc") or ctype
    params = raw.get("params") or {}

    # Heuristic mapping if catalog_type was loose or free-text
    if ctype not in VALID_CATALOG_TYPES:
        desc_low = desc.lower()
        if "file" in desc_low and "exist" in desc_low:
            ctype = "file_exists"
        elif "title" in desc_low:
            ctype = "html_title_nonempty"
        elif "form" in desc_low and ("label" in desc_low or "input" in desc_low):
            ctype = "html_form_has_labeled_inputs"
        elif "viewport" in desc_low or "mobile" in desc_low:
            ctype = "html_has_meta_viewport"
        elif "no external" in desc_low or "cdn" in desc_low:
            ctype = "html_no_external_resources"
        elif "css" in desc_low or "style" in desc_low:
            ctype = "css_present"
        elif "eval" in desc_low:
            ctype = "js_no_eval"
        elif "link" in desc_low and "local" in desc_low:
            ctype = "links_resolve_locally"
        elif "sensitive" in desc_low or "leak" in desc_low:
            ctype = "no_sensitive_values"
        elif "tag" in desc_low or "header" in desc_low or "footer" in desc_low:
            ctype = "html_has_tag"
        elif "contain" in desc_low or "text" in desc_low:
            ctype = "html_text_contains"
        else:
            ctype = "manual_review"

    if ctype == "manual_review":
        logger.warning(f"[CriteriaCatalog] Unmapped criterion '{desc}' assigned to manual_review.")

    return Criterion(
        id=cid,
        catalog_type=ctype,
        target_file=target,
        params=params,
        description=desc,
    )


def generate_pytest_code(criteria: List[Criterion], meeting_id: str) -> str:
    """Generate deterministic pytest code for the criteria using Python standard library."""
    lines = [
        '"""',
        'AUTO-GENERATED ACCEPTANCE TESTS - MEETILY CLEAN ROOM / NOMAD',
        f'Meeting ID: {meeting_id}',
        'DO NOT EDIT: This judge file is managed and verified by Nomad.',
        'Uses standard library only (html.parser, pathlib, urllib.parse).',
        '"""',
        'import os',
        'import re',
        'from html.parser import HTMLParser',
        'from pathlib import Path',
        'from urllib.parse import urlparse',
        'import pytest',
        '',
        'WORKSPACE = Path(os.environ.get("NOMAD_WORKSPACE_DIR", ".")).resolve()',
        '',
        'class TagCollector(HTMLParser):',
        '    def __init__(self):',
        '        super().__init__()',
        '        self.tags = []',
        '        self.attrs_by_tag = {}',
        '        self.text_content = []',
        '        self.errors = []',
        '        self.forms = []',
        '        self.inputs = []',
        '        self.labels = []',
        '        self.title_text = ""',
        '        self.in_title = False',
        '        self.open_tags = []',
        '    def handle_starttag(self, tag, attrs):',
        '        self.tags.append(tag.lower())',
        '        ad = {k.lower(): v for k, v in attrs}',
        '        self.attrs_by_tag.setdefault(tag.lower(), []).append(ad)',
        '        if tag.lower() == "title":',
        '            self.in_title = True',
        '        elif tag.lower() == "form":',
        '            self.forms.append(ad)',
        '        elif tag.lower() == "input":',
        '            self.inputs.append(ad)',
        '        elif tag.lower() == "label":',
        '            self.labels.append(ad)',
        '    def handle_endtag(self, tag):',
        '        if tag.lower() == "title":',
        '            self.in_title = False',
        '    def handle_data(self, data):',
        '        if self.in_title:',
        '            self.title_text += data',
        '        self.text_content.append(data)',
        '',
        'def _parse_html(rel_path: str) -> TagCollector:',
        '    p = WORKSPACE / rel_path',
        '    assert p.exists(), f"File {rel_path} does not exist in workspace {WORKSPACE}"',
        '    content = p.read_text(encoding="utf-8", errors="replace")',
        '    parser = TagCollector()',
        '    parser.feed(content)',
        '    return parser',
        '',
    ]

    for i, c in enumerate(criteria, start=1):
        safe_name = f"test_{i:02d}_{c.catalog_type}_{c.id}".replace("-", "_")
        target = c.target_file or "index.html"
        lines.append(f"def {safe_name}():")
        lines.append(f'    """Criterion: {c.description}"""')

        if c.catalog_type == "file_exists":
            lines.append(f'    target = WORKSPACE / "{target}"')
            lines.append(f'    assert target.exists(), f"Expected deliverable \'{target}\' to exist in workspace."')
            lines.append(f'    assert target.is_file(), f"Target \'{target}\' is not a file."')

        elif c.catalog_type == "html_valid_structure":
            lines.append(f'    parser = _parse_html("{target}")')
            lines.append(f'    assert "html" in parser.tags, "Missing <html> tag in {target}"')
            lines.append(f'    assert "body" in parser.tags, "Missing <body> tag in {target}"')

        elif c.catalog_type == "html_has_tag":
            tag = c.params.get("tag", "h1").lower()
            min_c = c.params.get("min_count", 1)
            lines.append(f'    parser = _parse_html("{target}")')
            lines.append(f'    count = parser.tags.count("{tag}")')
            lines.append(f'    assert count >= {min_c}, f"Expected at least {min_c} <{tag}> tag(s) in {target}, found {{count}}"')

        elif c.catalog_type == "html_title_nonempty":
            lines.append(f'    parser = _parse_html("{target}")')
            lines.append(f'    assert parser.tags.count("title") > 0, "Missing <title> tag in {target}"')
            lines.append(f'    assert parser.title_text.strip(), "<title> tag is empty in {target}"')

        elif c.catalog_type == "html_text_contains":
            expected = c.params.get("text") or c.description
            escaped = expected.replace('"', '\\"').replace('\n', ' ')
            lines.append(f'    parser = _parse_html("{target}")')
            lines.append('    all_text = " ".join(parser.text_content).lower()')
            lines.append(f'    assert "{escaped.lower()}" in all_text, "Text \'{escaped}\' not found in {target}"')

        elif c.catalog_type == "html_form_has_labeled_inputs":
            lines.append(f'    parser = _parse_html("{target}")')
            lines.append(f'    assert len(parser.forms) > 0, "Expected at least one <form> in {target}"')
            lines.append(f'    assert len(parser.inputs) > 0, "Expected <input> elements in form in {target}"')
            lines.append('    # Check that non-submit inputs have associated label or aria-label')
            lines.append('    label_fors = {lbl.get("for") for lbl in parser.labels if lbl.get("for")}')
            lines.append('    unlabeled = []')
            lines.append('    for inp in parser.inputs:')
            lines.append('        itype = inp.get("type", "text").lower()')
            lines.append('        if itype in ("submit", "button", "hidden", "reset"):')
            lines.append('            continue')
            lines.append('        iid = inp.get("id")')
            lines.append('        aria = inp.get("aria-label") or inp.get("aria-labelledby")')
            lines.append('        if not aria and (not iid or iid not in label_fors):')
            lines.append('            unlabeled.append(inp.get("name") or iid or itype)')
            lines.append(f'    assert not unlabeled, f"Found unlabeled form input(s) in {target}: {{unlabeled}}"')

        elif c.catalog_type == "html_has_meta_viewport":
            lines.append(f'    parser = _parse_html("{target}")')
            lines.append('    metas = parser.attrs_by_tag.get("meta", [])')
            lines.append('    has_vp = any(m.get("name", "").lower() == "viewport" for m in metas)')
            lines.append(f'    assert has_vp, "Missing <meta name=\'viewport\'> tag in {target}"')

        elif c.catalog_type == "html_no_external_resources":
            lines.append(f'    parser = _parse_html("{target}")')
            lines.append('    external_links = []')
            lines.append('    for tag in ("script", "link", "img", "iframe", "audio", "video"):')
            lines.append('        for attr_dict in parser.attrs_by_tag.get(tag, []):')
            lines.append('            url = attr_dict.get("src") or attr_dict.get("href") or ""')
            lines.append('            if url.startswith("//") or url.lower().startswith("http://") or url.lower().startswith("https://"):')
            lines.append('                parsed = urlparse(url)')
            lines.append('                if parsed.netloc and parsed.netloc not in ("localhost", "127.0.0.1"):')
            lines.append('                    external_links.append(f"{tag}:{url}")')
            lines.append(f'    assert not external_links, f"External third-party resource(s) found in {target}: {{external_links}}"')

        elif c.catalog_type == "css_present":
            lines.append(f'    parser = _parse_html("{target}")')
            lines.append('    has_style = len(parser.attrs_by_tag.get("style", [])) > 0 or "style" in parser.tags')
            lines.append('    has_link_css = any(l.get("rel", "").lower() == "stylesheet" for l in parser.attrs_by_tag.get("link", []))')
            lines.append(f'    assert has_style or has_link_css, "No stylesheet or <style> block found in {target}"')

        elif c.catalog_type == "js_no_eval":
            lines.append(f'    p = WORKSPACE / "{target}"')
            lines.append('    content = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""')
            lines.append(f'    assert not re.search(r"\\beval\\s*\\(", content), "eval() usage detected in {target}"')
            lines.append(f'    assert not re.search(r"new\\s+Function\\s*\\(", content), "Function constructor detected in {target}"')

        elif c.catalog_type == "links_resolve_locally":
            lines.append(f'    parser = _parse_html("{target}")')
            lines.append('    missing_targets = []')
            lines.append('    for a in parser.attrs_by_tag.get("a", []):')
            lines.append('        href = a.get("href", "")')
            lines.append('        if href and not href.startswith(("#", "mailto:", "tel:", "javascript:")):')
            lines.append('            parsed = urlparse(href)')
            lines.append('            if not parsed.netloc and not parsed.scheme:')
            lines.append('                dest = (WORKSPACE / parsed.path).resolve()')
            lines.append('                if not dest.exists():')
            lines.append('                    missing_targets.append(href)')
            lines.append(f'    assert not missing_targets, f"Broken local links in {target}: {{missing_targets}}"')

        elif c.catalog_type == "no_sensitive_values":
            forbidden = json.dumps(c.params.get("forbidden_values", []))
            lines.append(f'    forbidden_list = {forbidden}')
            lines.append('    leaked = []')
            lines.append('    for p in WORKSPACE.rglob("*"):')
            lines.append('        if p.is_file() and p.suffix in (".html", ".css", ".js", ".json", ".txt", ".md"):')
            lines.append('            if "tests_nomad" in p.parts:')
            lines.append('                continue')
            lines.append('            text = p.read_text(encoding="utf-8", errors="replace")')
            lines.append('            for f in forbidden_list:')
            lines.append('                if f and len(f) >= 4 and f in text:')
            lines.append('                    leaked.append(f"{p.name}:{f}")')
            lines.append('    assert not leaked, f"Sensitive unmasked value(s) found in workspace files: {leaked}"')

        elif c.catalog_type == "manual_review":
            lines.append('    # Criteria flagged as manual_review NEVER pass automated execution')
            lines.append(f'    pytest.fail("Manual review required by human operator: {c.description}")')

        lines.append("")

    return "\n".join(lines)


def save_acceptance_tests(meeting_id: str, criteria: List[Criterion]) -> Tuple[Path, str]:
    """
    Save generated pytest code in Nomad data directory (outside workspace).
    Returns (path_to_test_file, sha256_hash).
    """
    out_dir = Path(settings.DATA_DIR) / "acceptance_tests" / meeting_id
    out_dir.mkdir(parents=True, exist_ok=True)
    test_file = out_dir / "test_acceptance.py"

    code = generate_pytest_code(criteria, meeting_id)
    clean_bytes = code.replace("\r\n", "\n").encode("utf-8")
    test_file.write_bytes(clean_bytes)

    code_hash = hashlib.sha256(clean_bytes).hexdigest()
    logger.info(f"[CriteriaCatalog] Saved acceptance tests for meeting {meeting_id} ({len(criteria)} tests), hash={code_hash[:12]}")
    return test_file, code_hash
