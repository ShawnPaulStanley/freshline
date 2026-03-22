"""
Dependency Graph Builder — constructs a directed graph of how code entities
relate to each other (calls, imports, inheritance, type usage).
Uses networkx for graph operations.
"""

import networkx as nx
from typing import Optional

from app.models.schemas import (
    ParsedFile, ParsedClass, ParsedMethod,
    DependencyEdge, DependencyType
)


class DependencyGraph:
    """Builds and queries a directed dependency graph from parsed Java files."""

    def __init__(self):
        self.graph = nx.DiGraph()
        self._class_map: dict[str, ParsedClass] = {}    # class_name -> ParsedClass
        self._method_map: dict[str, ParsedMethod] = {}   # qualified_name -> ParsedMethod
        self._file_map: dict[str, ParsedFile] = {}        # file_path -> ParsedFile

    def build(self, parsed_files: list[ParsedFile]) -> None:
        """Build the dependency graph from a list of parsed files."""
        # Phase 1: Register all entities as nodes
        for pf in parsed_files:
            self._file_map[pf.file_path] = pf
            for cls in pf.classes:
                self._register_class(cls)

        # Phase 2: Build edges
        for pf in parsed_files:
            self._build_import_edges(pf)
            for cls in pf.classes:
                self._build_class_edges(cls)
                for method in cls.methods:
                    self._build_method_edges(method, cls)

    def _register_class(self, cls: ParsedClass) -> None:
        """Register a class and its methods as graph nodes."""
        class_id = cls.name  # Use simple name for matching
        self._class_map[class_id] = cls

        self.graph.add_node(class_id, type="class", data=cls)

        for method in cls.methods:
            method_id = method.qualified_name
            self._method_map[method_id] = method
            self.graph.add_node(method_id, type="method", data=method)

            # Edge: class contains method
            self.graph.add_edge(class_id, method_id,
                              dep_type=DependencyType.CALLS.value, weight=1.0)

    def _build_import_edges(self, pf: ParsedFile) -> None:
        """Build edges for import statements."""
        for imp in pf.imports:
            # Get the class name from the import (last segment)
            imported_class = imp.split(".")[-1]
            if imported_class in self._class_map:
                # Connect all classes in this file to the imported class
                for cls in pf.classes:
                    self.graph.add_edge(cls.name, imported_class,
                                      dep_type=DependencyType.IMPORTS.value, weight=0.5)

    def _build_class_edges(self, cls: ParsedClass) -> None:
        """Build inheritance and implementation edges."""
        if cls.extends and cls.extends in self._class_map:
            self.graph.add_edge(cls.name, cls.extends,
                              dep_type=DependencyType.INHERITS.value, weight=1.0)

        for iface in cls.implements:
            if iface in self._class_map:
                self.graph.add_edge(cls.name, iface,
                                  dep_type=DependencyType.IMPLEMENTS.value, weight=0.8)

        # Field type dependencies
        for field_str in cls.fields:
            parts = field_str.split()
            for part in parts:
                clean = part.strip("<>(),;")
                if clean in self._class_map:
                    self.graph.add_edge(cls.name, clean,
                                      dep_type=DependencyType.FIELD_TYPE.value, weight=0.3)

    def _build_method_edges(self, method: ParsedMethod, parent_class: ParsedClass) -> None:
        """Build method-call edges."""
        for call in method.calls:
            resolved = self._resolve_call(call, parent_class)
            if resolved:
                self.graph.add_edge(method.qualified_name, resolved,
                                  dep_type=DependencyType.CALLS.value, weight=1.0)

    def _resolve_call(self, call: str, parent_class: ParsedClass) -> Optional[str]:
        """Resolve a method call string to a qualified method name in the graph."""
        # Case 1: Qualified call like "Logger.log" → look for Logger.log
        if "." in call:
            parts = call.split(".")
            target_class = parts[0]
            target_method = parts[1]

            # Check if it's a known class
            if target_class in self._class_map:
                qualified = f"{target_class}.{target_method}"
                if qualified in self._method_map:
                    return qualified

            # Check if it's a local variable calling a method on its type
            # (simplified: we just check if any class has this method)
            for cls_name, cls in self._class_map.items():
                qualified = f"{cls_name}.{target_method}"
                if qualified in self._method_map:
                    # Check if the target_class could be a variable of this type
                    # by checking field types in parent class
                    for field_str in parent_class.fields:
                        if cls_name in field_str and target_class in field_str:
                            return qualified

            # Direct match for ClassName.methodName
            qualified = f"{target_class}.{target_method}"
            if qualified in self._method_map:
                return qualified

        # Case 2: Unqualified call like "withdraw" → look in same class first
        else:
            # Check same class
            qualified = f"{parent_class.name}.{call}"
            if qualified in self._method_map:
                return qualified

            # Check all classes
            for cls_name in self._class_map:
                qualified = f"{cls_name}.{call}"
                if qualified in self._method_map:
                    return qualified

        return None

    def get_dependencies(self, node_id: str, max_depth: int = 3) -> list[str]:
        """Get all dependencies of a node up to max_depth levels deep."""
        if node_id not in self.graph:
            return []

        visited = set()
        to_visit = [(node_id, 0)]
        deps = []

        while to_visit:
            current, depth = to_visit.pop(0)
            if current in visited or depth > max_depth:
                continue
            visited.add(current)

            if current != node_id:
                deps.append(current)

            # Follow outgoing edges (things this node depends on)
            for successor in self.graph.successors(current):
                if successor not in visited:
                    to_visit.append((successor, depth + 1))

        return deps

    def get_direct_dependencies(self, node_id: str) -> list[str]:
        """Get only direct (depth=1) dependencies."""
        if node_id not in self.graph:
            return []
        return list(self.graph.successors(node_id))

    def get_dependents(self, node_id: str) -> list[str]:
        """Get all nodes that depend ON this node (callers)."""
        if node_id not in self.graph:
            return []
        return list(self.graph.predecessors(node_id))

    def get_conversion_order(self) -> list[str]:
        """Return methods in topological order (dependencies first).
        Falls back to a stable ordering if the graph has cycles."""
        method_nodes = [n for n, d in self.graph.nodes(data=True)
                       if d.get("type") == "method"]

        # Build subgraph of just methods
        method_subgraph = self.graph.subgraph(method_nodes)

        try:
            return list(nx.topological_sort(method_subgraph))
        except nx.NetworkXUnfeasible:
            # Graph has cycles — use a cycle-aware ordering
            # Process SCCs in topological order
            ordered = []
            for scc in nx.strongly_connected_components(method_subgraph):
                ordered.extend(sorted(scc))
            return ordered

    def get_all_methods(self) -> list[ParsedMethod]:
        """Get all registered methods."""
        return list(self._method_map.values())

    def get_method(self, qualified_name: str) -> Optional[ParsedMethod]:
        """Look up a method by qualified name."""
        return self._method_map.get(qualified_name)

    def get_class(self, name: str) -> Optional[ParsedClass]:
        """Look up a class by name."""
        return self._class_map.get(name)

    def get_edge_type(self, source: str, target: str) -> Optional[str]:
        """Get the dependency type between two nodes."""
        if self.graph.has_edge(source, target):
            return self.graph[source][target].get("dep_type")
        return None

    def get_stats(self) -> dict:
        """Return graph statistics."""
        method_count = sum(1 for _, d in self.graph.nodes(data=True)
                          if d.get("type") == "method")
        class_count = sum(1 for _, d in self.graph.nodes(data=True)
                         if d.get("type") == "class")

        return {
            "total_nodes": self.graph.number_of_nodes(),
            "total_edges": self.graph.number_of_edges(),
            "classes": class_count,
            "methods": method_count,
            "has_cycles": not nx.is_directed_acyclic_graph(self.graph),
        }

    def to_dict(self) -> dict:
        """Export graph as a dictionary (for API/frontend consumption)."""
        nodes = []
        for node_id, data in self.graph.nodes(data=True):
            nodes.append({
                "id": node_id,
                "type": data.get("type", "unknown"),
                "label": node_id.split(".")[-1] if "." in node_id else node_id,
            })

        edges = []
        for source, target, data in self.graph.edges(data=True):
            edges.append({
                "source": source,
                "target": target,
                "type": data.get("dep_type", "unknown"),
            })

        return {"nodes": nodes, "edges": edges}
