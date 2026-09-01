"""Reading whatever the user attaches.

One job: turn an uploaded file into text, or say honestly why that isn't
possible. What the text *means* is decided elsewhere — this layer never guesses
at intent, and it never writes.

Supported today:
  • PDF with a text layer      -> extracted text
  • Plain text / markdown / csv -> the text itself

Not supported, and said plainly rather than failing quietly:
  • Images, and PDFs that are scans — there is no OCR in this deployment, so a
    picture of a timetable cannot be read. Reporting "no classes found" for a
    scan would look like a parsing result rather than a missing capability.
"""
import io
import re
from dataclasses import dataclass

MAX_BYTES = 8 * 1024 * 1024          # generous for a document, small enough to bound work
MAX_CHARS = 40_000                   # what downstream interpreters will look at

PDF_TYPES = {"application/pdf", "application/x-pdf"}
TEXT_TYPES = {"text/plain", "text/markdown", "text/csv", "application/json"}
IMAGE_PREFIX = "image/"

TEXT_SUFFIXES = (".txt", ".md", ".markdown", ".csv", ".json")
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic", ".bmp", ".tiff")


class UnreadableAttachment(Exception):
    """Cannot be read. The message is written for the user, not the log."""


@dataclass
class Attachment:
    filename: str
    kind: str          # "pdf" | "text"
    text: str
    pages: int = 1

    @property
    def chars(self) -> int:
        return len(self.text)

    def preview(self, limit: int = 400) -> str:
        flat = re.sub(r"\s+", " ", self.text).strip()
        return flat[:limit] + ("…" if len(flat) > limit else "")


def _read_pdf(data: bytes, filename: str) -> Attachment:
    try:
        from pypdf import PdfReader
    except ImportError:  # pragma: no cover — pinned dependency
        raise UnreadableAttachment("PDF support isn't installed on the server.")

    try:
        reader = PdfReader(io.BytesIO(data))
        if getattr(reader, "is_encrypted", False):
            try:
                reader.decrypt("")
            except Exception:
                raise UnreadableAttachment(
                    "That PDF is password-protected, so I can't open it.")
        pages = [(p.extract_text() or "") for p in reader.pages]
    except UnreadableAttachment:
        raise
    except Exception as exc:
        raise UnreadableAttachment(f"I couldn't open that PDF ({type(exc).__name__}).")

    text = "\n".join(pages).strip()
    if not text:
        raise UnreadableAttachment(
            "That PDF has no readable text — it looks like a scan or a photo. "
            "I can't read images, so I'd need a text-based PDF.")
    return Attachment(filename=filename, kind="pdf", text=text[:MAX_CHARS], pages=len(pages))


def read(data: bytes, filename: str = "", content_type: str = "") -> Attachment:
    """Turn an upload into text, or raise UnreadableAttachment with a reason."""
    name = (filename or "attachment").strip()
    lower = name.lower()
    ctype = (content_type or "").split(";")[0].strip().lower()

    if not data:
        raise UnreadableAttachment("That file was empty.")
    if len(data) > MAX_BYTES:
        raise UnreadableAttachment(
            f"That file is larger than {MAX_BYTES // (1024 * 1024)} MB.")

    if ctype.startswith(IMAGE_PREFIX) or lower.endswith(IMAGE_SUFFIXES):
        raise UnreadableAttachment(
            "I can't read images — there's no OCR in this build. If you can export "
            "the same thing as a text-based PDF or paste the text, I can work with that.")

    if ctype in PDF_TYPES or lower.endswith(".pdf") or data[:5].startswith(b"%PDF"):
        return _read_pdf(data, name)

    if ctype in TEXT_TYPES or lower.endswith(TEXT_SUFFIXES):
        try:
            text = data.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            try:
                text = data.decode("latin-1")
            except Exception:
                raise UnreadableAttachment("I couldn't decode that file as text.")
        if not text.strip():
            raise UnreadableAttachment("That file was empty.")
        return Attachment(filename=name, kind="text", text=text[:MAX_CHARS])

    raise UnreadableAttachment(
        "I can read PDFs and plain text. That looks like something else — if you "
        "can export it as a PDF or paste the contents, I'll take a look.")
