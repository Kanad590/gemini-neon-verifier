#!/usr/bin/env python3
"""
Gemini 4 Neon Payload Builder & Zero-Touch Extraction Engine
Autonomous pre-processor for gemini-neon-verifier.
Converts any file (PDF, TXT, Code, Image OCR, JSON) into full-fidelity raw text payload,
staged for zero-touch prompt injection into Gemini 4 Neon web app.
"""

import sys
import os
import subprocess
import mimetypes
from pathlib import Path

# Known binary extensions to explicitly reject rather than reading corrupted UTF-8
BINARY_EXTENSIONS = {
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".exe", ".bin", ".iso", ".img", ".dmg", ".pkg", ".deb", ".rpm",
    ".so", ".dll", ".dylib", ".class", ".jar", ".war", ".ear",
    ".apk", ".aab", ".ipa", ".pyc", ".pyo", ".pyd",
    ".mp3", ".wav", ".ogg", ".flac", ".mp4", ".mkv", ".avi", ".mov"
}

def extract_content(file_path: str) -> str:
    path = Path(file_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    ext = path.suffix.lower()

    if ext in BINARY_EXTENSIONS:
        raise ValueError(
            f"Binary file type '{ext}' cannot be processed directly for text prompt injection. "
            f"Please extract or convert '{path.name}' before running the verifier."
        )

    # 1. Plain text / code / config / json
    if ext in [".txt", ".json", ".md", ".csv", ".tsv", ".py", ".sh", ".yaml", ".yml", ".sql", ".conf", ".log"]:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

    # 2. PDF Document
    if ext == ".pdf":
        extracted_text = ""
        try:
            res = subprocess.run(
                ["pdftotext", "-layout", str(path), "-"],
                capture_output=True,
                text=True,
                check=True,
                timeout=30
            )
            if res.stdout.strip():
                extracted_text = res.stdout
        except Exception:
            pass

        # Fallback to pymupdf / fitz if pdftotext didn't yield text
        if not extracted_text.strip():
            try:
                import fitz
                doc = fitz.open(str(path))
                pages = []
                for page in doc:
                    pages.append(page.get_text("text"))
                extracted_text = "\n\n--- PAGE BREAK ---\n\n".join(pages)
            except Exception:
                pass

        if len(extracted_text.strip()) < 50:
            warning_msg = (
                f"[SCANNED_PDF_WARNING: Extracted text contains {len(extracted_text.strip())} characters. "
                f"The document '{path.name}' appears to be a scanned image or raster PDF without a digital text layer. "
                f"OCR processing is recommended.]\n\n"
            )
            return warning_msg + extracted_text
        return extracted_text

    # 3. Image OCR (PNG, JPG, JPEG, WEBP)
    if ext in [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"]:
        try:
            res = subprocess.run(
                ["tesseract", str(path), "stdout", "-l", "eng+ben", "--psm", "6"],
                capture_output=True,
                text=True,
                check=True,
                timeout=30
            )
            text = res.stdout.strip()
            if text:
                return f"=== EXTRACTED OCR TEXT FROM IMAGE ({path.name}) ===\n\n{text}"
            else:
                return f"=== IMAGE {path.name} (OCR produced 0 characters; purely visual or low contrast) ==="
        except subprocess.TimeoutExpired:
            return f"=== IMAGE {path.name} OCR TIMEOUT (exceeded 30 seconds) ==="
        except Exception as e:
            return f"=== IMAGE {path.name} OCR ERROR: {e} ==="

    # Default fallback to UTF-8 text read
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as e:
        raise RuntimeError(f"Unsupported file format for text extraction: {ext} ({e})")

def build_neon_prompt(file_path: str, user_instruction: str, output_path: str = None) -> str:
    content = extract_content(file_path)
    file_name = Path(file_path).name

    # Try loading template if available
    ref_template_path = Path(__file__).resolve().parent.parent / "references" / "gemini_neon_prompt.txt"
    if ref_template_path.exists():
        try:
            with open(ref_template_path, "r", encoding="utf-8") as rf:
                template = rf.read()
            prompt = template.format(file_name=file_name, user_instruction=user_instruction, content=content)
        except Exception:
            prompt = _fallback_prompt(file_name, user_instruction, content)
    else:
        prompt = _fallback_prompt(file_name, user_instruction, content)

    if output_path:
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "w", encoding="utf-8") as f:
            f.write(prompt)
        print(f"[neon_payload_builder] Staged {len(prompt)} characters to: {output_path}")

    return prompt

def _fallback_prompt(file_name: str, user_instruction: str, content: str) -> str:
    return f"""# 🛡️ Gemini 4 Neon Forensic Verification & Audit Request

## 📋 Context & Source File
- **Source File:** `{file_name}`
- **Task Objective:** {user_instruction}

---

## 🔍 Mandatory 4-Lens Diagnostic Audit Framework
Please perform a rigorous, anti-sycophantic, zero-compromise analysis through the following 4 lenses:
1. **Lens 1: Structural Traps & Blindspots:** Identify hidden pitfalls, calculation speed-traps, or deceptive assumptions.
2. **Lens 2: Time-Decay & Tripwires:** Detail critical milestones, expiration deadlines, transit windows, or cutoff thresholds.
3. **Lens 3: Contrarian Ground-Truth:** Challenge conventional crowd beliefs with hard logical, mathematical, or gazette facts.
4. **Lens 4: Actionable Protocol:** Provide a clear, step-by-step checklist of immediate do's and don'ts.

---

## 📄 Raw Source Data (Verbatim Full Text)
<source_payload filename="{file_name}">
{content}
</source_payload>
"""

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: neon_payload_builder.py <file_path> <instruction> [output_staged_path]")
        sys.exit(1)

    fpath = sys.argv[1]
    instr = sys.argv[2]
    out = sys.argv[3] if len(sys.argv) > 3 else None

    build_neon_prompt(fpath, instr, out)
