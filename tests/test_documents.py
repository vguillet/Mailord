from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfReader

from mailord.documents import (
    convert_for_print, export_message, filename, parse_message, render_pdf,
    safe_path, valid_pdf,
)


def mail(body="Bonjour Élodie, votre échéance est confirmée."):
    message = EmailMessage()
    message["Subject"] = "Contrat été"
    message["From"] = "Cabinet <cabinet@example.test>"
    message["To"] = "Élodie <elodie@example.test>"
    message["Date"] = "Fri, 23 Oct 2026 14:30:00 +0200"
    message.set_content(body)
    return message


def test_parse_html_is_passive_and_keeps_headers():
    message = mail()
    message.set_content("<h1>Bonjour Élodie</h1><p>Pièce jointe reçue.</p>"
                        "<script>secret()</script><style>secret-css</style>"
                        '<img src="https://tracker.invalid/pixel"><p>Merci &amp; salut</p>',
                        subtype="html")
    parsed = parse_message(message.as_bytes(), "2026-10-23T23:30:00+00:00")
    assert parsed["subject"] == "Contrat été"
    assert "elodie@example.test" in parsed["recipients"]
    assert "Bonjour Élodie" in parsed["body"]
    assert "Merci & salut" in parsed["body"]
    assert "secret" not in parsed["body"]
    assert "tracker.invalid" not in parsed["body"]
    assert parsed["date"].startswith("2026-10-24T01:30")


def test_parse_prefers_plain_alternative_and_keeps_inline_images():
    message = mail("Plain body")
    message.add_alternative("<p>HTML duplicate</p>", subtype="html")
    message.get_payload()[1].add_related(b"logo", maintype="image", subtype="png", cid="<logo>")
    message.add_attachment(b"original", maintype="application", subtype="octet-stream", filename="original.bin")
    parsed = parse_message(message.as_bytes())
    assert parsed["body"].strip() == "Plain body"
    assert len(parsed["attachments"]) == 2
    assert parsed["attachments"][0]["inline"] is True
    assert parsed["attachments"][1]["content"] == b"original"


def test_malformed_charset_date_and_missing_subject_are_safe():
    raw = (b"Date: nonsense\r\nContent-Type: text/plain; charset=unknown-xyz\r\n"
           b"Content-Transfer-Encoding: 8bit\r\n\r\nBonjour \xff")
    parsed = parse_message(raw, "bad-date")
    assert parsed["subject"]
    assert "Bonjour" in parsed["body"]
    assert datetime.fromisoformat(parsed["date"]).tzinfo is not None


@pytest.mark.parametrize("original,expected", [
    ("facture.pdf", "2026-10-23 - facture.pdf"),
    ("2026-10-22 - facture.pdf", "2026-10-23 - facture.pdf"),
    ("20261022 - facture.pdf", "2026-10-23 - facture.pdf"),
    ("../../facture.pdf", "2026-10-23 - facture.pdf"),
    (r"C:\\private\\facture.pdf", "2026-10-23 - facture.pdf"),
])
def test_filename_preserves_basename_and_single_prefix(original, expected):
    assert filename(original, "2026-10-23T12:00:00+02:00") == expected


def test_filename_custom_prefix_and_long_unicode():
    assert filename("pièce.txt", "2026-10-23", "%Y%m%d") == "20261023 - pièce.txt"
    name = filename("é" * 300 + ".pdf", "2026-10-23")
    assert len(name.encode("utf-8")) <= 240
    assert name.endswith(".pdf")
    with pytest.raises(ValueError):
        filename("a.pdf", "2026-10-23", "../../%Y")


@pytest.mark.parametrize("relative", ["../escape.pdf", "/tmp/escape.pdf", "a/../../x", "C:\\escape.pdf"])
def test_safe_path_rejects_escape(tmp_path, relative):
    with pytest.raises(ValueError):
        safe_path(tmp_path, relative)


