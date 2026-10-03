"""
AUTO-GENERATED ACCEPTANCE TESTS - MEETILY CLEAN ROOM / NOMAD
Meeting ID: mtg_eval_test
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
    """Criterion: exists"""
    target = WORKSPACE / "index.html"
    assert target.exists(), f"Expected deliverable 'index.html' to exist in workspace."
    assert target.is_file(), f"Target 'index.html' is not a file."
