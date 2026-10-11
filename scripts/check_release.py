"""Bounded source/metadata checks; no external services or HA writes."""
import ast
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
COMPONENT=ROOT/'custom_components/comfort_sense'


def main():
    for path in ROOT.rglob('*.py'):
        if '__pycache__' not in path.parts:
            ast.parse(path.read_text(encoding='utf-8'),filename=str(path))
    for path in ROOT.rglob('*.json'):
        json.loads(path.read_text(encoding='utf-8'))
    manifest=json.loads((COMPONENT/'manifest.json').read_text())
    assert manifest['domain']=='comfort_sense'
    assert manifest['config_flow'] is True
    assert manifest['version']=='0.1.0a1'
    assert (ROOT/'LICENSE').is_file()
    strings=json.loads((COMPONENT/'strings.json').read_text(encoding='utf-8'))
    translated=json.loads((COMPONENT/'translations/en.json').read_text(encoding='utf-8'))
    assert strings==translated
    for section in ['config','options']:
        assert set(strings[section]['step'])=={'system','manage','room','review'}
    for path in COMPONENT.rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts:
            assert path.suffix in ('.py','.json'), f'Unexpected integration artifact: {path.name}'
    print('Python syntax, JSON, metadata, English strings and integration contents validated.')


if __name__=='__main__':main()
