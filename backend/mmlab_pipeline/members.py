"""Deterministic membership resolution. No fuzzy matching or sender-domain gate."""
from __future__ import annotations

import re
import unicodedata
from email.utils import getaddresses

MEMBERS = (
    (1, "Nguyễn Vinh Tiệp", "Vinh-Tiep Nguyen", "tiepnv@uit.edu.vn"),
    (2, "Đặng Văn Thìn", "Thin Dang|Dang Van Thin|Dang Thin", "thindv@uit.edu.vn"),
    (3, "Nguyễn Đức Vũ", "Duc-Vu Nguyen", "vund@uit.edu.vn"),
    (4, "Nguyễn Ngọc Thừa", "Ngoc-Thua Nguyen|Thua Nguyen", "thuann@uit.edu.vn"),
    (5, "Lưu Đức Tuấn", "Duc-Tuan Luu", "tuanld@uit.edu.vn"),
    (6, "Nguyễn Thành Danh", "Thanh-Danh Nguyen", "danhnt@uit.edu.vn"),
    (7, "Chế Quang Huy", "Quang-Huy Che|Huy Che", "huycq@uit.edu.vn"),
    (8, "Trương Quốc Trường", "Quoc-Truong Truong", "truongtq@uit.edu.vn"),
    (9, "Trần Gia Nghĩa", "Gia-Nghia Tran", "nghiatg@uit.edu.vn"),
    (10, "Đàm Vũ Trọng Tài", "Trong-Tai Dam Vu", "taidvt@uit.edu.vn"),
    (11, "Phạm Thị Bích Nga", "Bich-Nga Pham", "ngaptb@uit.edu.vn"),
    (12, "Nguyễn Duy Tâm Anh", "Tam-Anh Nguyen Duy", "anhntd@uit.edu.vn"),
)
DIRECTORY = tuple({"id": i, "name": name, "aliases": aliases.split("|"), "email": email}
                  for i, name, aliases, email in MEMBERS)
EMAIL_RE = re.compile(r"[\w.!#$%&'*+/=?^`{|}~+-]+@[\w.-]+", re.UNICODE)


def fold(text: str) -> str:
    """Accent/case normalization; đ is not decomposed by NFKD."""
    text = unicodedata.normalize("NFKD", text).casefold().replace("đ", "d")
    return "".join(c for c in text if not unicodedata.combining(c))


def normalized_name(text: str) -> str:
    return re.sub(r"[\s\-‐‑‒–—]+", " ", fold(text)).strip()


def public_member(member: dict) -> dict:
    return {k: member[k] for k in ("id", "name", "email")}


def member_matches(text: str, source: str = "text") -> list[dict]:
    if not isinstance(text, str):
        raise TypeError("text phải là str")
    # Treat full email tokens atomically; do not match @uit.edu.vn.evil.
    emails = {m.group(0).casefold().rstrip(".") for m in EMAIL_RE.finditer(text)}
    searchable = normalized_name(EMAIL_RE.sub(" ", text))
    hits = []
    for member in DIRECTORY:
        if member["email"] in emails:
            hits.append({"member": public_member(member), "source": source,
                         "method": "exact_email", "matched": member["email"]})
            continue
        for alias in [member["name"], *member["aliases"]]:
            target = re.escape(normalized_name(alias))
            if re.search(r"(?<!\w)" + target + r"(?!\w)", searchable):
                hits.append({"member": public_member(member), "source": source,
                             "method": "normalized_alias", "matched": alias})
                break
    return hits


def resolve_members(text: str) -> list[dict]:
    return [hit["member"] for hit in member_matches(text)]


def sender_matches(sender: str, source: str = "Sender") -> list[dict]:
    """Mailbox only: a forged display name is not identity evidence."""
    addresses = [addr.casefold() for _, addr in getaddresses([sender]) if addr]
    if len(addresses) != 1:
        return []
    return [{"member": public_member(m), "source": source,
             "method": "exact_mailbox", "matched": addresses[0]}
            for m in DIRECTORY if m["email"] == addresses[0]]
