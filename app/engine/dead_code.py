"""
Dead Code & Noise Detector — identifies unreachable methods, excessive comments,
TODO blocks, commented-out code, and other noise that would confuse the LLM.
"""

import re

from app.models.schemas import (
    ParsedFile, ParsedClass, ParsedMethod,
    NoiseRegion, NoiseType, CleanedCode,
)
from app.config import NOISE_COMMENT_THRESHOLD, ENTRY_POINT_METHODS


def detect_dead_methods(
    parsed_files: list[ParsedFile],
    all_called_methods: set[str] | None = None,
) -> list[ParsedMethod]:
    """Find methods that are never called from anywhere in the project.

    Args:
        parsed_files: All parsed Java files in the project.
        all_called_methods: Optional pre-computed set of all method calls
            across the project. If None, will be computed.

    Returns:
        List of methods that appear to be dead code.
    """
    if all_called_methods is None:
        all_called_methods = _collect_all_calls(parsed_files)

    dead_methods = []

    for pf in parsed_files:
        for cls in pf.classes:
            for method in cls.methods:
                # Skip entry points — they're called externally
                if method.is_entry_point:
                    continue
                # Skip constructors
                if method.name == "__init__":
                    continue
                # Skip getters/setters (conventionally called externally)
                if method.name.startswith("get") or method.name.startswith("set") or \
                   method.name.startswith("is"):
                    continue
                # Skip overrides (toString, etc.)
                if method.name in {"toString", "hashCode", "equals", "compareTo"}:
                    continue

                # Check if this method is called anywhere
                is_called = (
                    method.name in all_called_methods or
                    method.qualified_name in all_called_methods or
                    f"{cls.name}.{method.name}" in all_called_methods
                )

                if not is_called:
                    dead_methods.append(method)

    return dead_methods


def _collect_all_calls(parsed_files: list[ParsedFile]) -> set[str]:
    """Collect all method call references across the entire project."""
    calls = set()
    for pf in parsed_files:
        for cls in pf.classes:
            for method in cls.methods:
                for call in method.calls:
                    calls.add(call)
                    # Also add the method name part for unqualified matching
                    if "." in call:
                        calls.add(call.split(".")[-1])
    return calls


def detect_noise(source_code: str) -> list[NoiseRegion]:
    """Detect noise regions in source code that would confuse the LLM."""
    lines = source_code.splitlines()
    noise_regions = []

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # 1. Detect consecutive comment blocks (excessive comments)
        if _is_comment_line(line):
            block_start = i
            comment_lines = []
            while i < len(lines) and _is_comment_line(lines[i].strip()):
                comment_lines.append(lines[i])
                i += 1

            if len(comment_lines) >= NOISE_COMMENT_THRESHOLD:
                content = "\n".join(comment_lines)
                # Check if it's a TODO/FIXME/HACK block
                if any(tag in content.upper() for tag in ["TODO", "FIXME", "HACK", "NOTE", "XXX"]):
                    noise_regions.append(NoiseRegion(
                        noise_type=NoiseType.TODO_BLOCK,
                        start_line=block_start + 1,
                        end_line=i,
                        content=content,
                        reason=f"TODO/FIXME block ({len(comment_lines)} lines) — irrelevant to LLM"
                    ))
                else:
                    noise_regions.append(NoiseRegion(
                        noise_type=NoiseType.EXCESSIVE_COMMENTS,
                        start_line=block_start + 1,
                        end_line=i,
                        content=content,
                        reason=f"Excessive comment block ({len(comment_lines)} lines)"
                    ))
            continue

        # 2. Detect commented-out code blocks
        if _is_commented_out_code(line):
            block_start = i
            commented_code_lines = []
            while i < len(lines) and _is_commented_out_code(lines[i].strip()):
                commented_code_lines.append(lines[i])
                i += 1

            if len(commented_code_lines) >= 2:
                noise_regions.append(NoiseRegion(
                    noise_type=NoiseType.COMMENTED_OUT_CODE,
                    start_line=block_start + 1,
                    end_line=i,
                    content="\n".join(commented_code_lines),
                    reason=f"Commented-out code block ({len(commented_code_lines)} lines)"
                ))
            continue

        i += 1

    return noise_regions


