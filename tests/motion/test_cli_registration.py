from motion2sheet.motion.cli import parser


def test_public_motion_cli_registers_canonical_commands_only():
    root = parser()
    choices = root._subparsers._group_actions[0].choices
    expected = {
        "build",
        "validate",
        "export-animation-json",
        "export-character",
        "export-humanoid-animation",
        "verify-humanoid-animation-fidelity",
        "render-humanoid-animation",
    }
    assert expected.issubset(choices)
    assert "render-model-animation" not in choices
    assert "render-character-animation" not in choices
