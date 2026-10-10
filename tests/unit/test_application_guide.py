import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "application-guide.md"


def test_application_guide_internal_markdown_links_resolve():
    content = GUIDE.read_text(encoding="utf-8")
    targets = re.findall(r"\[[^\]]+\]\(([^)]+)\)", content)

    local_targets = [
        target.split("#", maxsplit=1)[0]
        for target in targets
        if target and not target.startswith(("http://", "https://"))
    ]

    assert local_targets
    assert all((GUIDE.parent / target).exists() for target in local_targets)


def test_application_guide_fenced_code_blocks_are_balanced():
    content = GUIDE.read_text(encoding="utf-8")
    fences = [line for line in content.splitlines() if line.startswith("```")]

    assert fences
    assert len(fences) % 2 == 0
    assert "```mermaid" in fences


def test_application_guide_example_scenarios_exist_and_are_valid():
    content = GUIDE.read_text(encoding="utf-8")
    scenario_paths = set(re.findall(r"examples/[\w-]+\.json", content))

    assert scenario_paths == {
        "examples/greenfield.json",
        "examples/brownfield.json",
        "examples/ambiguous.json",
    }
    for scenario_path in scenario_paths:
        scenario = json.loads((ROOT / scenario_path).read_text(encoding="utf-8"))
        assert isinstance(scenario.get("requirement"), str)
        assert scenario["requirement"].strip()


def test_application_guide_inventories_source_and_test_modules():
    content = GUIDE.read_text(encoding="utf-8")
    modules = [
        *((ROOT / "src" / "agentic_engineer").rglob("*.py")),
        *((ROOT / "tests").rglob("*.py")),
    ]

    undocumented = []
    for path in modules:
        if path.name == "__init__.py":
            continue
        if path.is_relative_to(ROOT / "src" / "agentic_engineer"):
            documented_path = path.relative_to(ROOT / "src" / "agentic_engineer").as_posix()
        else:
            documented_path = path.relative_to(ROOT).as_posix()
        if documented_path not in content:
            undocumented.append(documented_path)

    assert not undocumented, f"Modules missing from guide: {undocumented}"