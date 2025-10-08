#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Batch convert PDFs to Markdown with Docling, CPU-safe:
- Force OCR to Tesseract (env + options 双保险)
- Disable DL-based OCR engines (easyocr/rapidocr/ocrmac)
- Provide a harmless easyocr stub to avoid crashes even if instantiated
"""

# ---------- 0) env overrides: 禁用非 tesseract 引擎 ----------
import os
os.environ.setdefault("DOCLING_OCR_ENGINE", "tesseract")      # 有些版本读取这个
os.environ.setdefault("DOCLING_OCR_ENGINES", "tesseract")     # 白名单
os.environ.setdefault("DOCLING_DISABLE_OCR_ENGINES", "easyocr,rapidocr,ocrmac")

# ---------- 1) easyocr stub：不抛错、不依赖 torch，但也不做 OCR ----------
import sys, types
if "easyocr" not in sys.modules:
    _m = types.ModuleType("easyocr")
    class Reader:
        def __init__(self, *a, **kw): pass
        # 返回空结果，避免被真正使用；我们会把引擎强制到 tesseract
        def readtext(self, *a, **kw): return []
    _m.Reader = Reader
    _m.__version__ = "0.0.0-stub"
    sys.modules["easyocr"] = _m

# 可选：如担心 rapidocr / ocrmac 被误触发，也 stub 掉
for _name in ("rapidocr", "ocrmac"):
    if _name not in sys.modules:
        sys.modules[_name] = types.ModuleType(_name)

# ---------- 2) imports ----------
from pathlib import Path
from importlib.util import find_spec

from docling.backend.docling_parse_v4_backend import DoclingParseV4DocumentBackend
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import ImageRefMode

INPUT_DIR  = "sample-data/batch"
OUTPUT_DIR = "/work/tmp/batch-converted"

# ---------- 3) force tesseract & 关闭 DL 路径 ----------
def force_tesseract(pipeline_options: "PdfPipelineOptions",
                    lang: list[str] = ["eng"], dpi: int = 300,
                    enable_osd: bool = False) -> None:
    # 避免 DataLoader pinned memory
    for k in ("pin_memory", "use_pinned_memory", "pinned_memory"):
        if hasattr(pipeline_options, k):
            setattr(pipeline_options, k, False)

    # 关掉可能触发模型/加速器的路径（若字段存在则生效）
    for k in ("enable_vlm","enable_picture_description","enable_image_understanding",
              "enable_layout_model","enable_table_model","enable_vision_models",
              "use_gpu","use_accelerator","accelerate"):
        if hasattr(pipeline_options, k):
            setattr(pipeline_options, k, False)

    # 引擎选择字段尽量全部设为 tesseract（不同版本字段名不同）
    for k, v in [
        ("ocr_engines", ["tesseract"]),
        ("ocr_backends", ["tesseract"]),
        ("ocr_engine", "tesseract"),
        ("ocr_engine_name", "tesseract"),
        ("ocr_model", "tesseract"),
        ("ocr_model_name", "tesseract"),
        ("default_ocr_engine", "tesseract"),
        ("layout_engine", "heuristic"),
        ("table_structure_engine", "heuristic"),
        ("figure_detection_engine", "none"),
    ]:
        if hasattr(pipeline_options, k):
            setattr(pipeline_options, k, v)

    # 新 API：OcrOptions
    if find_spec("docling_parse.ocr") is not None:
        from docling_parse.ocr import OcrOptions, OcrEngine  # type: ignore
        pipeline_options.ocr_options = OcrOptions(
            engine=OcrEngine.TESSERACT,
            languages=list(lang),
            dpi=dpi,
            enable_osd=enable_osd,
        )
    else:
        for k, v in [("ocr_languages", list(lang)), ("ocr_dpi", dpi), ("ocr_enable_osd", enable_osd)]:
            if hasattr(pipeline_options, k):
                setattr(pipeline_options, k, v)

# ---------- 4) main ----------
def main() -> None:
    in_dir  = Path(INPUT_DIR)
    out_dir = Path(OUTPUT_DIR); out_dir.mkdir(parents=True, exist_ok=True)
    pdfs = list(in_dir.glob("*.pdf"))

    opts = PdfPipelineOptions()
    opts.generate_page_images = True
    force_tesseract(opts, lang=["eng"])  # 中文可改 ["chi_sim"] / ["chi_tra"]

    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=opts,
                backend=DoclingParseV4DocumentBackend
            )
        }
    )

    results = converter.convert_all(pdfs, raises_on_error=False)
    for r in results:
        stem = r.input.file.stem
        r.document.save_as_markdown(out_dir / f"{stem}.md",
                                    image_mode=ImageRefMode.PLACEHOLDER)

if __name__ == "__main__":
    # 不再强制退出；打印一次软警告即可
    import importlib.util as _u
    if _u.find_spec("torch") is not None and not os.getenv("ALLOW_TORCH",""):
        print("WARNING: PyTorch detected. We force Tesseract and disabled other OCR engines "
              "to avoid DL paths. Set ALLOW_TORCH=1 to silence this message.")
    main()
