"""Certus inference server. Runs on the GPU machine, serves certificate generation.

Loads the model once, then serves HTTP requests. No external deps beyond
what's already installed for training (transformers, peft, torch).

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
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from peft import PeftModel
    import torch

    print(f"Loading model from {model_path}...")
    quant_config = BitsAndBytesConfig(
        load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16
    )
    base = AutoModelForCausalLM.from_pretrained(
        "Qwen/Qwen2.5-Coder-7B-Instruct",
        quantization_config=quant_config,
        device_map="auto",
    )
    MODEL = PeftModel.from_pretrained(base, model_path)
    TOKENIZER = AutoTokenizer.from_pretrained(model_path)
    MODEL.config.use_cache = True
    print("Model loaded. Ready to serve.")


def generate_certificate(code, max_tokens=512):
    import torch

    prompt = f"Generate a Certus certificate for this function:\n\n{code}"
    messages = [{"role": "user", "content": prompt}]
    text = TOKENIZER.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = TOKENIZER(text, return_tensors="pt").to(MODEL.device)

    with torch.no_grad():
        outputs = MODEL.generate(
            **inputs,
            max_new_tokens=max_tokens,
            temperature=0.1,
            top_p=0.95,
            do_sample=True,
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
