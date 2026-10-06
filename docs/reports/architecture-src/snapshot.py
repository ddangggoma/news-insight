from pathlib import Path
import ast, json, re, tomllib, subprocess, sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'apps/api/src'))
from news_insight.main import app
from news_insight.taxonomy.catalog import FIELDS, SIGNAL_TYPES, IMPACTS, SCOPES, TAXONOMY_REVISION
from news_insight.strategy.personas import PERSONAS
paths=[]
for directory in ['apps/api/src','apps/api/tests','apps/api/migrations','apps/api/scripts','apps/web/app','apps/web/components','apps/web/lib','apps/web/hooks','apps/web/tests','apps/web/e2e','scripts','ops/launchd','.github/workflows']:
    paths += [p for p in (ROOT/directory).rglob('*') if p.is_file() and p.suffix in ['.py','.ts','.tsx','.css','.sh','.yaml','.yml','.template']]
for name in ['README.md','compose.yaml','compose.override.yaml','ops/Caddyfile','ops/caddy/Dockerfile','apps/api/pyproject.toml','apps/api/Dockerfile','apps/web/package.json','apps/web/next.config.ts','apps/web/components.json','apps/web/tsconfig.json','apps/web/proxy.ts','apps/web/playwright.config.ts','apps/web/vitest.config.ts','apps/web/Dockerfile']:
    paths.append(ROOT/name)
paths+= list((ROOT/'docs/runbooks').glob('*.md'))
files=[]; tables=[]; symbols=[]; configs=[]
for p in sorted(set(paths)):
    raw=p.read_text(); rel=str(p.relative_to(ROOT)); doc=''; syms=[]; imports=[]
    if p.suffix=='.py':
        tree=ast.parse(raw)
        doc=ast.get_docstring(tree) or ''
        for n in ast.walk(tree):
            if isinstance(n,ast.ImportFrom) and n.module: imports.append(n.module)
            if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
                syms.append({'name':n.name,'line':n.lineno,'end':n.end_lineno,'kind':'class' if isinstance(n,ast.ClassDef) else 'function','doc':ast.get_docstring(n) or ''})
        for n in tree.body:
            if not isinstance(n,ast.ClassDef): continue
            tab=None
            for a in n.body:
                if isinstance(a,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='__tablename__' for t in a.targets): tab=ast.literal_eval(a.value)
            if tab:
                cols=[]; constraints=[]
                for a in n.body:
                    if isinstance(a,ast.AnnAssign):
                        cols.append({'name':a.target.id,'type':ast.unparse(a.annotation),'definition':ast.unparse(a.value) if a.value else 'annotation-inferred','line':a.lineno})
                    if isinstance(a,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='__table_args__' for t in a.targets): constraints.append(ast.unparse(a.value))
                tables.append({'name':tab,'class':n.name,'path':rel,'line':n.lineno,'doc':ast.get_docstring(n) or '', 'columns':cols,'constraints':constraints})
            if n.name=='Settings':
                for a in n.body:
                    if isinstance(a,ast.AnnAssign): configs.append({'name':a.target.id,'type':ast.unparse(a.annotation),'default':ast.unparse(a.value) if a.value else ''})
    elif p.suffix in ['.ts','.tsx']:
        imports=re.findall(r'from\s+[\"\']([^\"\']+)',raw)
        for m in re.finditer(r'(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(\w+)',raw): syms.append({'name':m[1],'line':raw[:m.start()].count('\n')+1,'kind':'function','doc':''})
    # Source snapshot excludes runtime secrets, and replaces sample credentials / personal addresses.
    raw=re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '[email redacted]',raw)
    raw=raw.replace('news-dev-password','[sample-password]')
    files.append({'path':rel,'lines':len(raw.splitlines()),'code':raw,'doc':doc,'symbols':syms,'imports':sorted(set(imports)),'client':bool(re.search(r'^[\"\']use client[\"\']',raw))})
    symbols += [{'path':rel,**s} for s in syms]
lock=tomllib.loads((ROOT/'apps/api/uv.lock').read_text())
package=json.loads((ROOT/'apps/web/package.json').read_text())
pyproject=tomllib.loads((ROOT/'apps/api/pyproject.toml').read_text())
import yaml
catalog=yaml.safe_load((ROOT/'apps/api/catalog/sources.yaml').read_text())
print('catalog type',type(catalog).__name__,list(catalog)[:5] if isinstance(catalog,dict) else len(catalog))
snapshot={'files':files,'tables':tables,'symbols':symbols,'settings':configs,'openapi':app.openapi(),'web':package,'python':pyproject['project']['dependencies'],'python_lock':{x['name']:x['version'] for x in lock['package']},'taxonomy':{'revision':TAXONOMY_REVISION,'fields':[{'key':f.key,'name':f.name,'themes':[{'key':t.key,'name':t.name} for t in f.themes]} for f in FIELDS],'signals':[{'key':n.key,'name':n.name} for n in SIGNAL_TYPES]},'personas':[p.__dict__ for p in PERSONAS],'commit':subprocess.check_output(['/opt/homebrew/bin/git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'catalog_count':len(catalog.get('sources',[])) if isinstance(catalog,dict) else len(catalog)}
# Redact sample settings from exported metadata too.
for c in configs:
    c['default']=re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '[email redacted]',c['default'])
out=json.dumps(snapshot,ensure_ascii=False).replace('news-dev-password','[sample-password]')

Path(sys.argv[1] if len(sys.argv)>1 else '.build/snapshot.json').write_text(out)
print(json.dumps({'files':len(files),'lines':sum(f['lines'] for f in files),'tables':len(tables),'symbols':len(symbols),'api_paths':len(snapshot['openapi']['paths']),'fields':len(FIELDS),'themes':sum(len(f.themes) for f in FIELDS),'bytes':len(out.encode())}))
