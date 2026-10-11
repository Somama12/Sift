"""Read-only checks for optional local components."""

from __future__ import annotations

import http.client
import importlib.util
import json
import platform
import shutil


def diagnose() -> dict:
    pdf_text = importlib.util.find_spec("pypdf") is not None
    image_ocr = shutil.which("tesseract") is not None
    pdf_renderer = shutil.which("pdftoppm") is not None
    result = {
        "python": platform.python_version(),
        "pdf_text": pdf_text,
        "image_ocr": image_ocr,
        "scanned_pdf_ocr": pdf_text and image_ocr and pdf_renderer,
        "ollama_server": False,
        "ollama_model": False,
    }
    connection = http.client.HTTPConnection("127.0.0.1", 11434, timeout=2)
    try:
        connection.request("GET", "/api/tags")
        response = connection.getresponse()
        if response.status == 200:
            models = json.loads(response.read(256_000))["models"]
            result["ollama_server"] = True
            if isinstance(models, list):
                result["ollama_model"] = any(isinstance(model, dict) and model.get("name") == "qwen3:4b-instruct" for model in models)
    except (OSError, ValueError, KeyError, TypeError, http.client.HTTPException):
        pass
    finally:
        connection.close()
    return result