def test_safe_path_rejects_symlink_escape(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        safe_path(root, "link/secret.pdf")
    assert safe_path(root, "client/file.pdf") == root / "client/file.pdf"


def test_pdf_contains_unicode_headers_and_paginated_long_body(tmp_path):
    parsed = parse_message(mail(("Échéance reçue ; merci Élodie.\n" * 400) + "Z" * 700).as_bytes())
    target = tmp_path / "message.pdf"
    render_pdf(parsed, target)
    assert valid_pdf(target)
    reader = PdfReader(target)
    assert len(reader.pages) > 2
    text = "\n".join(page.extract_text() for page in reader.pages)
    for required in ("Contrat été", "cabinet@example.test", "elodie@example.test", "2026-10-23", "Échéance reçue", "Élodie"):
        assert required in text


def test_export_keeps_originals_collision_safe_and_idempotent(tmp_path):
    message = mail()
    message.add_attachment(b"one", maintype="application", subtype="octet-stream", filename="../../same.bin")
    message.add_attachment(b"two", maintype="application", subtype="octet-stream", filename="same.bin")
    existing = tmp_path / "2026-10-23 - Contrat été.pdf"
    existing.write_bytes(b"personal file must survive")
    documents = export_message(message.as_bytes(), tmp_path, "2026-10-23T10:00:00+02:00", identity="source-a")
    assert len(documents) == 3
    assert existing.read_bytes() == b"personal file must survive"
    assert len({doc["path"] for doc in documents}) == 3
    assert documents[0]["printable"] is True
    assert valid_pdf(Path(documents[0]["path"]))
    assert {Path(doc["path"]).read_bytes() for doc in documents[1:]} == {b"one", b"two"}
    assert all(Path(doc["path"]).parent == tmp_path for doc in documents)
    assert all(doc["sha256"] for doc in documents)
    again = export_message(message.as_bytes(), tmp_path, "2026-10-23T10:00:00+02:00", identity="source-a")
    assert [doc["path"] for doc in documents] == [doc["path"] for doc in again]


def test_sent_date_policy_and_unsupported_attachment(tmp_path):
    message = mail()
    message.add_attachment(b"office", maintype="application", subtype="msword", filename="contract.doc")
    docs = export_message(message.as_bytes(), tmp_path, "2026-10-24T10:00:00+02:00", date_source="sent")
    assert all(Path(d["path"]).name.startswith("2026-10-23 - ") for d in docs)
    assert docs[1]["printable"] is False
    with pytest.raises(ValueError):
        convert_for_print(Path(docs[1]["path"]))


def test_print_conversion_images_and_text_and_corrupt_pdf(tmp_path):
    image = tmp_path / "scan.png"
    Image.new("RGB", (120, 80), "white").save(image)
    text = tmp_path / "notes.txt"
    text.write_text("Élodie : document reçu.", encoding="utf-8")
    for original in (image, text):
        converted = convert_for_print(original, tmp_path / "print")
        assert valid_pdf(converted)
        assert original.exists()
    pdf = tmp_path / "bad.pdf"
    pdf.write_bytes(b"%PDF-1.4\ninvalid")
    assert not valid_pdf(pdf)
    with pytest.raises(ValueError):
        convert_for_print(pdf)


def test_export_rejects_bad_options_without_files(tmp_path):
    with pytest.raises(ValueError):
        export_message(mail().as_bytes(), tmp_path, date_source="random")
    assert not list(tmp_path.iterdir())


def test_received_date_falls_back_to_mail_date():
    parsed = parse_message(mail().as_bytes(), "invalid")
    assert parsed["date"] == "2026-10-23T14:30:00+02:00"
    assert parsed["received_date"] is None


def test_pdf_attachment_content_and_inline_choice_are_explicit(tmp_path):
    attachment = tmp_path / "attachment.pdf"
    render_pdf(parse_message(mail().as_bytes()), attachment)
    message = mail()
    message.add_attachment(attachment.read_bytes(), maintype="application", subtype="pdf", filename="devis.pdf")
    message.add_attachment(b"broken", maintype="application", subtype="pdf", filename="broken.pdf")
    message.add_attachment(b"signature", maintype="image", subtype="png", filename="signature.png", disposition="inline")
    documents = export_message(message.as_bytes(), tmp_path / "archive")
    assert documents[1]["printable"] is True
    assert Path(documents[1]["path"]).read_bytes() == attachment.read_bytes()
    assert documents[2]["printable"] is False
    assert documents[3]["inline"] is True


def test_symlink_named_like_export_does_not_touch_target(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    personal = tmp_path / "personal.pdf"
    personal.write_bytes(b"original")
    (archive / "2026-10-23 - Contrat été.pdf").symlink_to(personal)
    documents = export_message(mail().as_bytes(), archive)
    assert personal.read_bytes() == b"original"
    assert Path(documents[0]["path"]).parent == archive
    assert not Path(documents[0]["path"]).is_symlink()


def test_render_never_overwrites_a_different_file(tmp_path):
    path = tmp_path / "personal.pdf"
    path.write_bytes(b"keep")
    with pytest.raises(ValueError):
        render_pdf(parse_message(mail().as_bytes()), path)
    assert path.read_bytes() == b"keep"


def test_nested_email_is_retained_as_eml(tmp_path):
    message = mail()
    nested = mail("Texte du message joint")
    message.add_attachment(nested, filename="forward.eml")
    parsed = parse_message(message.as_bytes())
    assert len(parsed["attachments"]) == 1
    assert parsed["attachments"][0]["name"] == "forward.eml"
    assert b"Texte du message joint" in parsed["attachments"][0]["content"]
    docs = export_message(message.as_bytes(), tmp_path)
    assert docs[1]["printable"] is False
