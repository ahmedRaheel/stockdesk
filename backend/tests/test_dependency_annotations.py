"""Guard against FastAPI dependency aliases being given a second Depends default."""
import ast
from pathlib import Path


def test_annotated_user_alias_is_not_redeclared_with_default():
    app = Path(__file__).resolve().parents[1] / "app"
    for module in app.rglob("*.py"):
        tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            args = node.args.args + node.args.kwonlyargs
            positional_defaults = {a.arg: d for a, d in zip(node.args.args[-len(node.args.defaults):], node.args.defaults)} if node.args.defaults else {}
            keyword_defaults = dict(zip(node.args.kwonlyargs, node.args.kw_defaults))
            for a in args:
                if not isinstance(a.annotation, ast.Name) or a.annotation.id != "User":
                    continue
                default = positional_defaults.get(a.arg, keyword_defaults.get(a.arg))
                assert not (isinstance(default, ast.Call) and isinstance(default.func, ast.Name) and default.func.id == "Depends"), (module, node.name, a.arg)
