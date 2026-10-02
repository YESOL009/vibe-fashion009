"""
VIBE-FASHION 웹 애플리케이션 팩토리 모듈
- Flask의 '애플리케이션 팩토리 패턴(Application Factory Pattern)'을 적용하여
  앱 인스턴스를 함수 안에서 생성하고 설정합니다.
"""

import os
from flask import Flask
from dotenv import load_dotenv

# .env 파일이 존재하면 환경 변수를 로드합니다.
load_dotenv()


def create_app(test_config=None):
    """
    Flask 애플리케이션 객체를 생성하고 설정하여 반환하는 팩토리 함수입니다.
    
    매개변수:
        test_config: 테스트 시 사용할 커스텀 설정 딕셔너리 (기본값: None)
    
    반환값:
        Flask 앱 인스턴스
    """
    # templates와 static 폴더 경로를 명시적으로 지정하여 앱 인스턴스를 생성합니다.
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static"
    )

    # 기본 환경 설정
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY", "default-dev-secret-key-1234"),
    )

    # 테스트 설정이 있다면 덮어씌웁니다.
    if test_config is not None:
        app.config.update(test_config)

    # 블루프린트(라우트 모듈) 등록
    # routes/main.py에 정의된 main_bp와 app/routes/auth.py에 정의된 auth_bp를 가져와서 앱에 연결합니다.
    from routes.main import main_bp
    from app.routes.auth import auth_bp
    from routes.admin_routes import manage_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(manage_bp)

    # 기존 /admin/* 경로로의 접근 원천 차단 (403 Forbidden)
    from flask import abort

    @app.route("/admin", defaults={"subpath": ""})
    @app.route("/admin/<path:subpath>")
    def blocked_legacy_admin(subpath):
        abort(403, description="login_required_for_admin")

    # 403 Forbidden 에러 핸들러 (비관리자 및 주소창 직접 입력 접근 시 403 페이지 표시)
    from flask import render_template

    @app.errorhandler(403)
    def forbidden_error(error):
        error_desc = getattr(error, "description", None)
        return render_template("403.html", brand_name="VIBE-FASHION", error_reason=error_desc), 403

    # 컨텍스트 프로세서: 모든 템플릿에서 is_admin 변수 사용 가능하도록 등록
    from routes.admin_auth import is_admin_user
    from flask import session

    @app.context_processor
    def inject_admin_status():
        user_id = session.get("user_id")
        is_admin = False
        if user_id:
            if session.get("role") == "admin":
                is_admin = True
            else:
                is_admin = is_admin_user(user_id)
        return dict(is_admin=is_admin)

    return app
