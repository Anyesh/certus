"""Tests for the certificate generator module."""

import json
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

import pytest

from certus.generator import (
    extract_functions,
    call_inference_server,
    generate_for_function,
    GenerateResult,
)


# --- extract_functions ---


def test_extract_single_function():
    source = "def add(a, b):\n    return a + b\n"
    funcs = extract_functions(source)
    assert len(funcs) == 1
    assert funcs[0][0] == "add"
    assert "return a + b" in funcs[0][1]


def test_extract_multiple_functions():
    source = "def foo():\n    pass\n\ndef bar():\n    pass\n"
    funcs = extract_functions(source)
    assert len(funcs) == 2
    assert funcs[0][0] == "foo"
    assert funcs[1][0] == "bar"


def test_extract_no_functions():
    source = "x = 1\ny = 2\n"
    funcs = extract_functions(source)
    assert len(funcs) == 0


def test_extract_skips_class_methods():
    source = "class Foo:\n    def method(self):\n        pass\n\ndef top():\n    pass\n"
    funcs = extract_functions(source)
    assert len(funcs) == 1
    assert funcs[0][0] == "top"


def test_extract_syntax_error():
    funcs = extract_functions("def broken(:\n")
    assert len(funcs) == 0


# --- Mock inference server ---


class MockHandler(BaseHTTPRequestHandler):
    response_cert = '@certus(\n    preconditions=[],\n    postconditions=[{"when": "always", "guarantees": ["result == a + b"]}],\n)'

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        resp = {"certificate": self.response_cert, "error": None}
        self.wfile.write(json.dumps(resp).encode())

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def mock_server():
    server = HTTPServer(("127.0.0.1", 0), MockHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


# --- call_inference_server ---


def test_call_inference_server(mock_server):
    result = call_inference_server("def add(a, b): return a + b", mock_server)
    assert result is not None
    assert "@certus" in result


def test_call_inference_server_bad_url():
    result = call_inference_server("def f(): pass", "http://127.0.0.1:1")
    assert result is None


# --- generate_for_function ---


def test_generate_for_function_valid(mock_server):
    source = "def add(a, b):\n    return a + b\n"
    result = generate_for_function(
        "add", source, source, mock_server, checker_mode="structural"
    )
    assert result.parsed is True
    assert result.certificate_kwargs is not None
    assert result.validation is not None
    assert result.validation.passed is True


def test_generate_for_function_server_down():
    source = "def f(): pass\n"
    result = generate_for_function("f", source, source, "http://127.0.0.1:1")
    assert result.error is not None
    assert "no result" in result.error.lower()
