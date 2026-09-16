"""Create an untracked, paired extension for this PC. Never distribute its token."""
import json
import shutil
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import Settings

cfg = Settings()
if not cfg.browser_bridge_token:
    raise SystemExit('Set LOCAL_LLM_BROWSER_BRIDGE_TOKEN in .env first.')
root = Path(__file__).resolve().parents[1]
target = root / 'data' / 'browser-extension'
shutil.copytree(root / 'browser-extension', target, dirs_exist_ok=True)
(target / 'config.js').write_text('const BRIDGE_TOKEN = ' + json.dumps(cfg.browser_bridge_token) + ';\n', encoding='utf-8')
print('Chrome 확장 프로그램 > 개발자 모드 > 압축해제된 확장 프로그램 로드:')
print(target)
