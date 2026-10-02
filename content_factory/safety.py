"""Hard post-filters and Stage-1 stubs for content safety."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from content_factory.models import AuditRemark, FactDossier, GeneratedText

# Hard medical/safety patterns (case-insensitive). Direction/style forbidden
# phrases are merged in at runtime.
DEFAULT_MEDICAL_PATTERNS: tuple[str, ...] = (
    r"guaranteed cure",
    r"medical diagnosis",
    r"diagnose yourself",
    r"\bdiagnos(?:e|is|ed)\b",
    r"individual treatment(?: recommendation)?",
    r"personal medical advice",
    r"medical promise",
    r"will cure(?: your)?",
    r"cures? your",
)

URL_RE = re.compile(r"https?://[^\s\)\]\"'<>]+", re.IGNORECASE)


@dataclass
class PostFilterResult:
    passed: bool
    remarks: list[AuditRemark] = field(default_factory=list)
    checklist: dict[str, bool] = field(default_factory=dict)


def check_duplicates_against_published(
    text: GeneratedText,
    direction: str,
) -> tuple[bool, AuditRemark | None]:
    """Stub: published corpus does not exist in Stage 1."""
    _ = (text, direction)
    return True, AuditRemark(
        rule="no_duplicates",
        quote="",
        comment="Skipped: published corpus not available in Stage 1",
    )


def apply_post_filter(
    text: GeneratedText,
    dossier: FactDossier | None,
    *,
    direction: str,
    forbidden_phrases: list[str] | None = None,
) -> PostFilterResult:
    """Hard gate on generator output before human handoff.

    Blocks medical promises/diagnoses/individual recommendations and
    citations that are not present in the fact dossier.
    Duplicate checks are stubbed until a published corpus exists.
    """
    remarks: list[AuditRemark] = []
    full_text = "\n".join(
        part for part in (text.title, text.lead or "", text.body, text.cta or "") if part
    )
    lowered = full_text.lower()

    medical_ok = True
    patterns = list(DEFAULT_MEDICAL_PATTERNS)
    for phrase in forbidden_phrases or []:
        if phrase.strip():
            patterns.append(re.escape(phrase.strip()))

    for pattern in patterns:
        match = re.search(pattern, lowered, flags=re.IGNORECASE)
        if match:
            medical_ok = False
            remarks.append(
                AuditRemark(
                    rule="no_medical_claims",
                    quote=match.group(0),
                    comment="Hard post-filter: medical promise, diagnosis, or individual recommendation",
                )
            )
            break

    facts_ok = True
    dossier_urls = {
        fact.source.url.rstrip("/").lower()
        for fact in (dossier.facts if dossier else [])
        if fact.source and fact.source.url
    }
    if dossier:
        dossier_urls.update(
            source.url.rstrip("/").lower()
            for source in dossier.sources
            if source.url
        )

    cited = [url.rstrip("/").lower() for url in text.sources_cited if url]
    for url in cited:
        if url not in dossier_urls:
            facts_ok = False
            remarks.append(
                AuditRemark(
                    rule="facts_confirmed",
                    quote=url,
                    comment="Hard post-filter: cited source is not in the fact dossier",
                )
            )

    for url in URL_RE.findall(full_text):
        normalized = url.rstrip(".,);]").lower().rstrip("/")
        if normalized not in dossier_urls:
            facts_ok = False
            remarks.append(
                AuditRemark(
                    rule="facts_confirmed",
                    quote=url,
                    comment="Hard post-filter: URL in text has no matching dossier source",
                )
            )
            break

    if dossier and not cited and dossier_urls:
        # Body that asserts facts must cite at least one dossier source.
        facts_ok = False
        remarks.append(
            AuditRemark(
                rule="facts_confirmed",
                quote="",
                comment="Hard post-filter: no sources cited from the fact dossier",
            )
        )

    duplicates_ok, dup_remark = check_duplicates_against_published(text, direction)
    if dup_remark:
        remarks.append(dup_remark)

    passed = medical_ok and facts_ok and duplicates_ok
    return PostFilterResult(
        passed=passed,
        remarks=remarks,
        checklist={
            "no_medical_claims": medical_ok,
            "facts_confirmed": facts_ok,
            "no_duplicates": duplicates_ok,
        },
    )