def clean_source(source_code: str) -> CleanedCode:
    """Remove noise from source code and return cleaned version with stats."""
    noise_regions = detect_noise(source_code)

    if not noise_regions:
        return CleanedCode(
            original_source=source_code,
            cleaned_source=source_code,
            noise_regions=[],
        )

    lines = source_code.splitlines()
    lines_to_remove = set()

    for region in noise_regions:
        for line_num in range(region.start_line, region.end_line + 1):
            lines_to_remove.add(line_num)

    cleaned_lines = []
    for i, line in enumerate(lines):
        if (i + 1) not in lines_to_remove:
            cleaned_lines.append(line)

    # Remove consecutive blank lines that result from stripping
    final_lines = []
    prev_blank = False
    for line in cleaned_lines:
        is_blank = line.strip() == ""
        if is_blank and prev_blank:
            continue
        final_lines.append(line)
        prev_blank = is_blank

    return CleanedCode(
        original_source=source_code,
        cleaned_source="\n".join(final_lines),
        noise_regions=noise_regions,
    )


def _is_comment_line(line: str) -> bool:
    """Check if a line is a comment (single-line, Javadoc, or block comment)."""
    stripped = line.strip()
    return (
        stripped.startswith("//") or
        stripped.startswith("/*") or
        stripped.startswith("*") or
        stripped.startswith("*/") or
        stripped == ""  # Blank lines within comment blocks count
    ) and not _is_code_line(stripped)


def _is_commented_out_code(line: str) -> bool:
    """Detect if a comment line contains what looks like actual code."""
    stripped = line.strip()

    if not stripped.startswith("//"):
        return False

    # Get the part after //
    code_part = stripped[2:].strip()

    # Heuristics for commented-out code
    code_patterns = [
        r'^(public|private|protected)\s',      # Access modifiers
        r'^(return|if|else|for|while|switch)\s', # Control flow
        r'^\w+\s*\(.*\)\s*[;{]',                # Method calls
        r'^\w+\s+\w+\s*=',                       # Variable assignments
        r'^this\.\w+',                            # Field access
        r'^\w+\.\w+\(',                           # Method call on object
        r'^\}',                                    # Closing brace
    ]

    return any(re.match(pattern, code_part) for pattern in code_patterns)


def _is_code_line(stripped: str) -> bool:
    """Check if a stripped line looks like actual code, not a comment."""
    if not stripped:
        return False
    # Lines that start with Java keywords or common code patterns
    code_starters = [
        "public", "private", "protected", "static", "final",
        "class", "interface", "enum", "import", "package",
        "return", "if", "else", "for", "while", "try", "catch",
        "new", "this", "super", "throw", "throws",
    ]
    for starter in code_starters:
        if stripped.startswith(starter):
            return True
    return False


def get_noise_summary(parsed_files: list[ParsedFile]) -> dict:
    """Get a summary of noise detected across all parsed files."""
    total_noise_lines = 0
    total_lines = 0
    noise_by_type: dict[str, int] = {}

    for pf in parsed_files:
        total_lines += len(pf.raw_source.splitlines())
        noise_regions = detect_noise(pf.raw_source)

        for region in noise_regions:
            region_lines = region.end_line - region.start_line + 1
            total_noise_lines += region_lines
            noise_type = region.noise_type.value
            noise_by_type[noise_type] = noise_by_type.get(noise_type, 0) + region_lines

    return {
        "total_lines": total_lines,
        "noise_lines": total_noise_lines,
        "noise_ratio": total_noise_lines / total_lines if total_lines > 0 else 0,
        "noise_by_type": noise_by_type,
    }
