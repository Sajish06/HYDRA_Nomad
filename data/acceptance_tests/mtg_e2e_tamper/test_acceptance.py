"""
AUTO-GENERATED ACCEPTANCE TESTS - MEETILY CLEAN ROOM / NOMAD
Meeting ID: mtg_e2e_tamper
DO NOT EDIT: This judge file is managed and verified by Nomad.
Uses standard library only (html.parser, pathlib, urllib.parse).
"""
import os
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
import pytest

WORKSPACE = Path(os.environ.get("NOMAD_WORKSPACE_DIR", ".")).resolve()

class TagCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.attrs_by_tag = {}
        self.text_content = []
        self.errors = []
        self.forms = []
        self.inputs = []
        self.labels = []
        self.title_text = ""
        self.in_title = False
        self.open_tags = []
    def handle_starttag(self, tag, attrs):
        self.tags.append(tag.lower())
        ad = {k.lower(): v for k, v in attrs}
        self.attrs_by_tag.setdefault(tag.lower(), []).append(ad)
        if tag.lower() == "title":
            self.in_title = True
        elif tag.lower() == "form":
            self.forms.append(ad)
        elif tag.lower() == "input":
            self.inputs.append(ad)
        elif tag.lower() == "label":
            self.labels.append(ad)
    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self.in_title = False
    def handle_data(self, data):
        if self.in_title:
            self.title_text += data
        self.text_content.append(data)

def _parse_html(rel_path: str) -> TagCollector:
    p = WORKSPACE / rel_path
    assert p.exists(), f"File {rel_path} does not exist in workspace {WORKSPACE}"
    content = p.read_text(encoding="utf-8", errors="replace")
    parser = TagCollector()
    parser.feed(content)
    return parser

def test_01_file_exists_crit_01():
    """Criterion: Deliverable index.html must exist"""
    target = WORKSPACE / "index.html"
    assert target.exists(), f"Expected deliverable 'index.html' to exist in workspace."
    assert target.is_file(), f"Target 'index.html' is not a file."

def test_02_html_valid_structure_crit_02():
    """Criterion: index.html must have valid HTML structure"""
    parser = _parse_html("index.html")
    assert "html" in parser.tags, "Missing <html> tag in index.html"
    assert "body" in parser.tags, "Missing <body> tag in index.html"

def test_03_html_title_nonempty_crit_03():
    """Criterion: index.html must have a non-empty <title>"""
    parser = _parse_html("index.html")
    assert parser.tags.count("title") > 0, "Missing <title> tag in index.html"
    assert parser.title_text.strip(), "<title> tag is empty in index.html"

def test_04_html_no_external_resources_crit_04():
    """Criterion: index.html must have no external resources"""
    parser = _parse_html("index.html")
    external_links = []
    for tag in ("script", "link", "img", "iframe", "audio", "video"):
        for attr_dict in parser.attrs_by_tag.get(tag, []):
            url = attr_dict.get("src") or attr_dict.get("href") or ""
            if url.startswith("//") or url.lower().startswith("http://") or url.lower().startswith("https://"):
                parsed = urlparse(url)
                if parsed.netloc and parsed.netloc not in ("localhost", "127.0.0.1"):
                    external_links.append(f"{tag}:{url}")
    assert not external_links, f"External third-party resource(s) found in index.html: {external_links}"

def test_05_file_exists_crit_05():
    """Criterion: Deliverable contact.html must exist"""
    target = WORKSPACE / "contact.html"
    assert target.exists(), f"Expected deliverable 'contact.html' to exist in workspace."
    assert target.is_file(), f"Target 'contact.html' is not a file."

def test_06_html_valid_structure_crit_06():
    """Criterion: contact.html must have valid HTML structure"""
    parser = _parse_html("contact.html")
    assert "html" in parser.tags, "Missing <html> tag in contact.html"
    assert "body" in parser.tags, "Missing <body> tag in contact.html"

def test_07_html_title_nonempty_crit_07():
    """Criterion: contact.html must have a non-empty <title>"""
    parser = _parse_html("contact.html")
    assert parser.tags.count("title") > 0, "Missing <title> tag in contact.html"
    assert parser.title_text.strip(), "<title> tag is empty in contact.html"

def test_08_html_no_external_resources_crit_08():
    """Criterion: contact.html must have no external resources"""
    parser = _parse_html("contact.html")
    external_links = []
    for tag in ("script", "link", "img", "iframe", "audio", "video"):
        for attr_dict in parser.attrs_by_tag.get(tag, []):
            url = attr_dict.get("src") or attr_dict.get("href") or ""
            if url.startswith("//") or url.lower().startswith("http://") or url.lower().startswith("https://"):
                parsed = urlparse(url)
                if parsed.netloc and parsed.netloc not in ("localhost", "127.0.0.1"):
                    external_links.append(f"{tag}:{url}")
    assert not external_links, f"External third-party resource(s) found in contact.html: {external_links}"

def test_09_html_form_has_labeled_inputs_crit_09():
    """Criterion: contact.html form must have labeled inputs"""
    parser = _parse_html("contact.html")
    assert len(parser.forms) > 0, "Expected at least one <form> in contact.html"
    assert len(parser.inputs) > 0, "Expected <input> elements in form in contact.html"
    # Check that non-submit inputs have associated label or aria-label
    label_fors = {lbl.get("for") for lbl in parser.labels if lbl.get("for")}
    unlabeled = []
    for inp in parser.inputs:
        itype = inp.get("type", "text").lower()
        if itype in ("submit", "button", "hidden", "reset"):
            continue
        iid = inp.get("id")
        aria = inp.get("aria-label") or inp.get("aria-labelledby")
        if not aria and (not iid or iid not in label_fors):
            unlabeled.append(inp.get("name") or iid or itype)
    assert not unlabeled, f"Found unlabeled form input(s) in contact.html: {unlabeled}"

def test_10_no_sensitive_values_crit_10():
    """Criterion: No unmasked sensitive values from vault in workspace files"""
    forbidden_list = ["Sarah Chen", "Zephyrine Quillfeather", "Northwind Analytics", "Priya Sharma", "David Vance", "Marcus Brody"]
    leaked = []
    for p in WORKSPACE.rglob("*"):
        if p.is_file() and p.suffix in (".html", ".css", ".js", ".json", ".txt", ".md"):
            if "tests_nomad" in p.parts:
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
            for f in forbidden_list:
                if f and len(f) >= 4 and f in text:
                    leaked.append(f"{p.name}:{f}")
    assert not leaked, f"Sensitive unmasked value(s) found in workspace files: {leaked}"
