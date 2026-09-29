"""
app 패키지 초기화 모듈
- 최상위 app.py의 create_app 함수를 가져와 노출합니다.
"""

import sys
import os
import importlib.util

# 최상위 app.py 파일 경로
_ROOT_APP_PY = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app.py")
if os.path.exists(_ROOT_APP_PY):
    _spec = importlib.util.spec_from_file_location("_root_app_module", _ROOT_APP_PY)
    if _spec and _spec.loader:
        _root_app = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_root_app)
        create_app = getattr(_root_app, "create_app", None)


