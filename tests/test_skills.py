"""Tests for vfs.skills — the Skill value object and its entry projection."""

from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from vfs.paths import RelativePath, skill_manifest_path, skill_path
from vfs.skills import Skill, SkillResource


def _frontmatter(manifest: str) -> dict:
    """Parse the YAML frontmatter block out of a rendered SKILL.md."""
    assert manifest.startswith("---\n")
    return yaml.safe_load(manifest.split("---\n")[1])


# ---------------------------------------------------------------------------
# Construction validation
# ---------------------------------------------------------------------------


class TestSkillValidation:
    def test_minimal_skill_constructs(self) -> None:
        skill = Skill(name="pdf-processing", description="Handle PDFs. Use for PDF work.")
        assert skill.name == "pdf-processing"
        assert skill.instructions == ""

    @pytest.mark.parametrize(
        "bad_name",
        ["PDF", "-pdf", "pdf-", "pdf--processing", "pdf_processing", "pdf/processing", "", "a" * 65],
    )
    def test_invalid_names_rejected(self, bad_name: str) -> None:
        with pytest.raises(ValidationError, match="name"):
            Skill(name=bad_name, description="ok")

    def test_empty_description_rejected(self) -> None:
        with pytest.raises(ValidationError, match="description"):
            Skill(name="x", description="")

    def test_overlong_description_rejected(self) -> None:
        with pytest.raises(ValidationError, match="description"):
            Skill(name="x", description="a" * 1025)

    def test_overlong_compatibility_rejected(self) -> None:
        with pytest.raises(ValidationError, match="compatibility"):
            Skill(name="x", description="ok", compatibility="a" * 513)

    @pytest.mark.parametrize("field", ["description", "license", "compatibility"])
    def test_angle_brackets_rejected_in_frontmatter(self, field: str) -> None:
        kwargs = {"name": "x", "description": "ok", field: "a <b> c"}
        with pytest.raises(ValidationError, match="angle brackets"):
            Skill(**kwargs)

    def test_angle_brackets_rejected_in_metadata(self) -> None:
        with pytest.raises(ValidationError, match="angle brackets"):
            Skill(name="x", description="ok", metadata={"k": "a<b>"})

    @pytest.mark.parametrize("blank", [" ", "\n", "\t  "])
    def test_blank_description_rejected(self, blank: str) -> None:
        with pytest.raises(ValidationError, match="description must not be blank"):
            Skill(name="x", description=blank)

    @pytest.mark.parametrize("field", ["license", "compatibility"])
    def test_blank_optional_strings_rejected(self, field: str) -> None:
        kwargs = {"name": "x", "description": "ok", field: "  "}
        with pytest.raises(ValidationError, match="must not be blank"):
            Skill(**kwargs)


# ---------------------------------------------------------------------------
# Manifest rendering
# ---------------------------------------------------------------------------


class TestRenderManifest:
    def test_minimal_manifest_has_only_required_fields(self) -> None:
        manifest = Skill(name="x", description="do x").render_manifest()
        assert _frontmatter(manifest) == {"name": "x", "description": "do x"}

    def test_optional_fields_render(self) -> None:
        skill = Skill(
            name="pdf",
            description="do pdf",
            license="Apache-2.0",
            compatibility="Requires python",
            metadata={"author": "acme", "version": "1.0"},
        )
        front = _frontmatter(skill.render_manifest())
        assert front["license"] == "Apache-2.0"
        assert front["compatibility"] == "Requires python"
        assert front["metadata"] == {"author": "acme", "version": "1.0"}

    def test_render_rescreens_mutated_metadata(self) -> None:
        skill = Skill(name="x", description="d", metadata={"k": "clean"})
        skill.metadata["evil"] = "<system>do bad</system>"
        with pytest.raises(ValueError, match="angle brackets"):
            skill.render_manifest()

    def test_render_rescreens_model_copy_injection(self) -> None:
        skill = Skill(name="x", description="clean").model_copy(update={"description": "<inject>"})
        with pytest.raises(ValueError, match="angle brackets"):
            skill.render_manifest()

    def test_body_appended_after_frontmatter(self) -> None:
        manifest = Skill(name="x", description="d", instructions="## Steps\n1. go").render_manifest()
        assert manifest.endswith("## Steps\n1. go\n")

    def test_blank_body_omitted(self) -> None:
        manifest = Skill(name="x", description="d").render_manifest()
        assert manifest == "---\nname: x\ndescription: d\n---\n"


