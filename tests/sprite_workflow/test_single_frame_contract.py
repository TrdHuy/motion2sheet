from pathlib import Path
import re


ROOT = Path("sample/sprite-generation/walk-down")
EXPECTED_FRAMES = list(range(1, 9))


def _numbered_files(pattern: str) -> dict[int, Path]:
    result: dict[int, Path] = {}
    regex = re.compile(pattern)
    for path in ROOT.iterdir():
        match = regex.fullmatch(path.name)
        if match:
            number = int(match.group(1))
            assert number not in result, f"duplicate frame number {number}: {path.name}"
            result[number] = path
    return result


def test_walk_down_shared_inputs_exist_and_are_nonempty():
    for name in ("README.md", "character reference.png", "general prompt.txt"):
        path = ROOT / name
        assert path.is_file(), f"missing sample input: {path}"
        assert path.stat().st_size > 0, f"empty sample input: {path}"


def test_walk_down_pose_description_pairing_is_complete():
    poses = _numbered_files(r"walk pose (\d+)\.png")
    descriptions = _numbered_files(r"walk description (\d+)\.txt")
    assert sorted(poses) == EXPECTED_FRAMES
    assert sorted(descriptions) == EXPECTED_FRAMES
    assert set(poses) == set(descriptions)
    for number, path in descriptions.items():
        assert path.read_text(encoding="utf-8").strip(), f"empty description for frame {number}"


def test_walk_down_has_no_orphan_numbered_pose_or_description_files():
    numbered = [
        path.name
        for path in ROOT.iterdir()
        if path.name.startswith("walk pose ") or path.name.startswith("walk description ")
    ]
    expected = {
        *(f"walk pose {number}.png" for number in EXPECTED_FRAMES),
        *(f"walk description {number}.txt" for number in EXPECTED_FRAMES),
    }
    assert set(numbered) == expected
