"""Certus inference server. Runs on the GPU machine, serves certificate generation.

Uses Unsloth for optimized loading and patched attention layers.

Usage:
    python serve_certus.py --model MODEL_PATH [--port 8234]

API:
    POST /generate  {"code": "def foo(): ..."}
    Response:       {"certificate": "@certus(...)", "error": null}
"""

import argparse
import json
from http.server import HTTPServer, BaseHTTPRequestHandler

MODEL = None
TOKENIZER = None


def load_model(model_path):
    global MODEL, TOKENIZER
    import torch
    from unsloth import FastLanguageModel

    print(f"Loading model from {model_path}...")
    MODEL, TOKENIZER = FastLanguageModel.from_pretrained(
        model_name=model_path,
        max_seq_length=2048,
        dtype=None,
        load_in_4bit=True,
    )
    MODEL.config.use_cache = True
    torch.set_grad_enabled(False)
    print("Model loaded. Ready to serve.")


def generate_certificate(code, max_tokens=512):
    import torch

    prompt = f"Generate a Certus certificate for this function:\n\n{code}"
    messages = [{"role": "user", "content": prompt}]
    text = TOKENIZER.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = TOKENIZER(text, return_tensors="pt").to(MODEL.device)

    outputs = MODEL.generate(
        **inputs,
        max_new_tokens=max_tokens,
        temperature=0.1,
        top_p=0.95,
        do_sample=True,
        use_cache=True,
    )

    return TOKENIZER.decode(
        outputs[0][inputs["input_ids"].shape[-1] :], skip_special_tokens=True
    )


class CertusHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/generate":
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        try:
            req = json.loads(body)
            code = req["code"]
        except (json.JSONDecodeError, KeyError):
            self.send_error(400, "Expected JSON with 'code' field")
            return

        try:
            cert = generate_certificate(code, max_tokens=req.get("max_tokens", 512))
            response = {"certificate": cert, "error": None}
        except Exception as e:
            response = {"certificate": None, "error": str(e)}

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())

    def log_message(self, format, *args):
        print(f"[serve] {args[0]}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--port", type=int, default=8234)
    args = parser.parse_args()

    load_model(args.model)

    server = HTTPServer(("0.0.0.0", args.port), CertusHandler)
    print(f"Serving on http://0.0.0.0:{args.port}")
    print('POST /generate {"code": "..."} to generate certificates')
    server.serve_forever()


if __name__ == "__main__":
    main()
