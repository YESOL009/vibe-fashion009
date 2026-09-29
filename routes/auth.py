"""
인증 라우트 모듈 참조 (app/routes/auth.py 연계)
"""

from app.routes.auth import auth_bp, login_required

__all__ = ["auth_bp", "login_required"]
