"""Bounded source/metadata checks; no external services or HA writes."""
import ast
import json
import re
import struct
import tomllib
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

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
    assert manifest['version']==tomllib.loads((ROOT/'pyproject.toml').read_text())['project']['version']
    assert manifest['integration_type']=='service'
    assert (ROOT/'LICENSE').is_file()
    strings=json.loads((COMPONENT/'strings.json').read_text(encoding='utf-8'))
    translated=json.loads((COMPONENT/'translations/en.json').read_text(encoding='utf-8'))
    assert strings==translated
    for section in ['config','options']:
        assert set(strings[section]['step'])=={'system','manage','room','review','init','schedules','schedule','schedule_settings','room_gains','advanced','presets','relay','average_pid','average_gains','schedule_details','morning','alarm_owner'}
    for path in COMPONENT.rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts:
            assert path.suffix in ('.py','.json','.png'), f'Unexpected integration artifact: {path.name}'
            if path.suffix=='.png':
                assert path.parent==COMPONENT/'brand', 'Brand images belong in brand/'
    for path,size in [(COMPONENT/'brand/icon.png',256), (COMPONENT/'brand/icon@2x.png',512),
                      (ROOT/'docs/assets/logo.png',512)]:
        header=path.read_bytes()[:33]
        assert header[:8]==b'\x89PNG\r\n\x1a\n', f'Invalid PNG: {path.name}'
        assert struct.unpack('>II',header[16:24])==(size,size), f'Wrong icon dimensions: {path.name}'
        assert header[25]==6, f'RGBA transparency expected: {path.name}'
    readme=(ROOT/'README.md').read_text(encoding='utf-8')
    links=re.findall(r'(?:src|href)="([^"]+)"|\]\(([^)]+)\)',readme)
    hacs_links=[]
    for pair in links:
        target=next(v for v in pair if v).replace('&amp;','&')
        if target.startswith('https://my.home-assistant.io/redirect/hacs_repository/'):
            hacs_links.append(target)
        if not urlparse(target).scheme and not target.startswith('#'):
            assert (ROOT/unquote(target.split('#',1)[0])).exists(), f'Missing README target: {target}'
    assert hacs_links, 'README needs an install-in-HACS link'
    for target in hacs_links:
        assert parse_qs(urlparse(target).query)=={
            'owner':['spikked27'],'repository':['Comfort-Sense-Thermostat-HA'],'category':['integration']}
    print('Source, metadata, brand PNGs, README assets and HACS links validated.')


if __name__=='__main__':main()
