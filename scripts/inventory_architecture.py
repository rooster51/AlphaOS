"""Read-only static inventory; no application imports, credentials or network calls.

Import reachability is conservative (including imports inside functions). It is
evidence for review, never an automatic dead-code/dependency deletion decision.
"""
import argparse
import ast
from collections import defaultdict
import json
from pathlib import Path
import re
import subprocess
import sys


def module_name(path):
    name = path.removesuffix('.py').replace('/', '.')
    return name.removesuffix('.__init__')


def python_graph(root, files):
    modules = {module_name(path): path for path in files if path.endswith('.py')}
    edges = {name: set() for name in modules}
    external = defaultdict(set)
    lazy = defaultdict(set)
    trees = {}
    for name, path in modules.items():
        tree = ast.parse((root / path).read_text(encoding='utf-8-sig'))
        trees[path] = tree
        package = name if path.endswith('/__init__.py') else name.rpartition('.')[0]

        def record(target, scope):
            resolved = target if target in modules else 'tests.' + target if 'tests.' + target in modules else None
            if resolved:
                edges[name].add(resolved)
                if scope: lazy[name].add(resolved)
            elif target and target.split('.')[0] not in sys.stdlib_module_names:
                external[name].add(target.split('.')[0])

        class Imports(ast.NodeVisitor):
            scope = 0

            def visit_FunctionDef(self, node):
                self.scope += 1
                self.generic_visit(node)
                self.scope -= 1

            visit_AsyncFunctionDef = visit_FunctionDef

            def visit_Import(self, node):
                for alias in node.names: record(alias.name, self.scope)

            def visit_ImportFrom(self, node):
                base = node.module or ''
                if node.level:
                    parts = package.split('.') if package else []
                    base = '.'.join(parts[:len(parts) - node.level + 1] + ([base] if base else []))
                record(base, self.scope)
                for alias in node.names:
                    child = base + '.' + alias.name
                    if child in modules: record(child, self.scope)

            def visit_Call(self, node):
                if (ast.unparse(node.func) in ('importlib.import_module', '__import__') and node.args
                        and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                    record(node.args[0].value, self.scope)
                self.generic_visit(node)

        Imports().visit(tree)
    return modules, edges, external, lazy, trees


def reachable(edges, roots):
    seen, pending = set(), list(roots)
    while pending:
        name = pending.pop()
        if name in seen: continue
        seen.add(name)
        pending.extend(edges.get(name, ()))
    return sorted(seen)


def web_graph(root, files):
    paths = set(files)
    graph = {}
    for path in files:
        if not path.startswith('web/src/') or not path.endswith(('.ts', '.tsx')): continue
        dependencies = []
        source = (root / path).read_text(encoding='utf-8-sig')
        for target in re.findall(r'''(?:\bfrom\s+|\bimport\s*\(\s*|\bimport\s+)["']([^"']+)["']''', source):
            if target.startswith('@/'): base = root / 'web/src' / target[2:]
            elif target.startswith('.'): base = (root / path).parent / target
            else: continue
            base = base.resolve().relative_to(root.resolve()).as_posix()
            resolved = next((p for p in (base,base+'.ts',base+'.tsx',base+'/index.ts',base+'/index.tsx') if p in paths), None)
            if resolved: dependencies.append(resolved)
        graph[path] = sorted(set(dependencies))
    return graph


def inventory(root, files, baseline):
    modules, edges, external, lazy, trees = python_graph(root, files)
    groups = {
        'api': ['alphaos_api.__main__', 'alphaos_api.app'],
        'archive_contract': ['alphaos_api.research2'],
        'streamlit': ['app', 'streamlit_app'] + [module_name(p) for p in files if p.startswith('pages/') and p.endswith('.py')],
        'cli': [module_name(p) for p in files if p.startswith('scripts/') and p.endswith('.py')],
        'tests': [module_name(p) for p in files if p.startswith('tests/') and p.endswith('.py')],
        'disabled_pages': [module_name(p) for p in files if p.startswith('disabled_pages/') and p.endswith('.py')],
    }
    closures = {group: reachable(edges, roots) for group, roots in groups.items()}
    rest, mcp = [], []
    duplicates = defaultdict(list)
    for path, tree in trees.items():
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)): continue
            if path == 'alphaos_api/mcp_server.py' and any(isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == 'tool' for d in node.decorator_list):
                targets = [ast.unparse(c.args[0]) for c in ast.walk(node) if isinstance(c,ast.Call)
                           and isinstance(c.func,ast.Name) and c.func.id == 'invoke' and c.args]
                mcp.append(dict(name=node.name, signature=ast.unparse(node.args), targets=targets))
            if path in ('alphaos_api/app.py', 'alphaos_api/phase9_routes.py', 'alphaos_api/research2.py'):
                for d in node.decorator_list:
                    if not (isinstance(d,ast.Call) and isinstance(d.func,ast.Attribute) and d.func.attr in ('get','post') and d.args and isinstance(d.args[0],ast.Constant)): continue
                    prefix = '/v1' if ast.unparse(d.func.value) == 'router' else ''
                    operation = next((k.value.value for k in d.keywords if k.arg == 'operation_id' and isinstance(k.value,ast.Constant)), None)
                    rest.append(dict(method=d.func.attr.upper(), path=prefix+d.args[0].value, operation_id=operation, source=path, handler=node.name))
        if path.startswith(('modules/','alphaos_api/')):
            for node in tree.body:
                if isinstance(node,ast.FunctionDef):
                    key = ast.dump(ast.Module(body=node.body, type_ignores=[]), include_attributes=False)
                    if len(key) > 100: duplicates[key].append(f'{path}:{node.name}')
    web = web_graph(root,files)
    web_roots = [p for p in web if p.startswith('web/src/app/')]
    website_routes = []
    for path in web_roots:
        filename = Path(path).name
        if filename not in ('page.tsx', 'route.ts'): continue
        route = '/' + '/'.join(Path(path).parts[3:-1])
        source = (root / path).read_text(encoding='utf-8-sig')
        methods = sorted(set(re.findall(r'export\s+(?:async\s+)?function\s+(GET|POST|PUT|PATCH|DELETE)\b', source)))
        for export in re.findall(r'export\s*\{([^}]+)\}', source):
            methods.extend(re.findall(r'\b(GET|POST|PUT|PATCH|DELETE)\b', export))
        website_routes.append(dict(path=route, source=path, methods=sorted(set(methods)) if filename == 'route.ts' else ['PAGE']))
    requirements = {p:[line.strip() for line in (root/p).read_text().splitlines()
                       if line.strip() and not line.lstrip().startswith('#')]
                    for p in files if p.startswith('requirements') and p.endswith('.txt')}
    return dict(
        baseline=baseline, source_state='working tree based on baseline; not a checkout of that commit',
        limitations=['Static imports include lazy/conditional paths; reachability is not proof of runtime use.',
                     'Dynamic Streamlit page discovery is included as explicit roots.',
                     'String references, external consumers and compatibility contracts require manual review.',
                     'Duplicate function bodies may depend on different globals or validation rules; never auto-merge.'],
        counts=dict(tracked_files=len(files), python_files=len(modules), python_test_files=sum(p.startswith('tests/') for p in trees),
                    rest_operations=len(rest), mcp_tools=len(mcp)),
        rest=rest, mcp=mcp,
        website_routes=website_routes,
        python={name:dict(path=path, imports=sorted(edges[name]), lazy_imports=sorted(lazy[name]),
                         external_import_roots=sorted(external[name]), reached_from=[g for g in closures if name in closures[g]])
                for name,path in sorted(modules.items())},
        duplicate_function_body_candidates=sorted(v for v in duplicates.values() if len(v)>1),
        web_imports=web, web_reachable=reachable(web,web_roots),
        streamlit_pages=[p for p in files if p.startswith('pages/')],
        disabled_pages=[p for p in files if p.startswith('disabled_pages/')],
        docs=[p for p in files if p.startswith('docs/') or p in ('README.md','ALPHAOS_2_BUILD_STATUS.md','web/DEPLOYMENT.md')],
        dependency_files=[p for p in files if p.startswith('requirements') or p in ('web/package.json','web/package-lock.json','.python-version','runtime.txt')],
        python_requirements=requirements,
        web_package=json.loads((root/'web/package.json').read_text()) if 'web/package.json' in files else {},
        workflows=[p for p in files if p.startswith('.github/workflows/')])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True, help='Audited Git commit; recorded as provenance, not checked out')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    files = subprocess.check_output(['git','ls-files','-z'],cwd=root).decode().rstrip('\0').split('\0')
    existing = [path for path in files if (root / path).is_file()]
    result = inventory(root,existing,args.baseline)
    result['missing_tracked_files'] = sorted(set(files) - set(existing))
    print(json.dumps(result,indent=2,sort_keys=True))


if __name__ == '__main__':
    main()
