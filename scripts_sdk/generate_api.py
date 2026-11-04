"""Regenerate named endpoint methods and reference from the bundled Swagger."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bitteam_sdk.endpoints import CATALOG, snake
import json

root = Path(__file__).resolve().parents[1] / 'bitteam_sdk'
live = {}
if (root / 'LIVE_CHECKS.json').exists():
    for item in json.loads((root / 'LIVE_CHECKS.json').read_text(encoding='utf-8'))['rest']:
        live[item['method']] = 'OK' if item['ok'] else 'HTTP ' + str(item.get('http_status', item.get('error_type', 'unknown')))
code = ['"""Generated API methods. Regenerate with scripts_sdk/generate_api.py."""',
        'from .endpoints import EndpointAPI', '', '', 'class BitTeamAPI(EndpointAPI):']
rows = ['# BitTeam API reference - 2026-11-03', '',
        'Use `client.api.<method>(path_arguments, params={...}, data={...})`.',
        'Responses preserve the original JSON shape. Server callbacks and dev operations are listed but not callable.',
        'All client routes have named methods; this catalog does not imply successful live verification of private routes.', '',
        '| Method | HTTP endpoint | Access | Body contract | Live public check |', '|---|---|---|---|---|']
for name, entry in CATALOG.items():
    op = entry['operation']
    params = [p['name'] for p in op.get('parameters', []) if p['in'] == 'path']
    args = ', '.join(snake(p) for p in params)
    signature = (args + ', ' if args else '') + '*, params=None, data=None'
    mapping = '{' + ', '.join(repr(p) + ': ' + snake(p) for p in params) + '}'
    desc = op.get('summary', '').replace('"', '').replace('\n', ' ')
    code += ['', f'    async def {name}(self, {signature}):',
             f'        """{entry["method"]} {entry["path"]}. {desc}"""',
             f'        return await self.call({name!r}, path={mapping}, params=params, data=data)']
    access = 'server-only' if entry['server_only'] else ('public' if entry['public'] else 'private')
    body = 'incomplete' if entry['method'] == 'POST' and not any(p['in'] == 'body' for p in op.get('parameters', [])) else 'Swagger'
    rows.append(f'| `{name}` | `{entry["method"]} {entry["path"]}` | {access} | {body} | {live.get(name, "not run")} |')
(root / 'api.py').write_text('\n'.join(code) + '\n', encoding='utf-8')
(root / 'API_REFERENCE.md').write_text('\n'.join(rows) + '\n', encoding='utf-8')
print(f'Generated {len(CATALOG)} endpoint methods')
