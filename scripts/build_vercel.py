"""Copy only public UI assets. Never copy data, configuration or private reports."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ('app.js', 'styles.css', 'layout.css', 'mark.svg')

def build_assets(root=ROOT):
    destination = root / 'public' / 'static'
    destination.mkdir(parents=True, exist_ok=True)
    for name in ASSETS:
        source = root / 'xcomify' / 'static' / name
        if not source.is_file():
            raise RuntimeError('Required UI asset is missing: ' + name)
        shutil.copy2(source, destination / name)
    return len(ASSETS)

if __name__ == '__main__':
    print('Prepared', build_assets(), 'public UI assets. No credentials or databases copied.')