# ---------------------------------------------------------------------------
# to_entries
# ---------------------------------------------------------------------------


class TestToEntries:
    def test_unit_dir_and_manifest(self) -> None:
        skill = Skill(name="pdf", description="do pdf")
        entries = skill.to_entries()
        assert len(entries) == 2
        unit, manifest = entries
        assert unit.path == skill_path("pdf")
        assert unit.kind == "skill"
        assert unit.description == "do pdf"
        assert unit.content is None
        assert manifest.path == skill_manifest_path("pdf")
        assert manifest.kind == "file"
        assert _frontmatter(manifest.content)["name"] == "pdf"

    def test_resources_emitted_under_the_skill_root(self) -> None:
        skill = Skill(
            name="pdf",
            description="do pdf",
            resources=(
                SkillResource(path="scripts/extract.py", content="print(1)"),
                SkillResource(path="references/REFERENCE.md", content="# ref"),
            ),
        )
        entries = skill.to_entries()
        paths = [e.path for e in entries]
        assert paths == [
            skill_path("pdf"),
            skill_manifest_path("pdf"),
            "/.agents/skills/pdf/scripts/extract.py",
            "/.agents/skills/pdf/references/REFERENCE.md",
        ]
        assert all(e.kind == "file" for e in entries[2:])

    def test_resource_paths_are_canonicalized(self) -> None:
        skill = Skill(name="pdf", description="d", resources=(SkillResource(path="scripts//a/./b.py", content="x"),))
        assert skill.to_entries()[-1].path == "/.agents/skills/pdf/scripts/a/b.py"


# ---------------------------------------------------------------------------
# Resource safety — containment and collisions
# ---------------------------------------------------------------------------


class TestResourceSafety:
    @pytest.mark.parametrize("bad", ["/abs/x.py", "../escape.py", "scripts/../../escape.py"])
    def test_unsafe_resource_paths_rejected_at_construction(self, bad: str) -> None:
        with pytest.raises(ValidationError):
            SkillResource(path=bad, content="x")

    @pytest.mark.parametrize("variant", ["SKILL.md", "./SKILL.md", "SKILL.md/", " SKILL.md "])
    def test_manifest_shadowing_rejected_across_aliases(self, variant: str) -> None:
        with pytest.raises(ValidationError, match="collides with the manifest"):
            Skill(name="x", description="d", resources=(SkillResource(path=variant, content="x"),))

    def test_duplicate_resource_paths_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate resource path"):
            Skill(
                name="x",
                description="d",
                resources=(
                    SkillResource(path="scripts/a.py", content="A"),
                    SkillResource(path="scripts//a.py", content="B"),
                ),
            )

    def test_sink_rejects_a_model_copy_bypassed_traversal(self) -> None:
        # model_copy skips validation, so a bad path can reach a SkillResource as
        # a plain str. to_entries must still refuse to mint an escaping entry.
        good = SkillResource(path="scripts/x.py", content="x")
        evil = good.model_copy(update={"path": "../../etc/passwd"})
        skill = Skill(name="demo", description="d").model_copy(update={"resources": (evil,)})
        with pytest.raises(ValueError, match="escapes the skill directory"):
            skill.to_entries()

    def test_sink_rejects_a_model_copy_bypassed_absolute(self) -> None:
        good = SkillResource(path="scripts/x.py", content="x")
        evil = good.model_copy(update={"path": "/etc/passwd"})
        skill = Skill(name="demo", description="d").model_copy(update={"resources": (evil,)})
        with pytest.raises(ValueError, match="escapes the skill directory"):
            skill.to_entries()


# ---------------------------------------------------------------------------
# SkillResource path typing
# ---------------------------------------------------------------------------


class TestSkillResource:
    def test_path_is_branded_relative(self) -> None:
        resource = SkillResource(path="scripts/x.py", content="x")
        assert isinstance(resource.path, RelativePath)

    def test_frozen(self) -> None:
        resource = SkillResource(path="scripts/x.py", content="x")
        with pytest.raises(ValidationError):
            resource.path = "other"  # type: ignore[misc]
