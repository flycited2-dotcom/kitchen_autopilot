"""Агенты и команды Claude Code: заголовок читается как YAML, агенты из команд существуют, разрешения на скрипты есть."""
import json
import re

import yaml

from tests.kitchen_fixtures import ROOT

AGENTS = ROOT / ".claude" / "agents"
COMMANDS = ROOT / ".claude" / "commands"


def _front(path):
    return yaml.safe_load(path.read_text(encoding="utf-8").split("---")[1])


def test_agent_frontmatter():
    names = set()
    for path in sorted(AGENTS.glob("*.md")):
        front = _front(path)
        assert front["name"] == path.stem
        assert front["model"] in ("opus", "sonnet")
        assert front["description"].strip()
        names.add(front["name"])
    assert names == {"content-manager", "recipe-developer", "photo-director", "video-producer", "copywriter",
                     "editor", "reporter"}


def test_commands_reference_existing_agents_and_allowed_scripts():
    agents = {path.stem for path in AGENTS.glob("*.md")}
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    allowed = settings["permissions"]["allow"]
    texts = [path.read_text(encoding="utf-8") for path in COMMANDS.glob("*.md")]
    texts += [path.read_text(encoding="utf-8") for path in AGENTS.glob("*.md")]
    for path in COMMANDS.glob("*.md"):
        assert _front(path)["description"].strip()
    for text in texts:
        for script in re.findall(r"python (tools/[a-z_]+\.py)", text):
            assert f"Bash(python {script}:*)" in allowed, script
            assert (ROOT / script).is_file(), script
    mentioned = set(re.findall(r"\b(content-manager|recipe-developer|photo-director|video-producer|copywriter|"
                               r"editor|reporter)\b", "\n".join(texts)))
    assert mentioned <= agents


def _examples(name):
    """JSON-примеры из промпта агента: все объекты, которые начинаются с {"id" и разбираются целиком."""
    text = (AGENTS / f"{name}.md").read_text(encoding="utf-8")
    decoder, found = json.JSONDecoder(), []
    for match in re.finditer(r'\{"id"', text):
        try:
            found.append(decoder.raw_decode(text[match.start():])[0])
        except json.JSONDecodeError:
            continue
    return found


def test_agent_examples_pass_the_same_checks():
    import check_package as cp
    from kitchen_common import load_rules
    from tests.kitchen_fixtures import BRIEF, FOLDER, RECIPE, SHOTS, VOICEOVER

    rules = load_rules()
    (brief,) = _examples("content-manager")
    assert cp.check_brief(brief, FOLDER, rules, set()) == []
    (recipe,) = _examples("recipe-developer")
    assert recipe == RECIPE
    (video_brief,) = _examples("video-producer")
    assert cp.check_video_brief(video_brief, SHOTS, RECIPE, BRIEF, rules) == []
    voiceover = [example for example in _examples("copywriter") if "lines" in example]
    assert voiceover == [VOICEOVER]
    assert cp.check_voiceover(voiceover[0], video_brief, RECIPE, BRIEF, rules) == []
