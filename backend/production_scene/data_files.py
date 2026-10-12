"""Optional local scene payloads. No production request selects a filesystem path."""
import json
from pathlib import Path
from django.conf import settings
from control.catalog import APIError


def data_root():
    return Path(settings.PRODUCTION_SCENE_DATA_DIR).expanduser().resolve()


def read_data(name, *, optional=False):
    file = data_root() / name
    try:
        return json.loads(file.read_text(encoding='utf-8'))
    except FileNotFoundError as exc:
        if optional:
            return None
        raise APIError('DEMO_DATA_MISSING', '本地演示包未安装，请执行 install_demo_bundle 并设置 PRODUCTION_SCENE_DATA_DIR', 503) from exc
    except (OSError, ValueError) as exc:
        raise APIError('DEMO_DATA_INVALID', '本地演示文件无法读取或格式错误：' + name, 503) from exc
