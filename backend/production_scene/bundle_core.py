"""Validate a local data ZIP before any write; never extract or execute its code."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import zipfile

MAX_TOTAL = 128 * 1024 * 1024
MAX_FILE = 64 * 1024 * 1024
REQUIRED = {'production-catalog.json', 'escape-policy.json', 'szg-8h.json', 'legacy/escape-policy-v2.json'}


def validate_bundle(path):
    payload = {}
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > 256 or len({x.filename for x in entries}) != len(entries):
            raise ValueError('包文件数量超限或存在重复路径')
        if sum(x.file_size for x in entries) > MAX_TOTAL:
            raise ValueError('包解压体积超过限制')
        for item in entries:
            name = item.filename
            parts = PurePosixPath(name)
            mode = item.external_attr >> 16
            if (parts.is_absolute() or '..' in parts.parts or '\\' in name
                    or str(parts) != name or item.is_dir()
                    or stat.S_IFMT(mode) not in (0, stat.S_IFREG) or item.file_size > MAX_FILE):
                raise ValueError('不安全的包路径或文件类型：' + name)
            if name != 'manifest.json' and not name.startswith('payload/'):
                raise ValueError('未声明的包路径：' + name)
        if not any(x.filename == 'manifest.json' and x.file_size <= 256 * 1024 for x in entries):
            raise ValueError('缺少有效 manifest.json')
        manifest = json.loads(archive.read('manifest.json'))
        if manifest.get('format') != 'compute-dashboard-local-demo-v1' or not isinstance(manifest.get('files'), list):
            raise ValueError('不支持的演示包格式')
        listed = set()
        for row in manifest['files']:
            name = row['path']
            if not isinstance(name, str) or name in listed:
                raise ValueError('清单路径重复或无效')
            listed.add(name)
            archive_name = 'payload/' + name
            data = archive.read(archive_name)
            if len(data) != row['size'] or hashlib.sha256(data).hexdigest() != row['sha256']:
                raise ValueError('演示文件 SHA256/大小校验失败：' + name)
            # ZIP path safety was checked above; payload itself is stored inertly.
            payload[name] = data
        if set(x.filename for x in entries) != {'manifest.json'} | {'payload/' + x for x in listed}:
            raise ValueError('包文件与 manifest 不一致')
        if not REQUIRED.issubset(listed):
            raise ValueError('演示包缺少必需文件')
    from .catalog_core import compile_catalog
    from .coverage_core import check_dataset
    from .recovery_core import compile_plan
    packet = json.loads(payload['production-catalog.json'])
    if packet.get('normalization_version') == 4 or manifest.get('scene_version') == 'szg8h.4':
        if not {'legacy/production-catalog-v3.json','legacy/escape-policy-v3.json'}.issubset(listed):
            raise ValueError('v4 演示包缺少旧目录纠正的校验文件')
    if manifest.get('scene_version') == 'szg8h.5':
        if not {'legacy/production-catalog-v3.json','legacy/escape-policy-v3.json','legacy/production-catalog-v4.json','legacy/escape-policy-v4.json'}.issubset(listed):
            raise ValueError('v5 演示包缺少旧目录修订的校验文件')
    catalog = compile_catalog(packet)
    policy = json.loads(payload['escape-policy.json'])
    plan = compile_plan(policy, catalog['catalog'])
    dataset = json.loads(payload['szg-8h.json'])
    coverage = check_dataset(dataset)
    if (dataset['bundle_id'] != catalog['bundle_id'] or dataset['catalog_source_hash'] != catalog['source_hash']
            or policy['catalog_bundle_id'] != catalog['bundle_id']
            or not any(p['plan_id'] == plan['plan_id'] and p['content_sha256'] == plan['content_sha256']
                       for p in dataset['catalog'].get('escape-plans', []))):
        raise ValueError('资源目录、预案与回放文件不匹配')
    return manifest, payload, coverage


def install_payload(payload, root, *, apply=False):
    root = Path(root).expanduser().absolute()
    if root.is_symlink():
        raise ValueError('目标目录不能是符号链接：' + str(root))
    # Resolve OS aliases such as macOS /var, then reject links within the chosen root.
    root = root.parent.resolve() / root.name
    paths = []
    for name, data in payload.items():
        parts = PurePosixPath(name)
        if parts.is_absolute() or '..' in parts.parts or '\\' in name or str(parts) != name or name == '.':
            raise ValueError('不安全的目标路径：' + name)
        target = root / name
        for part in (target, *target.parents):
            if part.is_symlink():
                raise ValueError('目标包含符号链接：' + str(part))
            if part == root:
                break
        if target.exists() and (not target.is_file() or target.read_bytes() != data):
            raise ValueError('目标已有不同文件，未覆盖：' + str(target))
        paths.append((target, data))
    created = []
    if apply:
        try:
            for target, data in paths:
                if target.exists():
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open('xb') as out:
                    created.append(target)
                    out.write(data)
        except BaseException:
            for target in reversed(created):
                target.unlink(missing_ok=True)
            raise
    return {'applied': apply, 'files': len(paths), 'data_dir': str(root),
            'already_installed': all(target.exists() for target, _ in paths) if not apply else not created}
