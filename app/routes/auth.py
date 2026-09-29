"""
인증(Auth) 라우트 블루프린트 모듈
- Supabase Python 클라이언트를 사용하여 이메일 회원가입, 로그인, 이메일 인증, 비밀번호 찾기/재설정을 처리합니다.
"""

import os
import sys
import json
import secrets
import urllib.parse
import urllib.request
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, session
from dotenv import load_dotenv
from supabase import create_client, Client
from supabase_auth.errors import AuthApiError

# 환경 변수 최신화
load_dotenv()

# auth 블루프린트 생성 (url_prefix="/auth")
auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

# 한국어 에러 및 안내 메시지 매핑
AUTH_MESSAGES = {
    # 에러 메시지
    "email_not_confirmed": "이메일 인증이 완료되지 않았습니다. 수신된 이메일의 인증 링크를 확인해주세요.",
    "invalid_credentials": "이메일 또는 비밀번호가 올바르지 않습니다.",
    "missing_fields": "모든 필수 항목을 입력해주세요.",
    "password_mismatch": "비밀번호가 일치하지 않습니다.",
    "password_length": "비밀번호는 최소 6자 이상이어야 합니다.",
    "invalid_confirm_params": "이메일 인증 정보가 올바르지 않거나 만료되었습니다.",
    "confirm_failed": "이메일 인증에 실패했습니다. 다시 시도해주세요.",
    "signup_failed": "회원가입 처리 중 오류가 발생했습니다.",
    "rate_limit_exceeded": "이메일 발송 한도를 초과했습니다. Supabase 인증 메일 발송 제한으로 인해 잠시 후(약 1시간 후) 다시 시도해주세요.",
    "user_already_exists": "이미 가입된 이메일 계정입니다. 로그인 페이지에서 로그인해주세요.",
    "reset_request_failed": "비밀번호 재설정 이메일 전송에 실패했습니다.",
    "reset_failed": "비밀번호 변경에 실패했습니다. 유효하지 않거나 만료된 링크일 수 있습니다.",
    "login_required": "로그인이 필요한 서비스입니다.",
    "withdraw_failed": "회원 탈퇴 처리 중 오류가 발생했습니다. 다시 시도해주세요.",
    "oauth_failed": "소셜 로그인 연동 중 오류가 발생했습니다. 다시 시도해주세요.",
    # 성공 메시지
    "reset_mail_sent": "비밀번호 재설정 링크가 이메일로 발송되었습니다. 메일함을 확인해주세요.",
    "password_reset_success": "비밀번호가 성공적으로 변경되었습니다. 새 비밀번호로 로그인해주세요.",
    "logout_success": "성공적으로 로그아웃되었습니다.",
    "email_confirmed_success": "이메일 인증이 완료되었습니다! 로그인해주세요.",
    "already_confirmed": "이메일 인증이 완료되었습니다. 로그인해주세요.",
    "account_deleted": "회원 탈퇴가 완료되었습니다. 데이터베이스에서 모든 회원 정보가 영구 삭제되었습니다. (다시 소셜 로그인을 누르실 경우 새로운 신규 회원으로 가입됩니다.)",
}


def get_site_url() -> str:
    """사이트 URL 반환 (환경 변수 우선, 기본값 요청 host_url 또는 http://localhost:5000)"""
    env_site_url = os.getenv("SITE_URL")
    if env_site_url:
        return env_site_url.rstrip("/")
    if request:
        return request.host_url.rstrip("/")
    return "http://localhost:5000"


def get_supabase_client() -> Client:
    """Supabase 클라이언트 인스턴스 생성 및 반환"""
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_anon_key = os.getenv("SUPABASE_ANON_KEY")
    if not supabase_url or not supabase_anon_key:
        raise RuntimeError("SUPABASE_URL 또는 SUPABASE_ANON_KEY 환경 변수가 설정되지 않았습니다.")
    return create_client(supabase_url, supabase_anon_key)


