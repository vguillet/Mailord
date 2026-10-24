"""Local, passive MIME exports. Originals never pass through a remote renderer.

Dates use Europe/Paris. Reception is preferred, then the message Date header,
then discovery time; the engine persists discovery time for stable retries.
PDF export deliberately preserves text and headers, not HTML page styling.
"""
from __future__ import annotations

from datetime import datetime
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from functools import partial
import hashlib
from html import escape
from html.parser import HTMLParser
from io import BytesIO
import mimetypes
import os
from pathlib import Path
import re
import tempfile
import unicodedata
import warnings
from zoneinfo import ZoneInfo

from PIL import Image, ImageOps
from pypdf import PdfReader
import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Image as PDFImage
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

PARIS = ZoneInfo("Europe/Paris")
PREFIXES = {"%Y-%m-%d", "%Y%m%d"}
TEXT_SUFFIXES = {".txt", ".csv", ".log", ".md", ".json", ".xml"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".gif", ".bmp", ".webp"}


class _PassiveHTML(HTMLParser):
    _blocked = {"script", "style", "head", "template", "iframe", "object", "svg", "noscript"}
    _blocks = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "hr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.blocked = []

    def handle_starttag(self, tag, attrs):
        if tag in self._blocked:
            self.blocked.append(tag)
        if not self.blocked and tag in self._blocks:
            self.parts.append("\n")
        if not self.blocked and tag in {"td", "th"}:
            self.parts.append("  ")

    def handle_endtag(self, tag):
        if self.blocked:
            if tag in self.blocked:
                self.blocked = self.blocked[:self.blocked.index(tag)]
            return
        if tag in self._blocks:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.blocked:
            self.parts.append(data)

    def text(self):
        text = "".join(self.parts).replace("\xa0", " ")
        text = re.sub(r"[ \t]+", " ", text)
        return re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", text).strip()


def _decode(content: bytes, charset=None) -> str:
    try:
        return content.decode(charset or "utf-8", errors="replace")
    except (LookupError, TypeError):
        return content.decode("utf-8", errors="replace")


def _date(value) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            try:
                parsed = parsedate_to_datetime(str(value))
            except (ValueError, TypeError, OverflowError):
                return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=PARIS)
    try:
        return parsed.astimezone(PARIS)
    except (ValueError, OverflowError):
        return None


def _header(message, key, default=""):
    try:
        return str(message.get(key, default)).strip()
    except (ValueError, UnicodeError):
        return default


def parse_message(raw: bytes, received_at: str | None = None) -> dict:
    """Decode message headers, a single body alternative and original attachments."""
    if not isinstance(raw, bytes):
        raise TypeError("Le message doit être fourni en octets MIME.")
    message = BytesParser(policy=policy.default).parsebytes(raw)
    sent = _date(_header(message, "Date"))
    received = _date(received_at)
    effective = received or sent or datetime.now(PARIS)
    body_part = message.get_body(preferencelist=("plain", "html"))
    body = ""
    if body_part is not None:
        content = body_part.get_payload(decode=True) or b""
        body = _decode(content, body_part.get_content_charset())
        if body_part.get_content_type() == "text/html":
            parser = _PassiveHTML()
            parser.feed(body)
            body = parser.text()
    attachments = []

    def collect(part):
        disposition = part.get_content_disposition()
        original_name = part.get_filename()
        if part.get_content_type() == "message/rfc822":
            payload = part.get_payload()
            content = b"\n".join(p.as_bytes(policy=policy.default) for p in payload) if isinstance(payload, list) else (part.get_payload(decode=True) or b"")
            attachments.append({"name": original_name or f"message-joint-{len(attachments) + 1}.eml", "content": content,
                                "content_type": "message/rfc822", "inline": disposition == "inline"})
            return
        if part.is_multipart():
            for child in part.iter_parts():
                collect(child)
            return
        if part is body_part:
            return
        content_type = part.get_content_type()
        # Unchosen plain/HTML alternatives are representations, not attachments.
        if not original_name and disposition != "attachment" and content_type in {"text/plain", "text/html"}:
            return
        content = part.get_payload(decode=True) or b""
        extension = mimetypes.guess_extension(content_type) or ".bin"
        attachments.append({"name": str(original_name or f"piece-jointe-{len(attachments) + 1}{extension}"),
                            "content": content, "content_type": content_type,
                            "inline": disposition == "inline" or (bool(part.get("Content-ID")) and disposition != "attachment")})

    collect(message)
    return {"subject": _header(message, "Subject", "Sans objet") or "Sans objet",
            "sender": _header(message, "From"), "recipients": _header(message, "To"),
            "cc": _header(message, "Cc"), "date": effective.isoformat(),
            "sent_date": sent.isoformat() if sent else None,
            "received_date": received.isoformat() if received else None,
            "body": body, "attachments": attachments}


