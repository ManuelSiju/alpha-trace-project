from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field, EmailStr


class Target(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None
    name: Optional[str] = None
    username: Optional[str] = None
    domain: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    image_path: Optional[str] = None

    def primary_identifier(self) -> str:
        for k in ("email", "username", "phone", "domain", "name", "company"):
            v = getattr(self, k)
            if v:
                return v
        return "unknown"

    def candidate_usernames(self) -> List[str]:
        out: List[str] = []
        if self.username:
            out.append(self.username)
        if self.email and "@" in self.email:
            local = self.email.split("@", 1)[0]
            out.append(local)
            stripped = "".join(c for c in local if c.isalpha())
            if stripped and stripped != local:
                out.append(stripped)
        if self.name:
            n = self.name.lower().strip()
            out.extend([
                n.replace(" ", ""),
                n.replace(" ", "_"),
                n.replace(" ", "."),
                n.replace(" ", "-"),
            ])
        seen = set()
        unique = []
        for u in out:
            if u and u not in seen:
                seen.add(u)
                unique.append(u)
        return unique


class Finding(BaseModel):
    category: str
    source: str
    title: Optional[str] = None
    content: str = ""
    url: Optional[str] = None
    confidence: int = Field(default=50, ge=0, le=100)
    data: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BriefingCategory(BaseModel):
    category: str
    summary: str = ""
    confidence: int = 0
    sources: int = 0
    details: List[str] = Field(default_factory=list)


class Briefing(BaseModel):
    target: str
    overview: str = ""
    categories: List[BriefingCategory] = Field(default_factory=list)
    total_data_points: int = 0
    total_sources: int = 0
    high_confidence_pct: int = 0
    medium_confidence_pct: int = 0
    low_confidence_pct: int = 0
    elapsed_seconds: float = 0.0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    raw_findings: List[Finding] = Field(default_factory=list)

    @classmethod
    def empty(cls, target: str) -> "Briefing":
        return cls(target=target, overview="No findings.")


class SessionRecord(BaseModel):
    session_id: str
    target: Target
    briefing: Optional[Briefing] = None
    chat_history: List[Dict[str, str]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
