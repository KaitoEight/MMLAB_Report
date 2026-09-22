"""Email text extraction, provenance and validation. All input is untrusted text."""
from __future__ import annotations

import html
import re
import unicodedata
from datetime import datetime, timezone, timedelta
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser

from pydantic import ValidationError

from .members import fold, member_matches, sender_matches
from .validator import LABELS, WorkReport, MilestoneReport, MonthlyReport, report_type
from .tasks import task_lines, repair_tasks

MAX_BODY_CHARS = 1_000_000
MAX_EML_BYTES = 10_000_000
FORWARD_RE = re.compile(
    r"^-*\s*(?:forwarded message|original message|thu duoc chuyen tiep|thu da chuyen tiep|thu chuyen tiep)\s*-*$"
    r"|^begin forwarded message\s*:$|^on .+wrote\s*:$", re.I)
KEY_RE = re.compile(r"^\s*(?P<open>\*{1,2}|_{1,2})?\s*(?P<label>"
                    + "|".join(re.escape(k).replace(r"\ ", r"\s+") for k in LABELS.values())
                    + r")\s*(?:\*{1,2}|_{1,2})?\s*:\s*(?P<close>\*{1,2}|_{1,2})?\s*(?P<value>.*)$", re.I)
LABEL_TO_KEY = {fold(v).casefold(): k for k, v in LABELS.items()}