def _truncate(value, limit=210):
    return value.encode("utf-8")[:limit].decode("utf-8", errors="ignore")


def _basename(original: str) -> str:
    name = unicodedata.normalize("NFC", str(original)).replace("\\", "/").split("/")[-1]
    name = "".join(c for c in name if not unicodedata.category(c).startswith("C"))
    name = re.sub(r'[<>:"|?*]', "_", name).strip(" .")
    name = re.sub(r"^(?:(?:\d{4}-\d{2}-\d{2}|\d{8})\s+-\s+)+", "", name)
    return name or "document"


def filename(original, date, prefix_format="%Y-%m-%d") -> str:
    """Keep the safe basename and extension, replacing any prior date prefix."""
    if prefix_format not in PREFIXES:
        raise ValueError("Le préfixe doit être %Y-%m-%d ou %Y%m%d.")
    parsed_date = _date(date)
    if parsed_date is None:
        raise ValueError("Date de document invalide.")
    base = _basename(original)
    suffix = Path(base).suffix
    if len(suffix.encode("utf-8")) > 24:
        suffix = ""
    stem = base[:-len(suffix)] if suffix else base
    prefix = parsed_date.strftime(prefix_format) + " - "
    stem = _truncate(stem, 220 - len(prefix.encode("utf-8")) - len(suffix.encode("utf-8")))
    return prefix + stem + suffix


def safe_path(root: Path, relative) -> Path:
    """Reject traversal and symlinks resolving outside a caller-owned root."""
    root = Path(root).resolve()
    value = str(relative)
    if "\x00" in value or "\\" in value or re.match(r"^[a-zA-Z]:", value):
        raise ValueError("Chemin de document invalide.")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Le chemin doit rester dans le dossier autorisé.")
    try:
        resolved = (root / path).resolve()
    except (OSError, RuntimeError) as error:
        raise ValueError("Chemin de document invalide.") from error
    if not resolved.is_relative_to(root):
        raise ValueError("Le chemin sort du dossier autorisé.")
    return resolved


def _font():
    name = "MailordUnicode"
    if name not in pdfmetrics.getRegisteredFontNames():
        candidates = [Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
                      Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
                      Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"]
        path = next((p for p in candidates if p.is_file()), None)
        if not path:
            raise RuntimeError("Police Unicode introuvable ; réinstaller ReportLab.")
        pdfmetrics.registerFont(TTFont(name, str(path)))
    return name


def _pdf_bytes(parsed):
    buffer = BytesIO()
    font = _font()
    body_style = ParagraphStyle("body", fontName=font, fontSize=10, leading=15, spaceAfter=5,
                                alignment=TA_LEFT, splitLongWords=True, allowWidows=0, allowOrphans=0)
    title_style = ParagraphStyle("title", parent=body_style, fontSize=16, leading=21, spaceAfter=14)
    header_style = ParagraphStyle("header", parent=body_style, fontSize=9, leading=13,
                                  textColor=colors.HexColor("#3f4755"))
    document = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=44, rightMargin=44,
                                 topMargin=42, bottomMargin=40, title=parsed.get("subject", "Mail"),
                                 author="Mailord", invariant=1)
    story = [Paragraph(escape(str(parsed.get("subject", "Sans objet"))), title_style)]
    for label, key in (("Expéditeur", "sender"), ("Destinataires", "recipients"), ("Copie", "cc"), ("Date", "date")):
        value = parsed.get(key)
        if value or key != "cc":
            story.append(Paragraph(escape(f"{label} : {value or 'Non renseigné'}"), header_style))
    story.append(Spacer(1, 15))
    body = str(parsed.get("body") or "(Ce message ne contient pas de texte.)")
    # Paragraph receives escaped text only: never HTML links, images or scripts.
    for line in body.splitlines():
        line = "".join(c for c in line if c == "\t" or not unicodedata.category(c).startswith("C"))
        story.append(Paragraph(escape(line).replace("\t", "    ") or "&#160;", body_style))

    def footer(pdf, doc):
        pdf.saveState()
        pdf.setFont(font, 8)
        pdf.setFillColor(colors.HexColor("#64748b"))
        pdf.drawRightString(A4[0] - 44, 24, f"Page {doc.page}")
        pdf.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer,
                   canvasmaker=partial(canvas.Canvas, invariant=1))
    return buffer.getvalue()


