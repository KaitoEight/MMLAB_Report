from datetime import date, datetime
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Member = Annotated[int, Field(strict=True, ge=1, le=12)]
Count = Annotated[int, Field(strict=True, ge=0, le=1000000)]


class DoneTask(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    date: str
    content: str


class MonthlyTasks(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    done: list[DoneTask] | None = None
    planned: list[str] | None = None


class Report(BaseModel):
    model_config = ConfigDict(strict=True, extra='allow')
    id: str = Field(min_length=1, max_length=300)
    date: str
    memberId: Member | None
    type: Literal['Paper', 'Đề tài', 'NCS', 'Seminar', 'Giải thưởng', 'Báo cáo tháng']
    title: str = Field(min_length=1, max_length=10000)
    status: str = Field(max_length=300)
    role: str = Field(max_length=300)
    authors: str = Field(max_length=30000)
    venue: str = Field(max_length=3000)
    ranking: str = Field(max_length=300)
    index: str | None
    memberIds: list[Member] = Field(max_length=12)
    source: Literal['gmail']
    forwarded: bool
    issues: list[str] = Field(max_length=200)
    sourceId: str = Field(min_length=1, max_length=1000)
    isValid: bool
    messageId: str = Field(default='', max_length=1000)
    warnings: list[str] = Field(default_factory=list, max_length=200)
    missingFields: list[str] = Field(default_factory=list, max_length=100)
    monthlyTasks: MonthlyTasks | None = None
    reportPeriod: str | None = Field(default=None, pattern=r'^\d{4}-(0[1-9]|1[0-2])$')

    @field_validator('date')
    @classmethod
    def valid_date(cls, value):
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError('Ngày phải có dạng YYYY-MM-DD.')
        return value

    @field_validator('memberIds')
    @classmethod
    def unique_members(cls, value):
        if len(value) != len(set(value)):
            raise ValueError('Thành viên trùng.')
        return value


class Summary(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    inbox_messages: Count
    processed: Count
    forwarded: Count
    reports: Count
    valid: Count
    invalid: Count
    ignored: Count
    review: Count
    errors: Count


class Bundle(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    schema_version: Literal['mmlab-imap-export/1']
    mailbox: str = Field(min_length=3, max_length=254)
    folder: str = Field(min_length=1, max_length=1000)
    uid_validity: str = Field(pattern=r'^\d+$')
    generated_at: str
    summary: Summary
    reports: list[Report] = Field(max_length=5000)
    review_candidates: list[dict] = Field(max_length=5000)
    errors: list[dict] = Field(max_length=5000)

    @model_validator(mode='after')
    def consistency(self):
        if datetime.fromisoformat(self.generated_at).tzinfo is None:
            raise ValueError('generated_at thiếu timezone.')
        s = self.summary
        if (s.reports != len(self.reports) or s.valid != sum(r.isValid for r in self.reports)
            or s.invalid != s.reports - s.valid or s.review != len(self.review_candidates)
            or s.errors != len(self.errors) or s.processed != s.reports + s.review + s.ignored
            or s.inbox_messages != s.processed + s.errors or s.forwarded > s.processed):
            raise ValueError('Số liệu tổng không khớp với dữ liệu.')
        prefix = f'imap:{self.mailbox}:{self.folder}:{self.uid_validity}:'
        ids = [r.sourceId for r in self.reports]
        if len(ids) != len(set(ids)) or any(not i.startswith(prefix) or not i[len(prefix):].isdigit() for i in ids):
            raise ValueError('UID trùng hoặc không thuộc hộp thư/thư mục.')
        return self
