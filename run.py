"""
VIBE-FASHION 애플리케이션 실행 진입점 (Entry Point)
- app 모듈의 create_app 팩토리 함수를 호출하여 앱을 구동합니다.
"""

from app import create_app

# 애플리케이션 팩토리 패턴을 통해 Flask 앱 인스턴스 생성
app = create_app()

if __name__ == "__main__":
    # 개발 서버 실행 (기본 포트 5050 - 충돌 방지)
    print("=" * 60)
    print(" [VIBE-FASHION] 쇼핑몰 웹 서버를 시작합니다.")
    print(" 접속 주소: http://127.0.0.1:5050")
    print("=" * 60)
    app.run(host="127.0.0.1", port=5050, debug=True)
