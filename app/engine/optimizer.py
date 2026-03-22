"""
Context Window Optimizer — THE CORE INNOVATION.

For a target function, this module:
1. Walks the dependency graph to find direct + transitive dependencies
2. Strips dead code and noise from each dependency
3. Ranks dependencies by relevance (direct > transitive > type-only)
4. Packs into a context window under the token budget
5. Returns an OptimizedContext with compression stats

This is what prevents LLM hallucinations — by feeding only relevant,
clean code instead of dumping the entire repository.
"""

from app.models.schemas import (
    ParsedMethod, ParsedClass, OptimizedContext, DependencyType,
)
from app.engine.graph import DependencyGraph
from app.engine.dead_code import clean_source
from app.config import (
    MAX_CONTEXT_TOKENS,
    DIRECT_DEP_WEIGHT,
    TRANSITIVE_DEP_WEIGHT,
    TYPE_ONLY_DEP_WEIGHT,
)


def count_tokens(text: str) -> int:
    """Estimate token count from text. Uses word-splitting heuristic
    (~1.3 tokens per word for code) which is close enough for budget control."""
    words = text.split()
    return int(len(words) * 1.3)


def optimize_context(
    target_method: ParsedMethod,
    dep_graph: DependencyGraph,
    token_budget: int = MAX_CONTEXT_TOKENS,
) -> OptimizedContext:
    """Build an optimized context window for a target method.

    This is the heart of the context optimization technique:
    - Only includes dependencies that the target method actually needs
    - Strips noise/dead-code from included dependencies
    - Prioritizes direct calls over transitive dependencies
    - Stays within the token budget to prevent LLM confusion

    Args:
        target_method: The method we want to modernize.
        dep_graph: The project's dependency graph.
        token_budget: Maximum tokens for the context window.

    Returns:
        OptimizedContext with the assembled context string and stats.
    """

    # Step 1: Collect all dependencies with their priority scores
    scored_deps = _score_dependencies(target_method, dep_graph)

    # Step 2: Sort by priority (highest first)
    scored_deps.sort(key=lambda x: x[1], reverse=True)

    # Step 3: Clean the target method's source
    target_cleaned = clean_source(target_method.source_code)
    target_code = target_cleaned.cleaned_source

    # Step 4: Start assembling context, track token usage
    context_parts = []
    included_deps = []
    excluded_deps = []
    total_original_lines = target_cleaned.original_lines

    # Reserve tokens for the target method itself + prompt overhead
    target_tokens = count_tokens(target_code)
    prompt_overhead = 500  # Reserve for system prompt, instructions, etc.
    remaining_budget = token_budget - target_tokens - prompt_overhead

    # Step 5: Pack dependencies into the budget
    for dep_id, score, dep_type in scored_deps:
        dep_source = _get_dependency_source(dep_id, dep_graph)
        if not dep_source:
            continue

        # Clean the dependency source
        cleaned = clean_source(dep_source)
        dep_code = cleaned.cleaned_source
        total_original_lines += cleaned.original_lines

        dep_tokens = count_tokens(dep_code)

        if dep_tokens <= remaining_budget:
            # Format with a header showing what this dependency is
            header = f"// --- Dependency: {dep_id} ({dep_type}) ---"
            context_parts.append(f"{header}\n{dep_code}")
            included_deps.append(dep_id)
            remaining_budget -= dep_tokens
        else:
            # Try to include a signature-only version if full doesn't fit
            signature = _extract_signature(dep_id, dep_graph)
            if signature:
                sig_tokens = count_tokens(signature)
                if sig_tokens <= remaining_budget:
                    header = f"// --- Dependency (signature only): {dep_id} ---"
                    context_parts.append(f"{header}\n{signature}")
                    included_deps.append(f"{dep_id} [sig-only]")
                    remaining_budget -= sig_tokens
                else:
                    excluded_deps.append(dep_id)
            else:
                excluded_deps.append(dep_id)

    # Step 6: Assemble the final context string
    context_code = "\n\n".join(context_parts) if context_parts else ""

    optimized_lines = len(context_code.splitlines()) + len(target_code.splitlines())
    total_tokens = count_tokens(context_code) + target_tokens

    return OptimizedContext(
        target_function=target_method,
        context_code=context_code,
        included_deps=included_deps,
        excluded_deps=excluded_deps,
        original_total_lines=total_original_lines,
        optimized_total_lines=optimized_lines,
        estimated_tokens=total_tokens,
    )


