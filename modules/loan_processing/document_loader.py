from core.document_loader import load_visual_document

SUPPORTED_IMAGES = {".png", ".jpg", ".jpeg", ".webp"}
SUPPORTED_FILES = SUPPORTED_IMAGES | {".pdf"}


def load_document(uploaded_file):
    """Return text, page images and mime type from a Streamlit UploadedFile-like object."""
    return load_visual_document(uploaded_file.name, uploaded_file.getvalue())
