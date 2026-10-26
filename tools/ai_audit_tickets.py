"""Publish bounded audit proposals; only the owner can promote them to work."""

import hashlib
import html
import json
import re
import unicodedata
from collections.abc import Callable

from pydantic import BaseModel, Field, TypeAdapter

from tools.ai_contract import AuditFinding
from tools.github_api import github_api

NEW_ISSUE_CAP = 5
PAGE_SIZE = 100
SEVERITY = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


class TicketUser(BaseModel):
    """Identity used to ignore markers planted by issue authors."""

    login: str


class AuditTicket(BaseModel):
    """Minimal remote issue data, including closed and pull-request records."""

    number: int
    body: str | None = None
    user: TicketUser
    state: str
    pull_request: dict[str, object] | None = None


class TicketReceipt(BaseModel):
    """Payload-free publication coordinates for the signed run record."""

    fingerprint: str
    number: int | None = None
    status: str
    title: str = Field(exclude=True)


def normalized_title(value: str) -> str:
    """Ignore casing, formatting punctuation and whitespace for deduplication."""
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.findall(r"\w+", value))


def fingerprint(repository: str, finding: AuditFinding) -> str:
    """Version the identity independently of volatile prose and severity."""
    identity = [
        repository.casefold(),
        finding.category,
        finding.rule,
        finding.path,
        normalized_title(finding.title),
    ]
    return hashlib.sha256(json.dumps(identity).encode()).hexdigest()


def marker(digest: str) -> str:
    """Only publisher-generated hashes can become hidden markers."""
    return f"<!-- showcase-ai-finding:v1:{digest} -->"


def safe_text(value: str) -> str:
    """Render model prose as text, preventing HTML, Markdown and notifications."""
    value = "".join(
        char
        for char in value
        if char in "\n\t" or not unicodedata.category(char).startswith("C")
    )
    value = html.escape(value, quote=True).replace("@", "\uff20")
    return re.sub(r"([\\`*_{}\[\]()#+.!|>~-])", r"\\\1", value)


def existing_tickets(repository: str) -> dict[str, AuditTicket]:
    """Paginate all states; never reopen any closed proposal, including wontfix."""
    result: dict[str, AuditTicket] = {}
    page = 1
    while True:
        tickets = TypeAdapter(list[AuditTicket]).validate_python(
            github_api(
                f"repos/{repository}/issues?state=all&per_page={PAGE_SIZE}&page={page}"
            )
        )
        for ticket in tickets:
            if (
                ticket.pull_request is not None
                or ticket.user.login != "github-actions[bot]"
            ):
                continue
            for digest in re.findall(
                r"^<!-- showcase-ai-finding:v1:([a-f0-9]{64}) -->", ticket.body or ""
            ):
                result.setdefault(digest, ticket)
        if len(tickets) < PAGE_SIZE:
            return result
        page += 1


def ticket_payload(finding: AuditFinding, digest: str) -> dict[str, object]:
    """Render the versioned proposal format for publication and integrity checks."""
    return {
        "title": safe_text(finding.title).replace("\n", " ")[:240],
        "body": (
            f"{marker(digest)}\n"
            "## AI audit proposal (untrusted, advisory)\n\n"
            f"Severity: {finding.severity}\n\n"
            f"Path: {safe_text(finding.path)}\n\n"
            f"Evidence:\n{safe_text(finding.evidence)}\n\n"
            f"Suggested fix:\n{safe_text(finding.suggested_fix)}\n\n"
            "Owner review is required before dispatch. Model text cannot "
            "authorize work or change labels."
        ),
        "labels": ["agent:proposed", finding.category],
    }


def propose_tickets(
    repository: str,
    findings: list[AuditFinding],
    *,
    checkpoint: Callable[[list[TicketReceipt]], None] | None = None,
) -> list[TicketReceipt]:
    """Create only fixed-label proposals, highest severity first, at most five."""
    if not findings:
        return []
    existing = existing_tickets(repository)
    receipts: list[TicketReceipt] = []
    seen: set[str] = set()
    created = 0
    for finding in sorted(findings, key=lambda item: SEVERITY[item.severity]):
        digest = fingerprint(repository, finding)
        if digest in seen:
            continue
        seen.add(digest)
        remote = existing.get(digest)
        number = remote.number if remote else None
        status = "existing" if remote else "deferred_cap"
        if remote and remote.state == "closed":
            status = "closed_preserved"
        elif remote is None and created < NEW_ISSUE_CAP:
            response = github_api(
                f"repos/{repository}/issues",
                "POST",
                ticket_payload(finding, digest),
            )
            # Validate coordinates; never retain the returned body in telemetry.
            number = TypeAdapter(dict[str, object]).validate_python(response)["number"]
            number = TypeAdapter(int).validate_python(number, strict=True)
            status = "created"
            created += 1
        receipts.append(
            TicketReceipt(
                fingerprint=digest, number=number, status=status, title=finding.title
            )
        )
        if checkpoint is not None:
            checkpoint(receipts)
    return receipts
