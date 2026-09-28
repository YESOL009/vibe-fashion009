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
    # routes/main.py에 정의된 main_bp를 가져와서 앱에 연결합니다.
    from routes.main import main_bp
    app.register_blueprint(main_bp)

    return app
