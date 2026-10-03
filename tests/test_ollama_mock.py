"""Fake HTTP server test suite for Ollama prompt compiler integration.

Covers:
1. Success: /api/tags returns models, /api/chat returns valid structured JSON.
2. Malformed JSON: /api/chat returns invalid JSON; compiler retries and falls back to deterministic template.
3. Timeout: /api/chat exceeds socket timeout; compiler falls back.
4. Model missing: requested model not in /api/tags; compiler chooses available or falls back.
5. Connection refused: port closed/invalid; compiler cleanly falls back without crashing.
"""

import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional
import pytest

from backend.loop.criteria_catalog import Criterion
from backend.loop.prompt_compiler import PromptCompiler, StructuredPrompt
from backend.loop.task_selector import BuildTask
from backend.processors.privacy import Vault


class MockOllamaHandler(BaseHTTPRequestHandler):
    mode = "success"  # success, malformed, timeout, missing_model

    def log_message(self, format, *args):
        # Silence HTTP server logs to keep test output clean
        pass

    def do_GET(self):
        if self.path == "/api/tags":
            if self.mode == "missing_model":
                data = {"models": [{"name": "unrelated_model:latest"}]}
            else:
                data = {"models": [{"name": "qwen2.5:7b"}, {"name": "test_model:latest"}]}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/api/chat":
            if self.mode == "timeout":
                time.sleep(4.0)  # Exceeds compiler timeout
                return

            if self.mode == "malformed":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"message": {"content": "not json at all {{"}}')
                return

            # Default: valid JSON matching StructuredPrompt schema
            sample_content = {
                "objective": "Build static HTML pages for verified meeting intelligence",
                "context": "Executive diligence review session",
                "requirements": ["Landing Page: Build index.html", "Contact Form: Build contact.html"],
                "constraints": ["No third-party CDN", "Standard HTML5"],
                "deliverables": ["index.html", "contact.html"],
                "acceptance_criteria": ["index.html exists", "contact.html exists"],
                "out_of_scope": ["Backend database", "External payments"],
            }
            resp_body = {
                "model": "qwen2.5:7b",
                "message": {"role": "assistant", "content": json.dumps(sample_content)},
                "done": True,
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(resp_body).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()


@pytest.fixture
def mock_ollama_server():
    server = HTTPServer(("127.0.0.1", 0), MockOllamaHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield f"http://127.0.0.1:{port}", MockOllamaHandler

    server.shutdown()
    server.server_close()


def test_ollama_success(mock_ollama_server):
    base_url, handler = mock_ollama_server
    handler.mode = "success"

    v = Vault()
    compiler = PromptCompiler(base_url=base_url, model="qwen2.5:7b", enable_ollama=True, vault=v)
    task = BuildTask(task_id="t1", title="Landing Page", description="Build index.html", deliverables=["index.html"])
    crit = Criterion(id="c1", catalog_type="file_exists", target_file="index.html", description="index.html exists")

    prompt = compiler.compile("mtg1", [task], [crit], "C:/test/workspace", iteration=1)
    assert prompt.source == "ollama"
    assert "index.html" in prompt.deliverables
    assert prompt.iteration == 1


def test_ollama_malformed_json_triggers_fallback(mock_ollama_server):
    base_url, handler = mock_ollama_server
    handler.mode = "malformed"

    v = Vault()
    compiler = PromptCompiler(base_url=base_url, model="qwen2.5:7b", enable_ollama=True, vault=v)
    task = BuildTask(task_id="t1", title="Landing Page", description="Build index.html", deliverables=["index.html"])
    crit = Criterion(id="c1", catalog_type="file_exists", target_file="index.html", description="index.html exists")

    prompt = compiler.compile("mtg1", [task], [crit], "C:/test/workspace", iteration=1)
    assert prompt.source == "fallback"
    assert "index.html" in prompt.deliverables


def test_ollama_timeout_triggers_fallback(mock_ollama_server):
    base_url, handler = mock_ollama_server
    handler.mode = "timeout"

    v = Vault()
    compiler = PromptCompiler(base_url=base_url, model="qwen2.5:7b", enable_ollama=True, vault=v)
    task = BuildTask(task_id="t1", title="Landing Page", description="Build index.html", deliverables=["index.html"])
    crit = Criterion(id="c1", catalog_type="file_exists", target_file="index.html", description="index.html exists")

    prompt = compiler.compile("mtg1", [task], [crit], "C:/test/workspace", iteration=1)
    assert prompt.source == "fallback"


def test_ollama_model_missing_uses_available(mock_ollama_server):
    base_url, handler = mock_ollama_server
    handler.mode = "missing_model"

    v = Vault()
    # Requesting non_existent_model, but server has unrelated_model:latest
    compiler = PromptCompiler(base_url=base_url, model="non_existent_model:latest", enable_ollama=True, vault=v)
    task = BuildTask(task_id="t1", title="Landing Page", description="Build index.html", deliverables=["index.html"])
    crit = Criterion(id="c1", catalog_type="file_exists", target_file="index.html", description="index.html exists")

    prompt = compiler.compile("mtg1", [task], [crit], "C:/test/workspace", iteration=1)
    # Compiler successfully chose the available model from /api/tags
    assert prompt.source == "ollama"


def test_ollama_connection_refused_falls_back():
    v = Vault()
    # Point to closed port
    closed_port = 59999
    compiler = PromptCompiler(base_url=f"http://127.0.0.1:{closed_port}", enable_ollama=True, vault=v)
    task = BuildTask(task_id="t1", title="Landing Page", description="Build index.html", deliverables=["index.html"])
    crit = Criterion(id="c1", catalog_type="file_exists", target_file="index.html", description="index.html exists")

    prompt = compiler.compile("mtg1", [task], [crit], "C:/test/workspace", iteration=1)
    assert prompt.source == "fallback"