def _publish(content: bytes, target: Path):
    """Publish complete bytes atomically without replacing any existing file."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".mailord-", suffix=".tmp", dir=target.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def render_pdf(parsed: dict, path: Path) -> Path:
    """Write a text PDF; a pre-existing different file is never overwritten."""
    path = Path(path)
    content = _pdf_bytes(parsed)
    try:
        _publish(content, path)
    except FileExistsError:
        if path.is_symlink() or not path.is_file() or path.read_bytes() != content:
            raise ValueError("Un autre fichier existe déjà à cet emplacement.") from None
    return path


def valid_pdf(path: Path) -> bool:
    try:
        with Path(path).open("rb") as stream:
            if not stream.read(5) == b"%PDF-":
                return False
            stream.seek(0)
            reader = PdfReader(stream, strict=True)
            return not reader.is_encrypted and len(reader.pages) > 0 and all(page.mediabox.width > 0 for page in reader.pages)
    except Exception:
        return False


def _image_valid(path):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as img:
                img.verify()
        return True
    except Exception:
        return False


def _printable(path):
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return valid_pdf(path)
    if suffix in IMAGE_SUFFIXES:
        return _image_valid(path)
    if suffix in TEXT_SUFFIXES:
        try:
            sample = path.read_bytes()
            return b"\x00" not in sample
        except OSError:
            return False
    return False


def _store_bytes(directory, name, content, identity=""):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(content).hexdigest()
    token = hashlib.sha256((identity + ":" + digest).encode()).hexdigest()[:10]
    stem, suffix = Path(name).stem, Path(name).suffix
    for index in range(10000):
        suffix_name = "" if index == 0 else f" - {token}" + (f"-{index}" if index > 1 else "")
        candidate_name = _truncate(stem, 220 - len(suffix_name.encode()) - len(suffix.encode())) + suffix_name + suffix
        unresolved = directory / candidate_name
        # Even symlinks within the root are never followed as existing exports.
        if unresolved.is_symlink():
            continue
        path = safe_path(directory, candidate_name)
        try:
            _publish(content, path)
            return path, digest
        except FileExistsError:
            if path.is_file() and not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest() == digest:
                return path, digest
    raise ValueError("Trop de fichiers portent le même nom dans ce dossier.")


def export_message(raw: bytes, directory: Path, received_at: str | None = None,
                   date_source="received", prefix_format="%Y-%m-%d", identity="") -> list[dict]:
    if date_source not in {"received", "sent"}:
        raise ValueError("La date doit être celle de réception ou d’envoi.")
    if prefix_format not in PREFIXES:
        raise ValueError("Format de préfixe invalide.")
    parsed = parse_message(raw, received_at)
    date = (parsed["sent_date"] or parsed["date"]) if date_source == "sent" else parsed["date"]
    original_name = parsed["subject"] + ".pdf"
    path, digest = _store_bytes(directory, filename(original_name, date, prefix_format), _pdf_bytes(parsed), identity + ":email")
    docs = [{"kind": "email", "original_name": original_name, "path": str(path), "name": path.name,
             "sha256": digest, "printable": True, "inline": False, "content_type": "application/pdf"}]
    for index, attachment in enumerate(parsed["attachments"]):
        name = filename(attachment["name"], date, prefix_format)
        path, digest = _store_bytes(directory, name, attachment["content"], f"{identity}:attachment:{index}")
        docs.append({"kind": "attachment", "original_name": attachment["name"], "path": str(path), "name": path.name,
                     "sha256": digest, "printable": _printable(path), "inline": attachment["inline"],
                     "content_type": attachment["content_type"]})
    return docs


def convert_for_print(path: Path, output_dir: Path | None = None) -> Path:
    """Prepare supported files; Office and other unsupported formats stay original."""
    path = Path(path)
    if not _printable(path):
        raise ValueError("Format non imprimable ou document endommagé.")
    if path.suffix.lower() == ".pdf":
        return path
    output_dir = Path(output_dir) if output_dir is not None else path.parent / ".print"
    if path.suffix.lower() in TEXT_SUFFIXES:
        content = _pdf_bytes({"subject": path.name, "sender": "Pièce jointe", "recipients": "—", "date": "—",
                              "body": _decode(path.read_bytes())})
    else:
        buffer = BytesIO()
        story = []
        with Image.open(path) as original:
            # Preserve every page of scanned TIFFs; animated GIFs use their first frame.
            frames = getattr(original, "n_frames", 1) if path.suffix.lower() in {".tif", ".tiff"} else 1
            from reportlab.platypus import PageBreak
            for index in range(frames):
                original.seek(index)
                img = ImageOps.exif_transpose(original.copy()).convert("RGB")
                image_data = BytesIO()
                img.save(image_data, format="PNG")
                image_data.seek(0)
                width, height = img.size
                scale = min((A4[0] - 72) / width, (A4[1] - 72) / height, 1)
                if story:
                    story.append(PageBreak())
                story.append(PDFImage(image_data, width=width * scale, height=height * scale))
        SimpleDocTemplate(buffer, pagesize=A4, leftMargin=30, rightMargin=30, topMargin=30, bottomMargin=30, invariant=1).build(
            story, canvasmaker=partial(canvas.Canvas, invariant=1))
        content = buffer.getvalue()
    exported, _ = _store_bytes(output_dir, _basename(path.stem) + ".pdf", content, hashlib.sha256(path.read_bytes()).hexdigest())
    return exported