def _score_dependencies(
    target_method: ParsedMethod,
    dep_graph: DependencyGraph,
) -> list[tuple[str, float, str]]:
    """Score all dependencies of a target method by relevance.

    Returns:
        List of (dep_id, score, dep_type_label) tuples.
    """
    scored = []

    # Get direct dependencies (depth 1)
    direct_deps = dep_graph.get_direct_dependencies(target_method.qualified_name)
    for dep_id in direct_deps:
        edge_type = dep_graph.get_edge_type(target_method.qualified_name, dep_id)
        score = _get_weight_for_edge(edge_type)
        scored.append((dep_id, score * DIRECT_DEP_WEIGHT, "direct"))

    # Get transitive dependencies (depth 2-3)
    all_deps = dep_graph.get_dependencies(target_method.qualified_name, max_depth=3)
    for dep_id in all_deps:
        if dep_id not in direct_deps:
            # Check how this is related
            edge_type = dep_graph.get_edge_type(target_method.qualified_name, dep_id)
            score = _get_weight_for_edge(edge_type)
            scored.append((dep_id, score * TRANSITIVE_DEP_WEIGHT, "transitive"))

    # Also include the parent class context
    parent_class = dep_graph.get_class(target_method.class_name)
    if parent_class:
        # Include sibling methods that are called by the target
        for call in target_method.calls:
            sibling_name = f"{target_method.class_name}.{call}"
            if dep_graph.get_method(sibling_name) and sibling_name not in [d[0] for d in scored]:
                scored.append((sibling_name, DIRECT_DEP_WEIGHT * 0.9, "sibling"))

    # Deduplicate — keep highest score
    seen = {}
    for dep_id, score, label in scored:
        if dep_id not in seen or seen[dep_id][0] < score:
            seen[dep_id] = (score, label)

    return [(dep_id, score, label) for dep_id, (score, label) in seen.items()]


def _get_weight_for_edge(edge_type: str | None) -> float:
    """Map edge type to a relevance weight."""
    if edge_type is None:
        return TYPE_ONLY_DEP_WEIGHT

    weights = {
        DependencyType.CALLS.value: 1.0,
        DependencyType.INHERITS.value: 0.9,
        DependencyType.IMPLEMENTS.value: 0.8,
        DependencyType.IMPORTS.value: 0.5,
        DependencyType.FIELD_TYPE.value: 0.3,
        DependencyType.PARAM_TYPE.value: 0.3,
        DependencyType.RETURN_TYPE.value: 0.3,
    }
    return weights.get(edge_type, TYPE_ONLY_DEP_WEIGHT)


def _get_dependency_source(dep_id: str, dep_graph: DependencyGraph) -> str | None:
    """Get the source code for a dependency node."""
    # Try as a method first
    method = dep_graph.get_method(dep_id)
    if method:
        return method.source_code

    # Try as a class
    cls = dep_graph.get_class(dep_id)
    if cls:
        return cls.source_code

    return None


def _extract_signature(dep_id: str, dep_graph: DependencyGraph) -> str | None:
    """Extract just the method/class signature (no body) for a dependency.
    Used when the full source doesn't fit in the token budget."""
    method = dep_graph.get_method(dep_id)
    if method:
        # Build a signature-only representation
        mods = " ".join(method.modifiers)
        params = ", ".join(method.parameters)
        return f"{mods} {method.return_type} {method.name}({params}) {{ /* ... */ }}"

    cls = dep_graph.get_class(dep_id)
    if cls:
        parts = []
        mods = " ".join(cls.modifiers)
        ext = f" extends {cls.extends}" if cls.extends else ""
        impl = f" implements {', '.join(cls.implements)}" if cls.implements else ""
        parts.append(f"{mods} class {cls.name}{ext}{impl} {{")

        # Include field declarations
        for field in cls.fields:
            parts.append(f"    {field};")

        # Include method signatures only
        for method in cls.methods:
            m_mods = " ".join(method.modifiers)
            m_params = ", ".join(method.parameters)
            parts.append(f"    {m_mods} {method.return_type} {method.name}({m_params});")

        parts.append("}")
        return "\n".join(parts)

    return None
