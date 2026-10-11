"""Build an integration-only zip; never include caches or private data."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from check_release import main as validate

ROOT=Path(__file__).resolve().parents[1]


def main():
    validate()
    output=ROOT/'comfort_sense-0.1.0a1.zip'
    component=ROOT/'custom_components/comfort_sense'
    with ZipFile(output,'w',ZIP_DEFLATED) as archive:
        for path in sorted(component.rglob('*')):
            if path.is_file() and path.suffix in ('.py','.json') and '__pycache__' not in path.parts:
                archive.write(path,path.relative_to(ROOT))
    print(f'Created {output.name}')


if __name__=='__main__':main()
