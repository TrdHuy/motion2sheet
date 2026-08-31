from pathlib import Path
def test_common_does_not_depend_on_clip_identity():
    root=Path(__file__).resolve().parents[3]/"motion2sheet/anim2sheet/common"; violations=[]
    for path in sorted(root.rglob("*.py")):
        text=path.read_text(encoding="utf-8")
        for token in ("animations.gale_slash","animations/gale_slash",'animation == "gale_slash"',"animation == 'gale_slash'",'animation == "sword_idle"',"animation == 'sword_idle'"):
            if token in text:violations.append(f"{path.relative_to(root)}:{token}")
    assert not violations,f"common -> clip dependency found: {violations}"