class _HTMLText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self.skip += 1
        if self.skip:
            return
        attrs = dict(attrs)
        if tag == "blockquote" or "gmail_quote" in attrs.get("class", "").split():
            self.parts.append("\n---------- Forwarded message ---------\n")
        if tag in ("br", "p", "div", "li", "tr", "table"):
            self.parts.append("\n")
        elif tag in ("td", "th"):
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head"):
            self.skip = max(0, self.skip - 1)
        if not self.skip and tag in ("p", "div", "li", "tr", "table"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def normalize_body(body: str) -> str:
    # Do not feed a plain mailbox <someone@host> to an HTML parser.
    if re.search(r"<(?:html|body|div|p|br|table|span|b|strong|i|em)\b[^>]*>", body, re.I):
        parser = _HTMLText()
        parser.feed(body)
        body = "".join(parser.parts)
    body = html.unescape(body)
    body = re.sub(r"\\([@.<>\-])", r"\1", body)  # Escaped Markdown email copy.
    return unicodedata.normalize("NFC", body).replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")


def clean_line(line: str) -> str:
    return re.sub(r"^\s*(?:>\s*)+", "", line).strip()


def key_value(line: str):
    match = KEY_RE.match(line)
    if not match:
        return None
    label = fold(re.sub(r"\s+", " ", match["label"]))
    value = match["value"].strip()
    opener = match["open"]
    if opener and not match["close"] and value.endswith(opener):
        value = value[:-len(opener)].strip()
    return LABEL_TO_KEY[label], value


def split_segments(text: str) -> list[dict]:
    segments = [{"lines": [], "sender": None, "depth": 0}]
    lines = text.splitlines()
    for index, raw in enumerate(lines):
        line = clean_line(raw)
        if FORWARD_RE.search(fold(line)):
            segments.append({"lines": [], "sender": None, "depth": len(segments)})
            continue
        # Outlook sometimes omits the dashed separator but retains a header run.
        if re.match(r"^(?:From|Từ)\s*:", line, re.I):
            following = [clean_line(x) for x in lines[index + 1:index + 7]]
            headers = [x for x in following if re.match(r"^(?:Sent|Date|To|Subject|Đến|Ngày|Chủ đề)\s*:", x, re.I)]
            already_at_forward_header = segments[-1]["depth"] and not any(x.strip() for x in segments[-1]["lines"])
            if len(headers) >= 2 and not already_at_forward_header:
                segments.append({"lines": [], "sender": None, "depth": len(segments)})
        segment = segments[-1]
        segment["lines"].append(line)
        # Only a leading forwarded header is identity evidence; never arbitrary From in prose.
        if segment["depth"] and segment["sender"] is None and len(segment["lines"]) <= 8:
            match = re.match(r"^(?:From|Từ)\s*:\s*(.+)$", line, re.I)
            if match:
                segment["sender"] = match[1].replace("**", "").strip()
    return segments


def extract(segment: dict):
    fields, occurrences, errors, extras = {}, {}, [], []
    current = None
    started = False
    for number, line in enumerate(segment["lines"], 1):
        if line in ("--", "-- ") or re.match(r"^(?:Sent from my|Gửi từ)\b", line, re.I):
            break
        item = key_value(line)
        if item:
            key, value = item
            started = True
            occurrences.setdefault(key, []).append({"line": number, "value": value})
            if key in fields:
                if key in ("done", "planned"):
                    fields[key] += "\n" + value
                    current = key
                    continue
                errors.append({"field": LABELS[key], "value": value,
                               "reason": "Trường xuất hiện nhiều lần; không tự chọn hoặc gộp giá trị"})
                current = None
                continue
            fields[key] = value
            current = key
            continue
        if current in ("done", "planned") and line:
            # Seminar: and similar prose labels belong to a monthly task.
            fields[current] += "\n" + line
        elif started and re.match(r"^[A-Za-z][A-Za-z ]{1,30}\s*:", line):
            extras.append(line)
            current = None
        elif current in ("title", "authors", "venue") and line:
            fields[current] += " " + line
        elif current in ("done", "planned") and line:
            fields[current] += "\n" + line
        elif not line:
            # Permit blank lines within monthly blocks; don't consume signatures into a title.
            if current not in ("done", "planned"):
                current = None
    return fields, occurrences, errors, extras


def _append_errors(result: dict, exc: ValidationError):
    for error in exc.errors(include_url=False, include_context=False):
        location = error["loc"]
        key = location[0] if location else "report"
        field = LABELS.get(key, str(key))
        if len(location) > 1:
            field += "." + ".".join(str(x) for x in location[1:])
        if error["type"] in ("missing", "required_empty") or (
                len(location) == 1 and isinstance(error.get("input"), str) and not error["input"].strip()):
            if field not in result["missing_fields"]:
                result["missing_fields"].append(field)
        else:
            result["invalid_fields"].append({"field": field, "value": error.get("input"),
                                              "reason": error["msg"]})


def parse_and_validate_email(subject: str, body: str, sender: str, *, received_at: str | None = None) -> dict:
    result = {"sender": sender, "is_valid": False, "category": None, "data": {},
              "credited_members": [], "missing_fields": [], "invalid_fields": [],
              "warnings": [], "kpi_eligible": False, "ready_for_kpi": False,
              "needs_review": False, "mapping_evidence": [], "provenance": {},
              "schema_version": "1.0.0"}
    for key, value in (("Subject", subject), ("body", body), ("Sender", sender)):
        if not isinstance(value, str):
            result["invalid_fields"].append({"field": key, "value": repr(value), "reason": "Phải là str"})
    if result["invalid_fields"]:
        return result
    if len(body) > MAX_BODY_CHARS or len(subject) > 10_000 or len(sender) > 10_000:
        result["invalid_fields"].append({"field": "email", "value": None, "reason": "Email vượt giới hạn kích thước"})
        return result
    if any(c in body + sender for c in ("\u200b", "\u200c", "\u200d", "\ufeff")):
        result["warnings"].append("Có ký tự ẩn trong nội dung; cần kiểm tra danh tính thủ công")
        result["needs_review"] = True
    segments = split_segments(normalize_body(body))
    extracted = [(s, extract(s)) for s in segments]
    candidates = [(s, x) for s, x in extracted if any(k in x[0] for k in ("report_type", "done", "planned"))]
    if len(candidates) > 1:
        result["warnings"].append("Có nhiều khối báo cáo trong chuỗi forward; chỉ đọc khối đầu, cần duyệt")
        result["needs_review"] = True
    segment, (fields, occurrences, extraction_errors, extras) = (candidates or extracted)[0]
    result["provenance"] = {"segment_depth": segment["depth"], "field_occurrences": occurrences,
                            "report_sender": segment["sender"] if segment["depth"] else sender}
    kind = report_type(fields.get("report_type", ""))
    monthly = "bao cao thang" in fold(subject) or "done" in fields or "planned" in fields or fold(kind) in ("bao cao thang", "monthly report")
    monthly_only = monthly and kind not in ("Paper", "Đề tài", "NCS", "Seminar", "Giải thưởng")
    # Paper metadata does not belong to monthly validation, even when supplied.
    result["invalid_fields"].extend(e for e in extraction_errors
                                  if not monthly_only or e["field"] in ("Đã", "Sẽ"))
    if extras and not monthly_only:
        result["warnings"].append("Có nhãn ngoài schema: " + "; ".join(extras))
        result["needs_review"] = True
    if segment["depth"]:
        result["warnings"].append("Báo cáo lấy từ phần forward; header From bên trong là dữ liệu chưa xác thực")
        result["needs_review"] = True
    evidence = []
    model = None
    payload = dict(fields)
    context = {}
    if kind in ("Paper", "Đề tài"):
        result["category"] = "Paper" if kind == "Paper" else "Project"
        payload.pop('subject', None)  # A forwarded Subject is metadata, not a Paper field.
        model = WorkReport
        evidence = member_matches(fields.get("authors", ""), "All authors")
        if monthly:
            result["invalid_fields"].append({"field": "Type of Report", "value": kind,
                                               "reason": "Xung đột loại báo cáo với Subject hoặc block tháng"})
        if not fields.get("ranking", "").strip():
            payload.pop("ranking", None)
        result["warnings"].append("Index/Ranking mới được kiểm tra cú pháp, chưa xác minh nguồn bên ngoài")
        result["warnings"].append("Role là vai trò khai báo của báo cáo; chưa xác định vai trò riêng từng thành viên")
    elif kind in ("NCS", "Seminar", "Giải thưởng"):
        result["category"], model = "Milestone", MilestoneReport
        payload = {k:v for k,v in fields.items() if k in ("report_type", "title")}
        title_hits = member_matches(fields.get("title", ""), "Title of Work")
        # Only current report segment, excluding headers and the standard signature separator.
        narrative = []
        for line in segment["lines"]:
            if line == "--" or re.match(r"^(?:Sent from my|Gửi từ)\b", line, re.I):
                break
            if not key_value(line) and not re.match(r"^(?:From|To|Cc|Subject|Date)\s*:", line, re.I):
                narrative.append(line)
        body_hits = member_matches("\n".join(narrative), "body")
        owner_hits = sender_matches(segment["sender"] or "", "forwarded.From") if segment["depth"] else sender_matches(sender)
        evidence = title_hits + body_hits + owner_hits
        if evidence:
            result["needs_review"] = True
            result["warnings"].append("NCS/Seminar/Giải thưởng: nhắc tên hoặc gửi email chưa chứng minh người thực hiện; cần duyệt")
        if monthly:
            result["invalid_fields"].append({"field": "Type of Report", "value": kind,
                                               "reason": "Xung đột loại báo cáo với báo cáo tháng"})
    elif monthly:
        result["category"], model = "Monthly Report", MonthlyReport
        payload = {"subject": subject, "done": None, "planned": None}
        if "report_type" in fields and fold(kind) not in ("bao cao thang", "monthly report"):
            result["invalid_fields"].append({"field": "Type of Report", "value": kind,
                                               "reason": "Type of Report không hợp lệ trong báo cáo tháng"})
        # Reporting period comes only from the mailbox reception timestamp.
        if received_at:
            stamp = datetime.fromisoformat(received_at)
            if stamp.tzinfo is None:
                raise ValueError("received_at must include timezone")
            stamp = stamp.astimezone(timezone(timedelta(hours=7)))
            context = {"year": stamp.year}
            result["provenance"]["report_month"] = stamp.strftime("%Y-%m")
        if "done" in fields:
            payload["done"] = repair_tasks(fields["done"].splitlines())
        if "planned" in fields:
            payload["planned"] = task_lines(fields["planned"])
        evidence = sender_matches(segment["sender"] or "", "forwarded.From") if segment["depth"] else sender_matches(sender)
        if not evidence:
            result["invalid_fields"].append({"field": "Sender", "value": result["provenance"]["report_sender"],
                                               "reason": "Báo cáo tháng phải map được mailbox người báo cáo vào danh sách lab"})
    else:
        if not kind:
            result["missing_fields"].append("Type of Report")
        else:
            result["invalid_fields"].append({"field": "Type of Report", "value": kind,
                                               "reason": "Loại báo cáo không nằm trong enum"})
        if not fields.get("title", "").strip():
            result["missing_fields"].append("Title of Work")
    result["data"] = payload
    if model:
        try:
            validated = model.model_validate(payload, context=context)
            result["data"] = validated.model_dump(mode="json")
        except ValidationError as exc:
            _append_errors(result, exc)
    result["mapping_evidence"] = evidence
    result["credited_members"] = sorted({e["member"]["id"]: e["member"] for e in evidence}.values(), key=lambda m: m["id"])
    result["kpi_eligible"] = bool(result["credited_members"])
    if not result["kpi_eligible"]:
        result["warnings"].append("Không xác định được thành viên lab từ nguồn đối soát hợp lệ; kpi_eligible=False")
    result["is_valid"] = not result["missing_fields"] and not result["invalid_fields"]
    result["ready_for_kpi"] = result["is_valid"] and result["kpi_eligible"] and not result["needs_review"]
    return result


def parse_eml(raw: bytes) -> dict:
    """Decode MIME charset/transfer-encoding; attachments never enter the report parser."""
    if len(raw) > MAX_EML_BYTES:
        raise ValueError("EML vượt giới hạn 10 MB")
    message = BytesParser(policy=policy.default).parsebytes(raw)
    part = message.get_body(preferencelist=("plain", "html"))
    body = part.get_content() if part else ""
    if not body.strip():
        html_part = message.get_body(preferencelist=("html",))
        if html_part:
            body = html_part.get_content()
    result = parse_and_validate_email(str(message.get("Subject", "")), body, str(message.get("From", "")))
    result["provenance"]["message_id"] = str(message.get("Message-ID", ""))
    defects = [type(defect).__name__ for p in message.walk() for defect in p.defects]
    if defects or len(message.get_all("From", [])) != 1 or len(message.get_all("Subject", [])) != 1:
        result["needs_review"] = True
        result["ready_for_kpi"] = False
        result["warnings"].append("MIME/header không chuẩn hoặc lặp; cần duyệt: " + ", ".join(defects))
    return result
