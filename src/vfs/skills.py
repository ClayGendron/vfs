"""Author Agent Skills as VFS entries.

A :class:`Skill` is the pure, validated value for one Agent Skill — the open
``SKILL.md`` format (https://agentskills.io/specification). It enforces the
spec's naming and length rules at construction, renders the ``SKILL.md``
manifest, and projects to the entry set that materializes the skill under
``/.agents/skills/<name>``:

    Skill(
        name="pdf-processing",
        description="Extract text and fill PDF forms. Use when working with PDFs.",
        instructions="## Steps\\n1. ...",
    ).to_entries()

The skill *directory* is the unit (``kind="skill"``); its ``SKILL.md`` is a
plain indexable file, and any bundled ``scripts``/``references``/``assets`` ride
along as further files. Intermediate directories are materialized by the write
chokepoint, so only the unit directory and the leaf files are emitted here.
"""

from __future__ import annotations

import re

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from vfs.models2 import Entry
from vfs.paths import SKILL_MANIFEST, RelativePath, skill_manifest_path, skill_path

# Constraints from the Agent Skills spec. The name must also match its parent
# directory — free here, since the directory is derived from the name.
NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
NAME_MAX = 64
DESCRIPTION_MAX = 1024
COMPATIBILITY_MAX = 512

# Angle brackets in frontmatter can inject instructions into the system prompt;
# the spec calls them out, so every rendered metadata string rejects them.
_ANGLE_BRACKETS = ("<", ">")


# ---------------------------------------------------------------------------
# Skill value
# ---------------------------------------------------------------------------


class SkillResource(BaseModel):
    """One bundled file in a skill, addressed relative to the skill root.

    ``path`` is a forward-slash relative path (``scripts/extract.py``); it never
    leads with ``/`` and never contains ``.``/``..`` segments, so it cannot
    escape the skill directory when joined onto the root.
    """

    model_config = ConfigDict(frozen=True)

    path: RelativePath
    content: str


class Skill(BaseModel):
    """A pure, validated Agent Skill — renders ``SKILL.md`` and projects to entries.

    Construction enforces the spec: ``name`` matches the naming grammar and is
    1-64 characters; ``description`` is 1-1024 characters; ``compatibility`` is
    1-512; none is blank; and no frontmatter string carries an angle bracket. A frozen
    value object — never bound to storage. ``instructions`` is the Markdown body
    (optional but recommended); ``resources`` are bundled files.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    instructions: str = ""
    license: str | None = None
    compatibility: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)
    resources: tuple[SkillResource, ...] = Field(default_factory=tuple)

    # --- Construction validation --------------------------------------------

    @field_validator("name")
    @classmethod
    def _check_name(cls, value: str) -> str:
        if not (1 <= len(value) <= NAME_MAX) or NAME_PATTERN.fullmatch(value) is None:
            msg = (
                f"name must be 1-{NAME_MAX} chars of lowercase letters, digits, and single "
                f"hyphens (no leading/trailing/consecutive hyphens): {value!r}"
            )
            raise ValueError(msg)
        return value

    @field_validator("description")
    @classmethod
    def _check_description(cls, value: str) -> str:
        if not (1 <= len(value) <= DESCRIPTION_MAX):
            msg = f"description must be 1-{DESCRIPTION_MAX} characters, got {len(value)}"
            raise ValueError(msg)
        return value

    @field_validator("compatibility")
    @classmethod
    def _check_compatibility(cls, value: str | None) -> str | None:
        if value is not None and len(value) > COMPATIBILITY_MAX:
            msg = f"compatibility must be at most {COMPATIBILITY_MAX} characters, got {len(value)}"
            raise ValueError(msg)
        return value

    @field_validator("description", "license", "compatibility")
    @classmethod
    def _reject_blank(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is not None and not value.strip():
            msg = f"{info.field_name} must not be blank"
            raise ValueError(msg)
        return value

    @field_validator("description", "license", "compatibility")
    @classmethod
    def _no_angle_brackets(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is not None:
            _reject_angle_brackets(value, info.field_name or "field")
        return value

    @field_validator("metadata")
    @classmethod
    def _metadata_no_angle_brackets(cls, value: dict[str, str]) -> dict[str, str]:
        for key, val in value.items():
            _reject_angle_brackets(key, "metadata key")
            _reject_angle_brackets(val, "metadata value")
        return value

    @model_validator(mode="after")
    def _validate_resources(self) -> Skill:
        """Resources must not shadow the manifest, and their paths must be distinct.

        Paths are already canonical ``RelativePath`` values, so ``scripts//x`` and
        ``scripts/x`` collide as the same resource and are rejected, not silently
        last-writer-wins at materialization.
        """
        seen: set[str] = set()
        for resource in self.resources:
            if resource.path == SKILL_MANIFEST:
                msg = f"resource path collides with the manifest file {SKILL_MANIFEST!r}"
                raise ValueError(msg)
            if resource.path in seen:
                msg = f"duplicate resource path: {resource.path!r}"
                raise ValueError(msg)
            seen.add(resource.path)
        return self

    # --- Rendering and projection -------------------------------------------

    def render_manifest(self) -> str:
        """Render the ``SKILL.md`` text: YAML frontmatter then the Markdown body.

        Only populated fields appear, in spec order; the body is omitted when
        blank. Angle brackets are re-screened here, not only at construction: a
        frozen model's ``metadata`` dict stays mutable, so the guard is
        re-applied at the render sink.
        """
        for label, value in (
            ("name", self.name),
            ("description", self.description),
            ("license", self.license),
            ("compatibility", self.compatibility),
        ):
            if value is not None:
                _reject_angle_brackets(value, label)
        for meta_key, meta_value in self.metadata.items():
            _reject_angle_brackets(meta_key, "metadata key")
            _reject_angle_brackets(meta_value, "metadata value")

        front: dict[str, object] = {"name": self.name, "description": self.description}
        if self.license is not None:
            front["license"] = self.license
        if self.compatibility is not None:
            front["compatibility"] = self.compatibility
        if self.metadata:
            front["metadata"] = dict(self.metadata)

        dumped = yaml.safe_dump(front, sort_keys=False, default_flow_style=False, allow_unicode=True).rstrip("\n")
        manifest = f"---\n{dumped}\n---\n"
        body = self.instructions.strip("\n")
        if body:
            manifest += f"\n{body}\n"
        return manifest

    def to_entries(self) -> list[Entry]:
        """Project to the entries that create this skill, unit directory first.

        The unit directory is ``kind="skill"`` and carries the skill's
        ``description``; the ``SKILL.md`` manifest and every bundled resource are
        ordinary indexable files under it.
        """
        root = skill_path(self.name)
        entries = [
            Entry(path=root, kind="skill", description=self.description),
            Entry(path=skill_manifest_path(self.name), kind="file", content=self.render_manifest()),
        ]
        for resource in self.resources:
            entry_path = root.joinpath(resource.path)
            if not entry_path.startswith(root + "/"):
                msg = f"resource {resource.path!r} escapes the skill directory: {entry_path}"
                raise ValueError(msg)
            entries.append(Entry(path=entry_path, kind="file", content=resource.content))
        return entries


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _reject_angle_brackets(value: str, label: str) -> None:
    """Reject angle brackets in a frontmatter string — a prompt-injection vector."""
    if any(ch in value for ch in _ANGLE_BRACKETS):
        msg = f"{label} must not contain angle brackets (prompt-injection risk)"
        raise ValueError(msg)