def get_supabase_admin_client() -> Client:
    """Supabase 서비스 키 관리자 클라이언트 인스턴스 생성 및 반환"""
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_service_key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    if not supabase_url or not supabase_service_key:
        raise RuntimeError("SUPABASE_URL 또는 SUPABASE_SERVICE_KEY 환경 변수가 설정되지 않았습니다.")
    return create_client(supabase_url, supabase_service_key)


def login_required(f):
    """
    로그인 필수 데코레이터
    - Flask session에서 user_id를 확인합니다.
    - 미로그인 시 로그인 페이지로 리다이렉트합니다.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("auth.login", error="login_required"))
        return f(*args, **kwargs)
    return decorated_function


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """
    [1] GET/POST /auth/login - 로그인 폼 및 처리
    - 이메일 미인증 시 error=email_not_confirmed로 리다이렉트
    """
    # 이미 로그인된 상태면 메인 페이지로 이동
    if session.get("user_id"):
        return redirect(url_for("main.index"))

    error_code = request.args.get("error")
    success_code = request.args.get("success")
    error_msg = AUTH_MESSAGES.get(error_code, error_code) if error_code else None
    success_msg = AUTH_MESSAGES.get(success_code, success_code) if success_code else None

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        if not email or not password:
            return redirect(url_for("auth.login", error="missing_fields"))

        try:
            supabase = get_supabase_client()
            response = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })

            user = response.user
            auth_session = response.session

            if not user:
                return redirect(url_for("auth.login", error="invalid_credentials"))

            # 세션에 사용자 정보 저장 (user_id 필수 저장)
            session["user_id"] = user.id
            full_name = (user.user_metadata or {}).get("full_name") or email.split("@")[0]
            session["user"] = {
                "id": user.id,
                "email": user.email,
                "name": full_name
            }
            if auth_session:
                session["access_token"] = auth_session.access_token
                session["refresh_token"] = auth_session.refresh_token
            session.modified = True

            return redirect(url_for("main.index"))

        except AuthApiError as e:
            err_text = str(e).lower()
            code = getattr(e, "code", "") or ""
            # 이메일 미인증 상태 체크
            if "email_not_confirmed" in code or "email not confirmed" in err_text:
                return redirect(url_for("auth.login", error="email_not_confirmed"))
            return redirect(url_for("auth.login", error="invalid_credentials"))
        except Exception as e:
            print(f"[로그인 오류] {e}", file=sys.stderr)
            err_text = str(e).lower()
            if "email not confirmed" in err_text:
                return redirect(url_for("auth.login", error="email_not_confirmed"))
            return redirect(url_for("auth.login", error="invalid_credentials"))

    return render_template(
        "login.html",
        brand_name="VIBE-FASHION",
        error=error_msg,
        success=success_msg
    )


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    """
    [2] GET/POST /auth/signup - 회원가입 폼 및 처리
    - 가입 성공 시 /auth/signup-complete 페이지 이동
    """
    if session.get("user_id"):
        return redirect(url_for("main.index"))

    error_code = request.args.get("error")
    error_msg = AUTH_MESSAGES.get(error_code, error_code) if error_code else None

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        password_confirm = request.form.get("password_confirm") or ""

        if not name or not email or not password:
            return redirect(url_for("auth.signup", error="missing_fields"))

        if password != password_confirm:
            return redirect(url_for("auth.signup", error="password_mismatch"))

        if len(password) < 6:
            return redirect(url_for("auth.signup", error="password_length"))

        site_url = get_site_url()
        redirect_to = f"{site_url}/auth/confirm"

        try:
            supabase = get_supabase_client()
            res = supabase.auth.sign_up({
                "email": email,
                "password": password,
                "options": {
                    "data": {"full_name": name},
                    "email_redirect_to": redirect_to
                }
            })

            # 이미 존재하는 이메일이거나 확인 대기인 경우 세션에 이메일 임시 저장
            session["signup_email"] = email
            session.modified = True
            return redirect(url_for("auth.signup_complete"))

        except AuthApiError as e:
            print(f"[회원가입 AuthApiError] {e}", file=sys.stderr)
            err_code = (getattr(e, "code", "") or "").lower()
            err_msg = str(e).lower()
            if "rate_limit" in err_code or "rate limit" in err_msg:
                return redirect(url_for("auth.signup", error="rate_limit_exceeded"))
            if "already_exists" in err_code or "already registered" in err_msg:
                return redirect(url_for("auth.signup", error="user_already_exists"))
            return redirect(url_for("auth.signup", error="signup_failed"))
        except Exception as e:
            print(f"[회원가입 오류] {e}", file=sys.stderr)
            err_msg = str(e).lower()
            if "rate limit" in err_msg:
                return redirect(url_for("auth.signup", error="rate_limit_exceeded"))
            return redirect(url_for("auth.signup", error="signup_failed"))

    return render_template(
        "register.html",
        brand_name="VIBE-FASHION",
        error=error_msg
    )


@auth_bp.route("/signup-complete", methods=["GET"])
def signup_complete():
    """
    [3] GET /auth/signup-complete - '인증 메일을 보냈습니다' 안내 페이지
    """
    email = session.pop("signup_email", None) or request.args.get("email")
    return render_template(
        "signup_complete.html",
        brand_name="VIBE-FASHION",
        email=email
    )


@auth_bp.route("/confirm", methods=["GET"])
def confirm():
    """
    [4] GET /auth/confirm - 이메일 인증 링크 클릭 처리
    - verify_otp 호출 → 성공 시 Flask session 저장 → /mypage
    - token_hash & type 파라미터 또는 token & email 방식 지원
    - 해시(#access_token=...) 방식으로 리다이렉트된 경우 브라우저 렌더링 템플릿(confirm.html)으로 처리
    """
    token_hash = request.args.get("token_hash")
    otp_type = request.args.get("type", "signup")
    token = request.args.get("token")
    email = request.args.get("email")

    # Supabase가 전달하는 쿼리 파라미터가 없는 경우:
    # Supabase는 기본적으로 #access_token=...&refresh_token=... 형태의 URL 해시로 리다이렉트하므로
    # 클라이언트 자바스크립트가 해시를 파싱할 수 있도록 confirm.html 템플릿을 반환합니다.
    if not token_hash and not (token and email):
        return render_template("confirm.html", brand_name="VIBE-FASHION")

    try:
        supabase = get_supabase_client()

        if token_hash:
            # token_hash 기반 verify_otp
            response = supabase.auth.verify_otp({
                "token_hash": token_hash,
                "type": otp_type
            })
        else:
            # token + email 기반 verify_otp
            response = supabase.auth.verify_otp({
                "email": email,
                "token": token,
                "type": otp_type
            })

        user = response.user
        auth_session = response.session

        if not user:
            return redirect(url_for("auth.login", error="confirm_failed"))

        # Flask session 저장
        session["user_id"] = user.id
        full_name = (user.user_metadata or {}).get("full_name") or (user.email.split("@")[0] if user.email else "회원")
        session["user"] = {
            "id": user.id,
            "email": user.email,
            "name": full_name
        }
        if auth_session:
            session["access_token"] = auth_session.access_token
            session["refresh_token"] = auth_session.refresh_token
        session.modified = True

        # 비밀번호 복구(recovery) 타입인 경우 새 비밀번호 설정 페이지로 이동
        if otp_type == "recovery":
            return redirect(url_for("auth.reset_password"))

        # 인증 성공 시 /mypage로 이동
        return redirect(url_for("main.mypage"))

    except Exception as e:
        print(f"[이메일 인증 오류] {e}", file=sys.stderr)
        return redirect(url_for("auth.login", error="confirm_failed"))


@auth_bp.route("/session-callback", methods=["POST"])
def session_callback():
    """
    클라이언트에서 전달받은 Supabase Auth 세션 토큰으로 Flask session을 확립하는 API
    """
    data = request.get_json(silent=True) or {}
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    otp_type = data.get("type", "signup")

    if not access_token:
        return {"success": False, "error": "missing_token"}, 400

    try:
        supabase = get_supabase_client()
        user_res = supabase.auth.get_user(access_token)
        user = user_res.user if user_res else None

        if not user:
            return {"success": False, "error": "invalid_user"}, 401

        session["user_id"] = user.id
        full_name = (user.user_metadata or {}).get("full_name") or (user.email.split("@")[0] if user.email else "회원")
        session["user"] = {
            "id": user.id,
            "email": user.email,
            "name": full_name
        }
        session["access_token"] = access_token
        if refresh_token:
            session["refresh_token"] = refresh_token
        session.modified = True

        # recovery 타입이면 비밀번호 재설정 페이지로 리다이렉트 URL 반환
        redirect_target = url_for("auth.reset_password") if otp_type == "recovery" else url_for("main.mypage")
        return {"success": True, "redirect_url": redirect_target}
    except Exception as e:
        print(f"[세션 콜백 오류] {e}", file=sys.stderr)
        return {"success": False, "error": str(e)}, 500


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """
    [5] GET/POST /auth/forgot-password - 비밀번호 재설정 메일 발송
    """
    error_code = request.args.get("error")
    success_code = request.args.get("success")
    error_msg = AUTH_MESSAGES.get(error_code, error_code) if error_code else None
    success_msg = AUTH_MESSAGES.get(success_code, success_code) if success_code else None

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()

        if not email:
            return redirect(url_for("auth.forgot_password", error="missing_fields"))

        site_url = get_site_url()
        # Supabase recovery 링크 클릭 시 /auth/confirm?type=recovery 또는 /auth/reset-password로 리다이렉트
        redirect_to = f"{site_url}/auth/confirm"

        try:
            supabase = get_supabase_client()
            supabase.auth.reset_password_for_email(
                email=email,
                options={"redirect_to": redirect_to}
            )
            return redirect(url_for("auth.forgot_password", success="reset_mail_sent"))
        except Exception as e:
            print(f"[비밀번호 재설정 메일 오류] {e}", file=sys.stderr)
            err_msg = str(e).lower()
            if "rate limit" in err_msg:
                return redirect(url_for("auth.forgot_password", error="rate_limit_exceeded"))
            return redirect(url_for("auth.forgot_password", error="reset_request_failed"))

    return render_template(
        "forgot_password.html",
        brand_name="VIBE-FASHION",
        error=error_msg,
        success=success_msg
    )


@auth_bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    """
    [6] GET/POST /auth/reset-password - 새 비밀번호 설정
    - 인증된 세션(또는 토큰)을 가진 상태에서 새 비밀번호를 입력받아 변경합니다.
    """
    error_code = request.args.get("error")
    success_code = request.args.get("success")
    error_msg = AUTH_MESSAGES.get(error_code, error_code) if error_code else None
    success_msg = AUTH_MESSAGES.get(success_code, success_code) if success_code else None

    # recovery 링크에서 query param으로 token_hash가 넘어온 경우 세션 확립 시도
    token_hash = request.args.get("token_hash")
    if token_hash:
        try:
            supabase = get_supabase_client()
            resp = supabase.auth.verify_otp({
                "token_hash": token_hash,
                "type": "recovery"
            })
            if resp.user:
                session["user_id"] = resp.user.id
                full_name = (resp.user.user_metadata or {}).get("full_name") or resp.user.email.split("@")[0]
                session["user"] = {
                    "id": resp.user.id,
                    "email": resp.user.email,
                    "name": full_name
                }
                if resp.session:
                    session["access_token"] = resp.session.access_token
                    session["refresh_token"] = resp.session.refresh_token
                session.modified = True
        except Exception as e:
            print(f"[비밀번호 재설정 토큰 검증 오류] {e}", file=sys.stderr)

    if request.method == "POST":
        password = request.form.get("password") or ""
        password_confirm = request.form.get("password_confirm") or ""
        form_access_token = request.form.get("access_token")
        form_refresh_token = request.form.get("refresh_token")

        if not password or not password_confirm:
            return redirect(url_for("auth.reset_password", error="missing_fields"))

        if password != password_confirm:
            return redirect(url_for("auth.reset_password", error="password_mismatch"))

        if len(password) < 6:
            return redirect(url_for("auth.reset_password", error="password_length"))

        access_token = form_access_token or session.get("access_token")
        refresh_token = form_refresh_token or session.get("refresh_token")

        if not access_token:
            return redirect(url_for("auth.login", error="login_required"))

        try:
            supabase = get_supabase_client()
            # 세션 설정 후 비밀번호 업데이트 (refresh_token이 없으면 빈 문자열 또는 access_token 기반)
            if refresh_token:
                try:
                    supabase.auth.set_session(access_token, refresh_token)
                except Exception:
                    pass
            # update_user 호출
            supabase.auth.update_user({"password": password})

            # 비밀번호 변경 후 보안상 세션 초기화하고 로그인 유도
            session.clear()
            session.modified = True

            return redirect(url_for("auth.login", success="password_reset_success"))

        except Exception as e:
            print(f"[비밀번호 변경 처리 오류] {e}", file=sys.stderr)
            return redirect(url_for("auth.reset_password", error="reset_failed"))

    return render_template(
        "reset_password.html",
        brand_name="VIBE-FASHION",
        error=error_msg,
        success=success_msg
    )


@auth_bp.route("/logout")
def logout():
    """로그아웃 처리"""
    session.clear()
    session.modified = True
    return redirect(url_for("auth.login", success="logout_success"))


@auth_bp.route("/withdraw", methods=["POST"])
@login_required
def withdraw():
    """
    회원 탈퇴 처리
    - 로그인된 사용자의 소셜 로그인 연동 해제(네이버 등)
    - DB 내 장바구니, 위시리스트, 알림, 프로필 및 Supabase Auth 계정을 영구 삭제합니다.
    """
    user_id = session.get("user_id")
    naver_token = session.get("naver_access_token")

    # 1. 네이버 소셜 로그인 연동 해제 처리
    if naver_token:
        naver_client_id = os.getenv("NAVER_CLIENT_ID")
        naver_client_secret = os.getenv("NAVER_CLIENT_SECRET")
        if naver_client_id and naver_client_secret:
            try:
                unlink_url = (
                    f"https://nid.naver.com/oauth2.0/token"
                    f"?grant_type=delete&client_id={naver_client_id}&client_secret={naver_client_secret}&access_token={naver_token}&service_provider=NAVER"
                )
                req = urllib.request.Request(unlink_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req) as resp:
                    print(f"[네이버 연동 해제 성공] {resp.read().decode()}", file=sys.stderr)
            except Exception as unlink_err:
                print(f"[네이버 연동 해제 호출 실패] {unlink_err}", file=sys.stderr)

    try:
        admin_client = get_supabase_admin_client()

        # 2. DB 테이블 잔여 데이터 명시적 삭제 (장바구니, 리뷰, 알림, 프로필 등)
        try:
            admin_client.table("carts").delete().eq("user_id", user_id).execute()
        except Exception:
            pass
        try:
            admin_client.table("reviews").delete().eq("user_id", user_id).execute()
        except Exception:
            pass
        try:
            admin_client.table("notifications").delete().eq("user_id", user_id).execute()
        except Exception:
            pass
        try:
            admin_client.table("profiles").delete().eq("id", user_id).execute()
        except Exception:
            pass

        # 3. Supabase Auth 사용자 영구 삭제
        admin_client.auth.admin.delete_user(user_id)

        # 4. 세션 및 쿠키 데이터 완전 파기
        session.clear()
        session.modified = True
        return redirect(url_for("auth.login", success="account_deleted"))
    except Exception as e:
        print(f"[회원 탈퇴 오류] {e}", file=sys.stderr)
        return redirect(url_for("main.mypage", error="withdraw_failed"))


@auth_bp.route("/callback", methods=["GET"])
def auth_callback():
    """
    OAuth 소셜 로그인 (Microsoft/Azure, Kakao 등) 및 인증 콜백 처리
    - code (PKCE) 파라미터가 있는 경우 exchange_code_for_session 수행
    - token_hash 파라미터가 있는 경우 verify_otp 수행
    - 브라우저 해시(#access_token=...) 방식으로 리다이렉트된 경우 confirm.html 템플릿 반환
    """
    code = request.args.get("code")
    token_hash = request.args.get("token_hash")
    otp_type = request.args.get("type", "signup")
    error = request.args.get("error")
    error_description = request.args.get("error_description")

    if error:
        print(f"[OAuth Callback Error] {error}: {error_description}", file=sys.stderr)
        return redirect(url_for("auth.login", error="oauth_failed"))

    site_url = get_site_url()
    redirect_to = f"{site_url}/auth/callback"

    try:
        supabase = get_supabase_client()

        # 1. code 기반 세션 교환 (PKCE Auth Code)
        if code:
            code_verifier = session.pop("code_verifier", None)
            exchange_params = {
                "auth_code": code,
                "code_verifier": code_verifier or "",
                "redirect_to": redirect_to
            }
            auth_response = supabase.auth.exchange_code_for_session(exchange_params)
            user = auth_response.user
            auth_session = auth_response.session

            if user:
                session["user_id"] = user.id
                full_name = (
                    (user.user_metadata or {}).get("full_name")
                    or (user.user_metadata or {}).get("name")
                    or (user.user_metadata or {}).get("user_name")
                    or (user.email.split("@")[0] if user.email else "회원")
                )
                session["user"] = {
                    "id": user.id,
                    "email": user.email,
                    "name": full_name
                }
                if auth_session:
                    session["access_token"] = auth_session.access_token
                    session["refresh_token"] = auth_session.refresh_token
                session.modified = True
                return redirect(url_for("main.mypage"))

        # 2. token_hash 기반 이메일 OTP 검증
        if token_hash:
            resp = supabase.auth.verify_otp({
                "token_hash": token_hash,
                "type": otp_type
            })
            if resp.user:
                session["user_id"] = resp.user.id
                full_name = (resp.user.user_metadata or {}).get("full_name") or resp.user.email.split("@")[0]
                session["user"] = {
                    "id": resp.user.id,
                    "email": resp.user.email,
                    "name": full_name
                }
                if resp.session:
                    session["access_token"] = resp.session.access_token
                    session["refresh_token"] = resp.session.refresh_token
                session.modified = True
                if otp_type == "recovery":
                    return redirect(url_for("auth.reset_password"))
                return redirect(url_for("main.mypage"))

        # 3. 쿼리 파라미터가 없으면 클라이언트 해시(#access_token=...) 처리를 위해 confirm.html 렌더링
        return render_template("confirm.html", brand_name="VIBE-FASHION")

    except Exception as e:
        print(f"[콜백 처리 오류] {e}", file=sys.stderr)
        # 해시 방식으로 넘어왔을 가능성이 있으므로 confirm.html fallback 시도
        return render_template("confirm.html", brand_name="VIBE-FASHION")


@auth_bp.route("/microsoft", methods=["GET"])
@auth_bp.route("/azure", methods=["GET"])
def microsoft_login():
    """
    Microsoft (Azure) 소셜 로그인 진입점
    """
    site_url = get_site_url()
    redirect_to = f"{site_url}/auth/callback"

    try:
        supabase = get_supabase_client()
        res = supabase.auth.sign_in_with_oauth({
            "provider": "azure",
            "options": {
                "redirect_to": redirect_to
            }
        })
        # PKCE code_verifier가 저장소에 있다면 세션에 보존
        code_verifier = supabase.auth._storage.get_item(f"{supabase.auth._storage_key}-code-verifier")
        if code_verifier:
            session["code_verifier"] = code_verifier
            session.modified = True

        if res and res.url:
            return redirect(res.url)
        return redirect(url_for("auth.login", error="oauth_failed"))
    except Exception as e:
        print(f"[Microsoft 로그인 오류] {e}", file=sys.stderr)
        return redirect(url_for("auth.login", error="oauth_failed"))


@auth_bp.route("/kakao", methods=["GET"])
@auth_bp.route("/login/kakao", methods=["GET"])
def kakao_login():
    """
    카카오톡 OAuth 소셜 로그인 진입점 (GET /auth/kakao)
    - supabase.auth.sign_in_with_oauth(provider='kakao') 호출
    - redirect_to는 환경변수 SITE_URL + '/auth/callback' 사용
    - prompt='login' 옵션으로 자동 로그인(Silent SSO) 방지 및 계정 선택 유도
    """
    site_url = get_site_url()
    redirect_to = f"{site_url}/auth/callback"

    try:
        supabase = get_supabase_client()
        res = supabase.auth.sign_in_with_oauth({
            "provider": "kakao",
            "options": {
                "redirect_to": redirect_to,
                "query_params": {
                    "prompt": "login"
                }
            }
        })
        # PKCE code_verifier 보존
        code_verifier = supabase.auth._storage.get_item(f"{supabase.auth._storage_key}-code-verifier")
        if code_verifier:
            session["code_verifier"] = code_verifier
            session.modified = True

        if res and res.url:
            return redirect(res.url)
        return redirect(url_for("auth.login", error="oauth_failed"))
    except Exception as e:
        print(f"[카카오 로그인 오류] {e}", file=sys.stderr)
        return redirect(url_for("auth.login", error="oauth_failed"))


@auth_bp.route("/google", methods=["GET"])
@auth_bp.route("/login/google", methods=["GET"])
def google_login():
    """
    구글(Google) OAuth 소셜 로그인 진입점 (GET /auth/google)
    - Supabase Auth provider='google' 활용
    - redirect_to: SITE_URL + '/auth/callback'
    - prompt='select_account' 옵션으로 항상 계정 선택 창 표시
    """
    site_url = get_site_url()
    redirect_to = f"{site_url}/auth/callback"

    try:
        supabase = get_supabase_client()
        res = supabase.auth.sign_in_with_oauth({
            "provider": "google",
            "options": {
                "redirect_to": redirect_to,
                "query_params": {
                    "prompt": "select_account"
                }
            }
        })
        code_verifier = supabase.auth._storage.get_item(f"{supabase.auth._storage_key}-code-verifier")
        if code_verifier:
            session["code_verifier"] = code_verifier
            session.modified = True

        if res and res.url:
            return redirect(res.url)
        return redirect(url_for("auth.login", error="oauth_failed"))
    except Exception as e:
        print(f"[Google 로그인 오류] {e}", file=sys.stderr)
        return redirect(url_for("auth.login", error="oauth_failed"))


@auth_bp.route("/naver", methods=["GET"])
@auth_bp.route("/login/naver", methods=["GET"])
def naver_login():
    """
    네이버(Naver) OAuth 소셜 로그인 진입점 (GET /auth/naver)
    - 네이버 개발자 센터 애플리케이션의 Client ID를 통해 네이버 로그인 인증 페이지로 이동
    - auth_type='reprompt' 옵션으로 동의/계정 재확인 창 표시
    """
    load_dotenv()
    naver_client_id = os.getenv("NAVER_CLIENT_ID")
    if not naver_client_id:
        print("[네이버 로그인 알림] NAVER_CLIENT_ID 환경변수가 설정되지 않았습니다.", file=sys.stderr)
        return redirect(url_for("auth.login", error="oauth_failed"))

    site_url = get_site_url()
    redirect_uri = f"{site_url}/auth/callback/naver"
    state = secrets.token_hex(16)
    session["naver_oauth_state"] = state
    session.modified = True

    encoded_redirect = urllib.parse.quote(redirect_uri, safe="")
    naver_auth_url = (
        f"https://nid.naver.com/oauth2.0/authorize"
        f"?response_type=code&client_id={naver_client_id}&redirect_uri={encoded_redirect}&state={state}&auth_type=reprompt"
    )
    return redirect(naver_auth_url)


@auth_bp.route("/callback/naver", methods=["GET"])
def naver_callback():
    """
    네이버 OAuth 콜백 처리 (GET /auth/callback/naver)
    - 전달받은 인가 코드(code)로 네이버 토큰 및 프로필을 조회하고 Supabase 계정 연동 및 Flask 세션 확립
    """
    load_dotenv()
    code = request.args.get("code")
    state = request.args.get("state")
    error = request.args.get("error")
    error_description = request.args.get("error_description")

    if error:
        print(f"[네이버 로그인 오류] {error}: {error_description}", file=sys.stderr)
        return redirect(url_for("auth.login", error="oauth_failed"))

    saved_state = session.pop("naver_oauth_state", None)
    if not code:
        print("[네이버 로그인 오류] 인가 코드(code)가 없습니다.", file=sys.stderr)
        return redirect(url_for("auth.login", error="oauth_failed"))

    if saved_state and state != saved_state:
        print(f"[네이버 로그인 오류] state 불일치: req={state}, saved={saved_state}", file=sys.stderr)

    naver_client_id = os.getenv("NAVER_CLIENT_ID")
    naver_client_secret = os.getenv("NAVER_CLIENT_SECRET")

    if not naver_client_id or not naver_client_secret:
        print("[네이버 로그인 오류] NAVER_CLIENT_ID 또는 NAVER_CLIENT_SECRET이 없습니다.", file=sys.stderr)
        return redirect(url_for("auth.login", error="oauth_failed"))

    try:
        # 1. 네이버 토큰 요청
        token_url = (
            f"https://nid.naver.com/oauth2.0/token"
            f"?grant_type=authorization_code&client_id={naver_client_id}&client_secret={naver_client_secret}&code={code}&state={state}"
        )
        req = urllib.request.Request(
            token_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        with urllib.request.urlopen(req) as resp:
            token_data = json.loads(resp.read().decode())
        
        access_token = token_data.get("access_token")
        if not access_token:
            print(f"[네이버 토큰 요청 실패] {token_data}", file=sys.stderr)
            return redirect(url_for("auth.login", error="oauth_failed"))

        # 2. 네이버 사용자 프로필 조회
        profile_req = urllib.request.Request(
            "https://openapi.naver.com/v1/nid/me",
            headers={
                "Authorization": f"Bearer {access_token}",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            }
        )
        with urllib.request.urlopen(profile_req) as resp:
            profile_res = json.loads(resp.read().decode())

        naver_account = profile_res.get("response", {})
        email = naver_account.get("email") or f"{naver_account.get('id')}@naver.user"
        nickname = naver_account.get("nickname") or naver_account.get("name") or "네이버회원"

        # 3. Supabase Admin 또는 세션을 통한 계정 연동
        admin_client = get_supabase_admin_client()
        existing_users = admin_client.auth.admin.list_users()
        matched = [u for u in existing_users if (u.email or "").lower() == email.lower()]

        if matched:
            user = matched[0]
        else:
            # 신규 가입 생성
            temp_pwd = secrets.token_urlsafe(24) + "Aa1!"
            new_u = admin_client.auth.admin.create_user({
                "email": email,
                "password": temp_pwd,
                "email_confirm": True,
                "user_metadata": {"full_name": nickname, "provider": "naver"}
            })
            user = new_u.user

        # 4. Flask 세션 확립
        session["user_id"] = user.id
        session["user"] = {
            "id": user.id,
            "email": email,
            "name": nickname
        }
        session["provider"] = "naver"
        session["naver_access_token"] = access_token
        session.modified = True

        return redirect(url_for("main.mypage"))
    except Exception as e:
        print(f"[네이버 콜백 오류] {e}", file=sys.stderr)
        return redirect(url_for("auth.login", error="oauth_failed"))
