import ast
from pathlib import Path

class CodeIntelligenceEngine:
    """Python source inventory and documentation starter using the standard-library AST parser."""
    def analyze_python(self, source: str, filename: str = "source.py") -> dict:
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            return {"filename": filename, "error": str(exc)}
        functions, classes, imports = [], [], []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append({"name": node.name, "line": node.lineno,
                                  "docstring": ast.get_docstring(node) or ""})
            elif isinstance(node, ast.ClassDef):
                classes.append({"name": node.name, "line": node.lineno,
                                "methods": [n.name for n in node.body
                                            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]})
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                imports.append(ast.unparse(node))
        return {"filename": filename, "functions": functions,
                "classes": classes, "imports": sorted(set(imports))}

    def analyze_file(self, path: str) -> dict:
        p = Path(path)
        if p.suffix != ".py": raise ValueError("Only Python files are supported in this MVP.")
        return self.analyze_python(p.read_text(encoding="utf-8"), p.name)
