"""Apply only validated, bounded AI patches before credential-free testing."""

import argparse
import subprocess
from pathlib import Path

from tools.ai_contract import Analysis, UnsafePatchError, validate_patch


def apply_proposal(
    repository: Path,
    analysis: Analysis,
    output: Path,
    *,
    standards_only: bool = False,
) -> bool:
    """Validate both diff paths and disk paths, then check and apply the patch."""
    if not analysis.patch:
        return False
    root = repository.resolve()
    for relative in validate_patch(analysis.patch):
        if standards_only and not relative.startswith("standards/"):
            raise UnsafePatchError
        path = root / relative
        if not path.resolve().is_relative_to(root):
            raise UnsafePatchError
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
            raise UnsafePatchError
    output.write_text(analysis.patch, encoding="utf-8", newline="\n")
    command = ["git", "-C", str(root), "apply", "--whitespace=error"]
    subprocess.run([*command, "--check", str(output)], check=True, capture_output=True)
    subprocess.run([*command, str(output)], check=True, capture_output=True)
    return True


def main() -> None:
    """Check and apply an artifact proposal without executing model instructions."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--standards-only", action="store_true")
    parser.add_argument("--body", type=Path)
    args = parser.parse_args()
    analysis = Analysis.model_validate_json(args.analysis.read_text(encoding="utf-8"))
    apply_proposal(
        args.repository, analysis, args.output, standards_only=args.standards_only
    )
    if args.body:
        args.body.write_text(
            "## AI proposal (draft, requires human review)\n\n"
            + analysis.summary
            + "\n\nThe bounded patch passed deterministic validation in a separate job "
            "without provider/App credentials. Inspect the workflow evidence and "
            "verify these claims before merging.\n\n"
            "Generated with MiMo 2.6 Flash through isolated OpenCode.\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
