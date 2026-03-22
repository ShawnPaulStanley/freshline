"""
Java AST Parser — parses .java files using javalang and extracts
classes, methods, fields, imports, and method calls into our data models.
"""

import os
import javalang
from pathlib import Path
from typing import Optional

from app.models.schemas import ParsedFile, ParsedClass, ParsedMethod


def parse_java_file(file_path: str) -> ParsedFile:
    """Parse a single .java file into a ParsedFile model."""
    path = Path(file_path)
    raw_source = path.read_text(encoding="utf-8", errors="replace")

    parsed_file = ParsedFile(
        file_path=str(path),
        raw_source=raw_source,
    )

    try:
        tree = javalang.parse.parse(raw_source)
    except javalang.parser.JavaSyntaxError as e:
        parsed_file.parse_errors.append(f"Syntax error: {e}")
        return parsed_file
    except Exception as e:
        parsed_file.parse_errors.append(f"Parse error: {e}")
        return parsed_file

    # Extract package
    if tree.package:
        parsed_file.package = tree.package.name

    # Extract imports
    for imp in tree.imports:
        parsed_file.imports.append(imp.path)

    # Extract classes, interfaces, enums
    source_lines = raw_source.splitlines()
    for type_decl in tree.types:
        if isinstance(type_decl, (javalang.tree.ClassDeclaration,
                                   javalang.tree.InterfaceDeclaration,
                                   javalang.tree.EnumDeclaration)):
            parsed_class = _extract_class(type_decl, file_path, parsed_file.package, source_lines)
            parsed_file.classes.append(parsed_class)

    return parsed_file


def _extract_class(
    type_decl,
    file_path: str,
    package: str,
    source_lines: list[str]
) -> ParsedClass:
    """Extract a ParsedClass from a javalang type declaration."""
    is_interface = isinstance(type_decl, javalang.tree.InterfaceDeclaration)
    is_enum = isinstance(type_decl, javalang.tree.EnumDeclaration)

    extends = None
    implements = []

    if hasattr(type_decl, "extends") and type_decl.extends:
        if isinstance(type_decl.extends, list):
            extends = type_decl.extends[0].name if type_decl.extends else None
        else:
            extends = type_decl.extends.name

    if hasattr(type_decl, "implements") and type_decl.implements:
        implements = [impl.name for impl in type_decl.implements]

    modifiers = list(type_decl.modifiers) if type_decl.modifiers else []

    # Extract fields
    fields = []
    if hasattr(type_decl, "fields") and type_decl.fields:
        for field_decl in type_decl.fields:
            if isinstance(field_decl, javalang.tree.FieldDeclaration):
                field_type = _get_type_name(field_decl.type)
                field_mods = list(field_decl.modifiers) if field_decl.modifiers else []
                for declarator in field_decl.declarators:
                    field_str = f"{' '.join(field_mods)} {field_type} {declarator.name}".strip()
                    fields.append(field_str)

    # Extract methods
    methods = []
    if hasattr(type_decl, "methods") and type_decl.methods:
        for method_decl in type_decl.methods:
            parsed_method = _extract_method(method_decl, type_decl.name, file_path, source_lines)
            if parsed_method:
                methods.append(parsed_method)

    # Also extract constructors as methods
    if hasattr(type_decl, "constructors") and type_decl.constructors:
        for ctor in type_decl.constructors:
            parsed_method = _extract_constructor(ctor, type_decl.name, file_path, source_lines)
            if parsed_method:
                methods.append(parsed_method)

    # Get class source code (approximate: from class declaration line to end)
    class_source = ""
    if hasattr(type_decl, "position") and type_decl.position:
        start_line = type_decl.position.line - 1
        class_source = "\n".join(source_lines[start_line:])

    return ParsedClass(
        name=type_decl.name,
        file_path=file_path,
        package=package,
        extends=extends,
        implements=implements,
        methods=methods,
        fields=fields,
        modifiers=modifiers,
        is_interface=is_interface,
        source_code=class_source,
    )


