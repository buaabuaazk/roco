"""将当前 BWIKI 采集批次及原始模块打包，便于传回开发电脑。"""
import argparse
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def pack(data_dir, output):
    data_dir = Path(data_dir).resolve()
    manifest_file = data_dir / 'converted/manifest.json'
    manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
    if manifest['status'] != 'complete':
        raise ValueError('当前批次未完整转换，请先检查采集命令的错误或缺失引用')
    files = [manifest_file, data_dir / 'modules/response.json']
    metadata = data_dir / 'modules/fetch.json'
    if metadata.exists():
        files.append(metadata)
    for name in manifest['files']:
        path = (data_dir / 'converted' / name).resolve()
        if not path.is_relative_to(data_dir / 'converted'):
            raise ValueError('manifest 中包含目录外的路径')
        files.append(path)
    files = sorted(set(files))
    for path in files:
        if not path.is_file():
            raise FileNotFoundError(f'待打包文件缺失：{path}')
    output = Path(output).resolve()
    if output in files:
        raise ValueError('压缩包路径不能覆盖资料文件')
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + '.tmp')
    try:
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in files:
                archive.write(path, str(Path('data/bwiki') / path.relative_to(data_dir)))
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return {'archive': str(output), 'pets': manifest['pets'], 'skills': manifest['skills'],
            'features': manifest['features'], 'files': len(files)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'data/bwiki')
    parser.add_argument('--output', type=Path, default=ROOT / 'bwiki-data.zip')
    args = parser.parse_args()
    try:
        print(json.dumps(pack(args.data_dir, args.output), ensure_ascii=False, indent=4))
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f'打包失败：{exc}\n')


if __name__ == '__main__':
    main()
