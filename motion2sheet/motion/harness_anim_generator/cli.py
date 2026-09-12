from __future__ import annotations

import argparse
import webbrowser
from pathlib import Path

from .contracts import GenerationRequest
from .orchestrator import AnimationGenerationOrchestrator
from .providers import PROVIDER_NAMES, create_provider
from .workspace import graphical_environment


def _port(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("report port must be an integer") from exc
    if not 0 <= parsed <= 65535:
        raise argparse.ArgumentTypeError("report port must be between 0 and 65535")
    return parsed


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def generation_request_from_args(args: argparse.Namespace) -> GenerationRequest:
    prompt = args.prompt
    if args.prompt_file is not None:
        try:
            prompt = Path(args.prompt_file).read_text(encoding="utf-8")
        except OSError as exc:
            raise RuntimeError(f"cannot read prompt file {args.prompt_file}: {exc}") from exc
    return GenerationRequest(
        prompt=prompt,
        provider=args.provider,
        output=Path(args.output),
        skill_directory=Path(args.skill) if args.skill is not None else None,
        resume_run_id=args.resume_run,
        report_port=args.report_port,
        open_report=not args.no_open_report,
    )


def _generate(args: argparse.Namespace) -> int:
    request = generation_request_from_args(args)
    root = repo_root()
    orchestrator = AnimationGenerationOrchestrator(
        provider=create_provider(request.provider, repo_root=root),
        repo_root=root,
        workspace_root=root / "build" / "harness_anim_generator",
    )
    active = orchestrator.start(request)
    print(f"Run ID: {active.run_id}")
    print(f"Agent: {request.provider}")
    print("Status: running")
    print(f"Workspace: {active.workspace.root}")
    print(f"Report: {active.report_url}")
    if request.open_report and graphical_environment():
        try:
            webbrowser.open(active.report_url)
        except webbrowser.Error:
            pass
    result = active.wait()
    print(f"motion2sheet: humanoid animation generation completed -> {result.output}")
    print(f"Static report: {result.report_path}")
    return 0


def add_harness_anim_generator_subcommands(subparsers) -> None:
    generate = subparsers.add_parser(
        "generate-humanoid-animation",
        help="Launch a skill-driven animation authoring agent and supervise its run",
    )
    prompt = generate.add_mutually_exclusive_group(required=True)
    prompt.add_argument("--prompt")
    prompt.add_argument("--prompt-file")
    generate.add_argument("--provider", choices=PROVIDER_NAMES, default="codex-cli")
    generate.add_argument("--output", required=True)
    generate.add_argument(
        "--skill",
        metavar="DIRECTORY",
        help="Use a skill directory containing SKILL.md and skill.json",
    )
    generate.add_argument("--resume-run")
    generate.add_argument("--report-port", type=_port, default=0)
    generate.add_argument("--no-open-report", action="store_true")
    generate.set_defaults(func=_generate)
