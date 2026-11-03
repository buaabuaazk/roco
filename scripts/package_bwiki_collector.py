"""构建可直接复制到另一台电脑运行的 BWIKI 采集包。"""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    files = {
        'scripts/collect_bwiki_modules.py': ROOT / 'scripts/collect_bwiki_modules.py',
        'scripts/pack_bwiki_results.py': ROOT / 'scripts/pack_bwiki_results.py',
        'README.md': ROOT / 'docs/collector_portable.md',
    }
    output = ROOT / 'exports/roco-bwiki-collector.zip'
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, path in files.items():
            archive.write(path, 'roco-bwiki-collector/' + name)
        archive.writestr('roco-bwiki-collector/package.json', json.dumps({
            'package': 'roco-bwiki-collector', 'python': '>=3.10',
            'files_sha256': {name: hashlib.sha256(path.read_bytes()).hexdigest()
                             for name, path in files.items()},
        }, ensure_ascii=False, indent=4) + '\n')
    print(output)


if __name__ == '__main__':
    main()
