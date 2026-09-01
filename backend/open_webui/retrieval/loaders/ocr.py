"""Text-layer-first PDF loader with per-page OCR fallback.

Upstream's `PyPDFLoader(extract_images=True)` cannot serve this deployment, for
three separate reasons measured against the corpus:

1. It reads only the *first* filter of a filter chain, so an image stored as
   `['/FlateDecode', '/DCTDecode']` is classified lossless and reshaped as raw
   pixels while `get_data()` actually returns JPEG bytes -> `ValueError:
   cannot reshape array of size 13369 into shape (827,1169,newaxis)`.
2. `/CCITTFaxDecode` objects fail the same reshape: pypdf returns a
   TIFF-wrapped stream, not a pixel buffer.
3. Even with both fixed it extracts *XObjects*. The scanned documents here are
   MRC/layered scans - a near-blank JPEG background plus dozens of bitonal
   CCITT text masks - so per-image OCR reads a blank page and a pile of
   fragments. The text only exists once the page is composited.

So this loader rasterises the *page* and OCRs that, and only for pages that
have no usable text layer. Across the current corpus 91% of pages (337/370)
carry real text and never reach the OCR path.
"""

import hashlib
import logging
import os
import sys
import threading

from langchain_core.documents import Document
from open_webui.env import GLOBAL_LOG_LEVEL, REQUESTS_VERIFY

logging.basicConfig(stream=sys.stdout, level=GLOBAL_LOG_LEVEL)
log = logging.getLogger(__name__)

# Ships with the repo: the character dict belonging to the rec model below,
# extracted from its `inference.yml`. Written with no trailing newline -
# RapidOCR's `read_character_file` would read one as an extra empty entry and
# shift the appended ' ' index, corrupting every decode.
DEFAULT_KEYS_PATH = os.path.join(os.path.dirname(__file__), 'ocr_dicts', 'cyrillic_keys.txt')

# Mirrors PDF_OCR_REC_MODEL_URL's default in config.py. Repeated rather than
# imported so the loader still works when constructed directly (scripts, tests)
# - without it an unset URL reaches requests as '' and raises MissingSchema,
# which reads as a network fault rather than a missing setting.
DEFAULT_REC_MODEL_URL = (
    'https://huggingface.co/PaddlePaddle/cyrillic_PP-OCRv5_mobile_rec_onnx/resolve/main/inference.onnx'
)

_engine_lock = threading.Lock()
_engine_cache: dict = {}


