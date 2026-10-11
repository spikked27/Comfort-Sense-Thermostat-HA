"""Build an integration-only zip; never include caches or private data."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import json
from check_release import main as validate

ROOT=Path(__file__).resolve().parents[1]


def main():
    validate()
    component=ROOT/'custom_components/comfort_sense'
    version=json.loads((component/'manifest.json').read_text())['version']
    output=ROOT/f'comfort_sense-{version}.zip'
    with ZipFile(output,'w',ZIP_DEFLATED) as archive:
        for path in sorted(component.rglob('*')):
            if path.is_file() and path.suffix in ('.py','.json','.png') and '__pycache__' not in path.parts:
                archive.write(path,path.relative_to(ROOT))
    print(f'Created {output.name}')


if __name__=='__main__':main()
