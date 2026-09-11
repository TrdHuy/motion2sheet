from __future__ import annotations

import argparse
from pathlib import Path

from .contracts import GenerationRequest
from .metadata import MetadataBuilder
from .motion2sheet_adapter import Motion2SheetAdapter
from .orchestrator import AnimationGenerationOrchestrator
from .providers import PROVIDER_NAMES, create_provider
from .references import ReferenceLibrary
from .review import ProviderReviewer


def _positive_integer(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("max iterations must be an integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("max iterations must be positive")
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
        max_iterations=args.max_iterations,
    )


def _generate(args: argparse.Namespace) -> int:
    request = generation_request_from_args(args)
    root = repo_root()
    provider = create_provider(request.provider, repo_root=root)
    workspace_root = root / "build" / "harness_anim_generator"
    adapter = Motion2SheetAdapter(repo_root=root, workspace=workspace_root)
    orchestrator = AnimationGenerationOrchestrator(
        provider=provider,
        references=ReferenceLibrary(root / "sample" / "humanoid_motion" / "mixamo"),
        adapter=adapter,
        reviewer=ProviderReviewer(provider),
        metadata_builder=MetadataBuilder(),
        workspace_root=workspace_root,
    )
    result = orchestrator.run(request)
    print(
        "motion2sheet: humanoid animation generation PASS; "
        f"iterations={len(result.iterations)} output={result.output}"
    )
    return 0


def add_harness_anim_generator_subcommands(subparsers) -> None:
    generate = subparsers.add_parser(
        "generate-humanoid-animation",
        help="Generate, validate, render and review a Humanoid Motion animation through an AI provider",
    )
    prompt = generate.add_mutually_exclusive_group(required=True)
    prompt.add_argument("--prompt")
    prompt.add_argument("--prompt-file")
    generate.add_argument("--provider", choices=PROVIDER_NAMES, default="codex-cli")
    generate.add_argument("--output", required=True)
    generate.add_argument("--max-iterations", type=_positive_integer, default=3)
    generate.set_defaults(func=_generate)