def _extract_method(
    method_decl: javalang.tree.MethodDeclaration,
    class_name: str,
    file_path: str,
    source_lines: list[str]
) -> Optional[ParsedMethod]:
    """Extract a ParsedMethod from a javalang MethodDeclaration."""
    if not method_decl.position:
        return None

    start_line = method_decl.position.line
    end_line = _find_method_end(source_lines, start_line - 1)

    # Get source code for this method
    method_source = "\n".join(source_lines[start_line - 1 : end_line])

    # Return type
    return_type = _get_type_name(method_decl.return_type) if method_decl.return_type else "void"

    # Parameters
    parameters = []
    if method_decl.parameters:
        for param in method_decl.parameters:
            param_type = _get_type_name(param.type)
            parameters.append(f"{param_type} {param.name}")

    # Modifiers
    modifiers = list(method_decl.modifiers) if method_decl.modifiers else []

    # Extract method calls within the body
    calls = _extract_method_calls(method_decl)

    return ParsedMethod(
        name=method_decl.name,
        class_name=class_name,
        file_path=file_path,
        start_line=start_line,
        end_line=end_line,
        source_code=method_source,
        return_type=return_type,
        parameters=parameters,
        modifiers=modifiers,
        calls=calls,
    )


def _extract_constructor(
    ctor: javalang.tree.ConstructorDeclaration,
    class_name: str,
    file_path: str,
    source_lines: list[str]
) -> Optional[ParsedMethod]:
    """Extract constructor as a ParsedMethod."""
    if not ctor.position:
        return None

    start_line = ctor.position.line
    end_line = _find_method_end(source_lines, start_line - 1)
    method_source = "\n".join(source_lines[start_line - 1 : end_line])

    parameters = []
    if ctor.parameters:
        for param in ctor.parameters:
            param_type = _get_type_name(param.type)
            parameters.append(f"{param_type} {param.name}")

    modifiers = list(ctor.modifiers) if ctor.modifiers else []
    calls = _extract_method_calls(ctor)

    return ParsedMethod(
        name="__init__",  # Treat constructors like Python __init__
        class_name=class_name,
        file_path=file_path,
        start_line=start_line,
        end_line=end_line,
        source_code=method_source,
        return_type="void",
        parameters=parameters,
        modifiers=modifiers,
        calls=calls,
    )


def _extract_method_calls(node) -> list[str]:
    """Recursively extract all method invocations from a method's body."""
    calls = []

    if not hasattr(node, "body") or node.body is None:
        return calls

    # Walk the entire subtree looking for MethodInvocation nodes
    for _, child_node in node.filter(javalang.tree.MethodInvocation):
        if child_node.qualifier:
            calls.append(f"{child_node.qualifier}.{child_node.member}")
        else:
            calls.append(child_node.member)

    return list(set(calls))  # Deduplicate


def _get_type_name(type_node) -> str:
    """Get a human-readable type name from a javalang type node."""
    if type_node is None:
        return "void"
    if isinstance(type_node, javalang.tree.BasicType):
        return type_node.name
    if isinstance(type_node, javalang.tree.ReferenceType):
        name = type_node.name
        if type_node.arguments:
            args = ", ".join(_get_type_name(arg.type) if hasattr(arg, "type") else "?"
                           for arg in type_node.arguments)
            name += f"<{args}>"
        return name
    return str(type_node)


def _find_method_end(source_lines: list[str], start_idx: int) -> int:
    """Find the end line of a method by tracking brace depth."""
    depth = 0
    found_opening = False

    for i in range(start_idx, len(source_lines)):
        line = source_lines[i]
        # Count braces (ignoring ones in strings/comments for simplicity)
        for char in line:
            if char == '{':
                depth += 1
                found_opening = True
            elif char == '}':
                depth -= 1

        if found_opening and depth == 0:
            return i + 1  # 1-indexed

    return len(source_lines)


def parse_project(project_dir: str) -> list[ParsedFile]:
    """Parse all .java files in a project directory."""
    parsed_files = []

    for root, _dirs, files in os.walk(project_dir):
        for filename in files:
            if filename.endswith(".java"):
                file_path = os.path.join(root, filename)
                parsed = parse_java_file(file_path)
                parsed_files.append(parsed)

    return parsed_files
