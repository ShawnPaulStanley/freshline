"""Data models for all parsed entities throughout the pipeline."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DependencyType(Enum):
    """How one code entity relates to another."""
    CALLS = "calls"             # MethodA calls MethodB
    IMPORTS = "imports"         # File imports a class
    INHERITS = "inherits"      # Class extends another
    IMPLEMENTS = "implements"  # Class implements interface
    FIELD_TYPE = "field_type"  # Field uses a class as its type
    PARAM_TYPE = "param_type"  # Method param uses a class as type
    RETURN_TYPE = "return_type" # Method return type uses a class


class NoiseType(Enum):
    """Types of noise detected in code."""
    EXCESSIVE_COMMENTS = "excessive_comments"
    TODO_BLOCK = "todo_block"
    COMMENTED_OUT_CODE = "commented_out_code"
    DEAD_IMPORT = "dead_import"


@dataclass
class ParsedMethod:
    """A single method extracted from a Java file."""
    name: str
    class_name: str
    file_path: str
    start_line: int
    end_line: int
    source_code: str
    return_type: str = "void"
    parameters: list[str] = field(default_factory=list)    # ["String name", "int age"]
    modifiers: list[str] = field(default_factory=list)     # ["public", "static"]
    calls: list[str] = field(default_factory=list)         # ["otherMethod", "SomeClass.doThing"]
    local_variables: list[str] = field(default_factory=list)

    @property
    def qualified_name(self) -> str:
        return f"{self.class_name}.{self.name}"

    @property
    def is_entry_point(self) -> bool:
        return (self.name == "main" and "static" in self.modifiers) or \
               self.name in {"init", "run", "start", "execute"}


@dataclass
class ParsedClass:
    """A class or interface extracted from a Java file."""
    name: str
    file_path: str
    package: str = ""
    extends: Optional[str] = None
    implements: list[str] = field(default_factory=list)
    methods: list[ParsedMethod] = field(default_factory=list)
    fields: list[str] = field(default_factory=list)        # ["private String name", "int count"]
    modifiers: list[str] = field(default_factory=list)
    is_interface: bool = False
    source_code: str = ""

    @property
    def qualified_name(self) -> str:
        return f"{self.package}.{self.name}" if self.package else self.name


@dataclass
class ParsedFile:
    """Everything extracted from a single .java file."""
    file_path: str
    package: str = ""
    imports: list[str] = field(default_factory=list)
    classes: list[ParsedClass] = field(default_factory=list)
    raw_source: str = ""
    parse_errors: list[str] = field(default_factory=list)

    @property
    def all_methods(self) -> list[ParsedMethod]:
        methods = []
        for cls in self.classes:
            methods.extend(cls.methods)
        return methods


@dataclass
class NoiseRegion:
    """A region of code identified as noise."""
    noise_type: NoiseType
    start_line: int
    end_line: int
    content: str
    reason: str


@dataclass
class CleanedCode:
    """Code with noise stripped out, plus stats."""
    original_source: str
    cleaned_source: str
    noise_regions: list[NoiseRegion] = field(default_factory=list)

    @property
    def original_lines(self) -> int:
        return len(self.original_source.splitlines())

    @property
    def cleaned_lines(self) -> int:
        return len(self.cleaned_source.splitlines())

    @property
    def noise_ratio(self) -> float:
        if self.original_lines == 0:
            return 0.0
        return 1.0 - (self.cleaned_lines / self.original_lines)


@dataclass
class DependencyEdge:
    """An edge in the dependency graph."""
    source: str       # qualified name of caller
    target: str       # qualified name of callee
    dep_type: DependencyType
    weight: float = 1.0


@dataclass
class OptimizedContext:
    """The optimized context window to send to the LLM."""
    target_function: ParsedMethod
    context_code: str                     # The assembled context string
    included_deps: list[str] = field(default_factory=list)  # Names of included deps
    excluded_deps: list[str] = field(default_factory=list)  # Names of deps that didn't fit
    original_total_lines: int = 0
    optimized_total_lines: int = 0
    estimated_tokens: int = 0

    @property
    def compression_ratio(self) -> float:
        if self.original_total_lines == 0:
            return 0.0
        return 1.0 - (self.optimized_total_lines / self.original_total_lines)


@dataclass
class ModernizedFunction:
    """Result of modernizing a single function."""
    original_method: ParsedMethod
    python_code: str
    explanation: str
    documentation: str
    confidence: float       # 0.0 - 1.0
    confidence_notes: str
    context_stats: OptimizedContext


@dataclass
class ProjectResult:
    """Complete result of modernizing a project."""
    project_name: str
    source_dir: str
    output_dir: str
    files_parsed: int
    files_failed: int
    methods_converted: int
    methods_skipped: int
    functions: list[ModernizedFunction] = field(default_factory=list)
    total_original_lines: int = 0
    total_output_lines: int = 0
    avg_confidence: float = 0.0
    avg_compression_ratio: float = 0.0
