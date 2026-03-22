"""
Prompt Templates — carefully engineered prompts for code modernization.

These prompts are designed to:
1. Ground the LLM in the specific context (no hallucination from general knowledge)
2. Use markdown code blocks for clean output parsing (NOT JSON — avoids escape hell)
3. Include self-assessment of confidence
"""


MODERNIZE_SYSTEM_PROMPT = """You are an expert legacy code modernizer. Your job is to convert Java code to clean, modern, idiomatic Python.

RULES:
1. ONLY use information from the provided code context. Do NOT invent methods, classes, or imports that aren't in the context.
2. Preserve the exact business logic — do not "improve" or optimize the logic unless it's a direct language difference.
3. Use Pythonic patterns: dataclasses, type hints, list comprehensions, context managers, etc.
4. Convert Java naming conventions to Python (camelCase -> snake_case, ClassName stays PascalCase).
5. Replace Java-specific patterns with Python equivalents:
   - ArrayList -> list
   - HashMap -> dict
   - System.out.println -> print
   - getter/setter -> @property when appropriate
   - static methods -> @staticmethod or module-level functions
   - Java enums -> Python Enum class
6. Add type hints to all function signatures.
7. Add a docstring to each function and class.
8. If you are uncertain about a conversion, flag it in your confidence notes.

You MUST respond in EXACTLY this format (using the markers shown):

===PYTHON_CODE_START===
(your complete Python code here)
===PYTHON_CODE_END===

===EXPLANATION_START===
(brief explanation of what you converted and key decisions)
===EXPLANATION_END===

===CONFIDENCE===
(a number between 0.0 and 1.0)

===CONFIDENCE_NOTES===
(any concerns or uncertainties about this conversion)

The confidence score should reflect:
- 0.9-1.0: Simple, direct conversion with full context available
- 0.7-0.9: Good conversion but some context was missing or patterns were complex
- 0.5-0.7: Conversion required assumptions due to missing dependencies
- 0.0-0.5: Significant guesswork was needed, review carefully"""


def build_modernize_prompt(
    target_method_source: str,
    context_code: str,
    target_class_name: str,
    method_name: str,
    included_deps: list[str],
    excluded_deps: list[str],
) -> str:
    """Build the user prompt for modernizing a single method."""
    parts = []

    parts.append(f"Convert the following Java method `{target_class_name}.{method_name}` to modern Python.\n")

    if excluded_deps:
        parts.append(f"WARNING: The following dependencies were NOT included in the context due to size constraints: {', '.join(excluded_deps)}")
        parts.append("Do NOT guess their implementation. Use placeholder comments like `# TODO: requires <dep_name>` if needed.\n")

    if context_code:
        parts.append("=== DEPENDENCY CONTEXT (other code this method relies on) ===")
        parts.append(context_code)
        parts.append("=== END DEPENDENCY CONTEXT ===\n")

    parts.append("=== TARGET METHOD TO CONVERT ===")
    parts.append(target_method_source)
    parts.append("=== END TARGET METHOD ===")

    parts.append("\nConvert ONLY the target method. Use dependency context for understanding, but only output the converted target method.")

    return "\n".join(parts)


DOCUMENT_SYSTEM_PROMPT = """You are a technical documentation expert. Your job is to generate clear, comprehensive documentation for legacy Java code being modernized.

Generate documentation that:
1. Explains what the code does in plain English
2. Documents all parameters and return values
3. Notes any business rules or edge cases
4. Flags potential issues or technical debt
5. Describes dependencies on other components

Respond in this format:

===PYTHON_CODE_START===
(the Python code with comprehensive docstrings added)
===PYTHON_CODE_END===

===EXPLANATION_START===
(summary of what this code does)
===EXPLANATION_END===

===CONFIDENCE===
0.9

===CONFIDENCE_NOTES===
(any uncertainties in the documentation)"""


def build_document_prompt(
    class_source: str,
    class_name: str,
    context_code: str = "",
) -> str:
    """Build prompt for generating documentation for a class."""
    parts = []

    parts.append(f"Generate comprehensive Python documentation for the class `{class_name}`, "
                 f"originally written in Java.\n")

    if context_code:
        parts.append("=== RELATED CODE CONTEXT ===")
        parts.append(context_code)
        parts.append("=== END CONTEXT ===\n")

    parts.append("=== CLASS TO DOCUMENT ===")
    parts.append(class_source)
    parts.append("=== END CLASS ===")

    return "\n".join(parts)
