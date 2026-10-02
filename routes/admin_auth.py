"""
관리자 인증 및 권한 제어 모듈 (admin_auth.py)
- @admin_required 데코레이터
- 관리자 로그인/로그아웃 및 profiles 테이블 role='admin' 검증
"""

import sys
from functools import wraps
from flask import session, redirect, url_for, request, abort, flash
from utils.db import (
    get_admin_client as get_admin_supabase_client,
    get_supabase_client as get_anon_supabase_client,
)


def is_admin_user(user_id: str) -> bool:
    """
    주어진 user_id가 profiles 테이블에서 role='admin'인지 검증
    """
    if not user_id:
        return False

    # 1. 세션에 이미 검증된 admin 역할이 있는 경우 우선 통과
    if session.get("role") == "admin" and session.get("user_id") == user_id:
        return True

    # 2. Supabase profiles 테이블 조회
    client = get_admin_supabase_client() or get_anon_supabase_client()
    if not client:
        return False

    try:
        res = (
            client.table("profiles")
            .select("role")
            .eq("id", user_id)
            .maybe_single()
            .execute()
        )
        if res and res.data:
            role = res.data.get("role")
            if role == "admin":
                session["role"] = "admin"
                return True
    except Exception as e:
        print(f"[관리자 권한 조회 오류] {e}", file=sys.stderr)

    return False


def is_direct_address_bar_access(req) -> bool:
    """
    브라우저 주소창 직접 입력(Direct URL Navigation / Bookmark) 감지 함수
    - 관리자 대시보드 화면(/admin/dashboard) 등 HTML 페이지 탐색을 주소창으로 직접 시도하는 행위 차단
    - POST 요청 또는 AJAX/API 요청은 주소창 직접 탐색이 아니므로 제외
    - W3C Fetch Metadata 표준: Sec-Fetch-Site == 'none'인 경우 (주소창 타이핑, 북마크 클릭)
    - Referer 헤더가 없거나(None/빈값) 동일 사이트 내부 호스트가 아닌 경우
    """
    from flask import current_app

    # 테스트 환경 우회용 헤더 확인
    if current_app and current_app.config.get("TESTING") and req.headers.get("X-Test-Allow-Direct"):
        return False

    # 1. POST 요청이나 API/JSON 요청은 주소창 직접 타이핑이 아님
    if req.method != "GET" or req.is_json or req.path.startswith("/admin/api/"):
        return False

    sec_fetch_site = req.headers.get("Sec-Fetch-Site")
    referrer = req.referrer
    entry_param = req.args.get("entry")

    # 2. 사이트 내부 버튼 클릭(entry=portal)으로 유입되었고, 순수 주소창 타이핑(none)이 아니면 허용
    if entry_param == "portal" and sec_fetch_site != "none":
        return False

    # 3. 브라우저 표준 Fetch Metadata: 'none'은 주소창 타이핑 또는 북마크 접속을 명시
    if sec_fetch_site == "none":
        return True

    # 4. Referer 헤더가 없는 경우 (주소창 직접 타이핑 접속)
    if not referrer:
        return True

    # 5. Referer가 현재 사이트의 호스트가 아닌 경우 (외부 사이트 링크 유입 등)
    host_url = req.host_url.rstrip("/")
    if not referrer.startswith(host_url):
        return True

    return False


def admin_required(f):
    """
    관리자 전용 접근 제어 데코레이터
    - 로그인하지 않은 경우: 403 Forbidden (login_required_for_admin) 표시하여 관리자 화면 노출 차단
    - 로그인했지만 admin 권한이 없는 경우(role != 'admin'): 403 Forbidden 페이지 표시
    - 브라우저 주소창 직접 입력으로 접근 시: 403 Forbidden (direct_url_blocked) 표시
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get("user_id")

        # 1. 미로그인 상태 -> 관리자 로그인 화면을 노출하지 않고 403 Forbidden 차단
        if not user_id:
            abort(403, description="login_required_for_admin")

        # 2. 로그인되어 있으나 관리자 권한(role='admin')이 없는 경우 -> 403 Forbidden
        if not is_admin_user(user_id):
            abort(403, description="not_admin_role")

        # 3. 브라우저 주소창 직접 입력(Direct URL Navigation) 차단
        # 관리자 로그인 직후 리다이렉트되어 진입하는 경우 세션 플래그를 통해 허용
        is_login_redirect = session.pop("_admin_login_redirect", False)
        if not is_login_redirect and is_direct_address_bar_access(request):
            abort(403, description="direct_url_blocked")

        return f(*args, **kwargs)

    return decorated_function