def _download(url: str, dest: str) -> None:
    """Fetch `url` to `dest`, atomically, so a killed process leaves no stub."""
    import requests

    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = f'{dest}.part'
    log.info(f'Downloading OCR model: {url}')
    with requests.get(url, stream=True, timeout=300, verify=REQUESTS_VERIFY) as r:
        r.raise_for_status()
        with open(tmp, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    os.replace(tmp, dest)
    log.info(f'OCR model ready: {dest} ({os.path.getsize(dest)} bytes)')


def _get_engine(model_dir: str, model_url: str, keys_path: str):
    """Build (once) the RapidOCR engine.

    Cached because loading the ONNX sessions costs seconds and `Loader.load`
    runs per file on a worker thread (`Loader.aload` -> `asyncio.to_thread`),
    so this is reached concurrently.
    """
    cache_key = (model_dir, model_url, keys_path)
    with _engine_lock:
        if cache_key in _engine_cache:
            return _engine_cache[cache_key]

        from rapidocr_onnxruntime import RapidOCR

        # Namespaced by a digest of the URL: these models are all published as
        # `inference.onnx`, so caching on the basename alone would serve a
        # stale Cyrillic model to someone who had swapped in another language.
        digest = hashlib.sha256(model_url.encode()).hexdigest()[:12]
        name = os.path.basename(model_url.split('?')[0]) or 'rec.onnx'
        model_path = os.path.join(model_dir, f'{digest}_{name}')
        if not os.path.exists(model_path):
            _download(model_url, model_path)

        # Every one of these deviates from RapidOCR's defaults for a measured
        # reason. Numbers are page 4 of РД-1910000-КТН-001-10 (dense justified
        # Russian body text); see the branch notes before changing any of them.
        #
        #   use_cls=False        the bundled `ch_ppocr_mobile_v2.0_cls` angle
        #                        classifier is trained on Chinese text and
        #                        misfires on Cyrillic, flipping whole lines
        #                        180deg so they decode to blanks.
        #                        560 -> 1171 chars, 3 blank lines -> 0,
        #                        mean confidence 0.810 -> 0.977, no time cost.
        #                        Trade-off accepted: genuinely rotated text
        #                        (e.g. a vertical margin stamp) is no longer
        #                        straightened.
        #   det_limit_type='max' RapidOCR defaults to 'min'/736, which only
        #                        ever upscales - so detection ran at the full
        #                        2480x3507, ~4x the DB model's training scale,
        #                        and over-segmented lines into fragments.
        #                        Capping the long side merges them back:
        #                        29 ragged boxes -> 21 clean full lines.
        #   max_side_len=4000    the global default of 2000 silently downscaled
        #                        a 300 DPI A4 render before detection ever ran.
        engine = RapidOCR(
            rec_model_path=model_path,
            rec_keys_path=keys_path,
            use_cls=False,
            det_limit_type='max',
            det_limit_side_len=1280,
            max_side_len=4000,
        )
        _engine_cache[cache_key] = engine
        return engine


class PDFOCRLoader:
    """Load a PDF page by page, OCRing only the pages that need it."""

    def __init__(
        self,
        file_path: str,
        dpi: int = 300,
        text_threshold: int = 100,
        model_dir: str = '',
        model_url: str = '',
        keys_path: str = '',
        mode: str = 'page',
    ):
        if not os.path.exists(file_path):
            raise FileNotFoundError(f'File not found at {file_path}')

        self.file_path = file_path
        self.dpi = dpi
        self.text_threshold = text_threshold
        self.model_dir = model_dir
        self.model_url = model_url or DEFAULT_REC_MODEL_URL
        self.keys_path = keys_path or DEFAULT_KEYS_PATH
        self.mode = mode

    def _read_text_layer(self, pdf, index: int) -> str:
        """Return the page's embedded text. Handles are closed explicitly -
        pypdfium2 keeps every page and textpage alive on the parent document
        otherwise, which on a 334-page book means 334 leaked handles.
        """
        page = pdf[index]
        try:
            textpage = page.get_textpage()
            try:
                return textpage.get_text_range().strip()
            finally:
                textpage.close()
        finally:
            page.close()

    def _ocr_page(self, engine, pdf, index: int) -> str:
        """Rasterise one page and return its recognised text, top-to-bottom."""
        page = pdf[index]
        try:
            image = page.render(scale=self.dpi / 72).to_pil()
        finally:
            page.close()

        result, _ = engine(image)
        if not result:
            return ''
        # RapidOCR returns (box, text, score); box[0] is the top-left corner.
        # Detection order is not reading order, so sort by y then x. The y is
        # bucketed to 10px so a slightly skewed line does not sort by its tilt.
        ordered = sorted(result, key=lambda item: (round(item[0][0][1] / 10), item[0][0][0]))
        return '\n'.join(text for _box, text, _score in ordered if text.strip())

    def load(self) -> list[Document]:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(self.file_path)
        try:
            return self._load(pdf)
        finally:
            pdf.close()

    def _load(self, pdf) -> list[Document]:
        total = len(pdf)

        # Read every text layer first, so the engine (and its download) is only
        # touched when a page actually needs it.
        page_texts: list[str] = []
        needs_ocr: list[int] = []
        # Pages whose text actually came from OCR, which is not the same as the
        # pages that were *tried* - see the length guard below.
        ocr_applied: set[int] = set()
        for index in range(total):
            text = self._read_text_layer(pdf, index)
            page_texts.append(text)
            if len(text) < self.text_threshold:
                needs_ocr.append(index)

        if needs_ocr:
            log.info(f'OCR: {len(needs_ocr)}/{total} pages have no text layer in {os.path.basename(self.file_path)}')
            # Deliberately not caught: a document whose scanned pages silently
            # embed as empty looks like a perfectly normal approved document
            # in the registry. Failing the upload is the honest outcome.
            engine = _get_engine(self.model_dir, self.model_url, self.keys_path)
            for position, index in enumerate(needs_ocr, start=1):
                try:
                    text = self._ocr_page(engine, pdf, index)
                except Exception as e:
                    # One bad page should not lose the other 200.
                    log.warning(f'OCR failed on page {index + 1}/{total}: {e}')
                    continue
                # Keep whichever is longer. The threshold catches pages with a
                # thin-but-real text layer too - a diagram with a few labels, or
                # somebody's earlier bad OCR - and those must not end up with
                # *less* text than they arrived with. OCR returning '' for a
                # page it could not read is the same case.
                if len(text) > len(page_texts[index]):
                    page_texts[index] = text
                    ocr_applied.add(index)
                if position % 10 == 0:
                    log.info(f'OCR: {position}/{len(needs_ocr)} pages done')

        metadata = {'source': self.file_path, 'total_pages': total}
        if self.mode == 'single':
            return [Document(page_content='\n\n'.join(page_texts), metadata=metadata)]

        return [
            Document(
                page_content=text,
                metadata={
                    **metadata,
                    'page': index,
                    'page_label': str(index + 1),
                    'ocr': index in ocr_applied,
                },
            )
            for index, text in enumerate(page_texts)
        ]
