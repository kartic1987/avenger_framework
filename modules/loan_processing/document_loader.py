from pathlib import Path
import io
import pymupdf
from PIL import Image

SUPPORTED_IMAGES = {".png", ".jpg", ".jpeg", ".webp"}
SUPPORTED_FILES = SUPPORTED_IMAGES | {".pdf"}


def load_document(uploaded_file):
    """Return text, page images and mime type from a Streamlit UploadedFile-like object."""
    name = uploaded_file.name
    suffix = Path(name).suffix.lower()
    data = uploaded_file.getvalue()

    if suffix not in SUPPORTED_FILES:
        raise ValueError(f"Unsupported file type: {suffix}")

    if suffix == ".pdf":
        texts, images = [], []
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            for page in doc:
                page_text = page.get_text("text").strip()
                if page_text:
                    texts.append(page_text)
                # Render pages too: scanned PDFs often have no selectable text.
                pix = page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False)
                images.append(pix.tobytes("png"))
        return {
            "filename": name,
            "text": "\n".join(texts).strip(),
            "images": images,
            "mime_type": "application/pdf",
            "raw_bytes": data,
        }

    image = Image.open(io.BytesIO(data)).convert("RGB")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return {
        "filename": name,
        "text": "",
        "images": [buf.getvalue()],
        "mime_type": "image/png",
        "raw_bytes": data,
    }
