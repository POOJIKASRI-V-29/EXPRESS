"""Build a real, minimal PDF in memory.

Written by hand rather than pulled from a binary fixture so the tests are
readable and the input is fully controlled: what goes in is exactly what the
parser must get out. This produces a genuine PDF with a text layer — pypdf
opens it the same way it opens any other.
"""


def _escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def make_pdf(lines: list[str], *, with_text: bool = True) -> bytes:
    """A one-page PDF containing `lines`.

    `with_text=False` produces a valid PDF with no text layer at all — the
    shape a scanned timetable has, used to check that we say so rather than
    reporting an empty result.
    """
    if with_text:
        body = ["BT", "/F1 11 Tf", "50 760 Td", "14 TL"]
        for line in lines:
            body.append(f"({_escape(line)}) Tj")
            body.append("T*")
        body.append("ET")
        content = "\n".join(body).encode("latin-1")
    else:
        content = b""   # a page that draws nothing

    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"

    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_at}\n%%EOF\n").encode()
    return bytes(out)


TIMETABLE_LINES = [
    "Semester 5 Time Table",
    "Monday",
    "10:00-11:00  DBMS  Database Management Systems  Room AB-201",
    "14:00-15:00  CS310  Machine Learning  Room CD-102",
    "Tuesday",
    "09:00-10:00  DBMS  Database Management Systems  Room AB-201",
    "11:00-12:00  CS310  Machine Learning  Lab B",
    "Wednesday",
    "10:00-11:00  DBMS  Database Management Systems  Room AB-201",
]

SYLLABUS_LINES = [
    "Course Title: Database Management Systems",
    "Course Code: DBMS",
    "Unit I - Database Fundamentals",
    "- DBMS architecture",
    "- ER model",
    "- Relational model",
    "Unit II - Design",
    "- Normalization",
    "- Functional dependencies",
    "Unit III - Transactions",
    "- ACID properties",
    "- Concurrency control",
]
