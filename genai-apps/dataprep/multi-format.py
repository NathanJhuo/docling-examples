#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# ---------- 0) 環境變數：白名單只允許 tesseract ----------
import os
os.environ.setdefault("DOCLING_OCR_ENGINE", "tesseract")
os.environ.setdefault("DOCLING_OCR_ENGINES", "tesseract")
os.environ.setdefault("DOCLING_DISABLE_OCR_ENGINES", "easyocr,rapidocr,ocrmac")

# ---------- 1) 防呆：釘掉 easyocr / rapidocr / ocrmac ----------
import sys, types
if "easyocr" not in sys.modules:
    m = types.ModuleType("easyocr")
    class Reader:
        def __init__(self, *a, **k): pass
        def readtext(self, *a, **k): return []
    m.Reader = Reader
    m.__version__ = "0.0.0-stub"
    sys.modules["easyocr"] = m
for _n in ("rapidocr", "ocrmac"):
    if _n not in sys.modules:
        sys.modules[_n] = types.ModuleType(_n)

# ---------- 2) imports（相容新舊 docling） ----------
from pathlib import Path
from importlib.util import find_spec

# backend
try:
    from docling.backends.docling_parse_v4 import DoclingParseV4DocumentBackend
except Exception:
    from docling.backend.docling_parse_v4_backend import DoclingParseV4DocumentBackend  # type: ignore

# datamodel / pipeline / converter
try:
    from docling.datamodel.pipeline_options import PdfPipelineOptions
except Exception:
    from docling.pipeline.standard_pdf_pipeline import PdfPipelineOptions  # type: ignore

try:
    from docling.document_converter import DocumentConverter, InputFormat, PdfFormatOption
except Exception:
    from docling.document_converter import DocumentConverter, PdfFormatOption  # type: ignore
    from docling.datamodel.base_models import InputFormat  # type: ignore

# ImageRefMode
try:
    from docling_core.types.doc import ImageRefMode
except Exception:
    from docling.models.docling_document import ImageRefMode  # type: ignore


INPUT_DIR  = "/work/genai-apps/dataprep/sample-data/multi-format"
OUTPUT_DIR = "/work/tmp/multi-converted"

# ---------- 3) 鎖定 Tesseract（與 batch 相同邏輯） ----------
def force_tesseract(opts: "PdfPipelineOptions", lang=("eng",), dpi=300, enable_osd=False):
    # 關掉所有可能走到 DL/加速器的選項（若該欄位存在）
    for k in ("pin_memory","use_pinned_memory","pinned_memory",
              "enable_vlm","enable_picture_description","enable_image_understanding",
              "enable_layout_model","enable_table_model","enable_vision_models",
              "use_gpu","use_accelerator","accelerate"):
        if hasattr(opts, k):
            setattr(opts, k, False)

    # 嘗試把所有 OCR 相關欄位統一設為 tesseract（不同版位名稱不同）
    for k, v in [
        ("ocr_engines", ["tesseract"]), ("ocr_backends", ["tesseract"]),
        ("ocr_engine", "tesseract"),    ("ocr_engine_name", "tesseract"),
        ("ocr_model", "tesseract"),     ("ocr_model_name", "tesseract"),
        ("default_ocr_engine", "tesseract"),
        ("layout_engine", "heuristic"), ("table_structure_engine", "heuristic"),
        ("figure_detection_engine", "none"),
    ]:
        if hasattr(opts, k):
            setattr(opts, k, v)

    # 新 API：docling_parse.ocr.OcrOptions
    if find_spec("docling_parse.ocr") is not None:
        from docling_parse.ocr import OcrOptions, OcrEngine  # type: ignore
        opts.ocr_options = OcrOptions(
            engine=OcrEngine.TESSERACT,
            languages=list(lang),
            dpi=dpi,
            enable_osd=enable_osd,
        )
    else:
        # 舊 API 字段
        for k, v in [("ocr_languages", list(lang)), ("ocr_dpi", dpi), ("ocr_enable_osd", enable_osd)]:
            if hasattr(opts, k):
                setattr(opts, k, v)


def main():
    in_dir = Path(INPUT_DIR)
    out_dir = Path(OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not in_dir.exists():
        print(f"[ERROR] Input dir not found: {in_dir}", file=sys.stderr)
        return

    allowed = ["*.pdf", "*.docx", "*.xlsx", "*.pptx", "*.csv", "*.asciidoc"]
    inputs = []
    for ext in allowed:
        inputs.extend(in_dir.glob(ext))

    print(f"[INFO] Found {len(inputs)} files in {in_dir}")
    if not inputs:
        print("[WARN] No files to convert.")
        return

    # PDF/Office 皆可用預設 converter；OCR 鎖 tesseract
    opts = PdfPipelineOptions()
    opts.generate_page_images = True
    force_tesseract(opts, lang=("eng",))  # 需要中文改為 ("chi_sim",) 或 ("chi_tra",)

    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=opts,
                backend=DoclingParseV4DocumentBackend
            )
        }
    )

    results = converter.convert_all(inputs, raises_on_error=False)

    saved = 0
    for r in results:
        # 相容不同版本：input_path 或 input.file
        stem = getattr(r, "input_path", None).stem if getattr(r, "input_path", None) else r.input.file.stem
        if r.document is None:
            print(f"[SKIP] {stem} (no document)")
            continue

        # 👉 這裡輸出 JSON；若要 MD 改為 save_as_markdown
        out = out_dir / f"{stem}.json"
        r.document.save_as_json(out, image_mode=ImageRefMode.PLACEHOLDER)
        print("[SAVE]", out)
        saved += 1

    print(f"[DONE] Saved {saved} file(s) to {out_dir}")


if __name__ == "__main__":
    import sys
    if find_spec("torch") is not None and not os.getenv("ALLOW_TORCH", ""):
        print("WARNING: PyTorch detected; we force Tesseract and disable DL OCR engines "
              "to avoid AVX-related crashes. Set ALLOW_TORCH=1 to silence.")
    main()
