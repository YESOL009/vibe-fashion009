"""
데이터베이스 및 공통 유틸리티 모듈 (utils/db.py)
- Supabase 클라이언트 팩토리
- UUID 유효성 검사 및 날짜 파싱 유틸리티
- 상품 이미지 및 가격 매핑 상수
"""

import os
import sys
import uuid
import datetime
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or SUPABASE_ANON_KEY

# 특정 상품 로컬 대표 이미지 매핑
LOCAL_IMAGE_MAP = {
    "베이직 크롭 티셔츠": "/static/images/crop_tee.png",
    "와이드 데님 팬츠": "/static/images/denim_pants.png",
    "오버핏 코튼 자켓": "/static/images/cotton_jacket.png",
    "플로럴 미디 원피스": "/static/images/floral_dress.png",
}

# 기본 정상가(원가) 매핑
DEFAULT_ORIGINAL_PRICES = {
    "베이직 크롭 티셔츠": 29900,
    "와이드 데님 팬츠": 49900,
    "오버핏 코튼 자켓": 89000,
    "플로럴 미디 원피스": 59900,
    "청키 스트릿 스니커즈": 89000,
    "빈티지 워싱 볼캡": 35000,
}


def get_supabase_client() -> Client:
    """Supabase 익명(anon) 클라이언트 인스턴스 반환"""
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise RuntimeError("SUPABASE_URL 또는 SUPABASE_ANON_KEY 환경 변수가 설정되지 않았습니다.")
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


def get_admin_client() -> Client | None:
    """Supabase 관리자(service_role) 클라이언트 인스턴스 반환 (RLS 우회 및 관리자용)"""
    if SUPABASE_URL and SUPABASE_SERVICE_KEY:
        try:
            return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        except Exception as e:
            print(f"[Supabase Admin 클라이언트 생성 오류] {e}", file=sys.stderr)
    return None


# 하위 호환성을 위한 alias
get_admin_supabase_client = get_admin_client
get_anon_supabase_client = get_supabase_client


def is_valid_uuid(val: any) -> bool:
    """UUID 문자열 형식 유효성 확인 헬퍼"""
    if not val:
        return False
    try:
        uuid.UUID(str(val))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def parse_datetime(dt_str: str) -> datetime.datetime | None:
    """
    다양한 형식의 ISO 8601 및 날짜 문자열을 datetime 객체로 안전하게 파싱
    """
    if not dt_str:
        return None
    try:
        clean_str = str(dt_str).replace("Z", "+00:00")
        if "+" in clean_str:
            base, tz = clean_str.split("+", 1)
            if "." in base:
                base = base[:26]
            clean_str = f"{base}+{tz}"
        return datetime.datetime.fromisoformat(clean_str)
    except Exception:
        try:
            return datetime.datetime.strptime(str(dt_str)[:19], "%Y-%m-%dT%H:%M:%S")
        except Exception:
            try:
                return datetime.datetime.strptime(str(dt_str)[:19], "%Y-%m-%d %H:%M:%S")
            except Exception:
                return None


def get_product_thumbnail(name: str, product_id: str = None, images: list = None) -> str:
    """
    상품명 또는 product_images로부터 대표 썸네일 URL 반환 (fallback 처리 포함)
    """
    # 1. 로컬 정적 이미지 매핑 확인
    if name and name in LOCAL_IMAGE_MAP:
        return LOCAL_IMAGE_MAP[name]

    # 2. product_images 리스트에서 썸네일 검색
    if images:
        for img in sorted(images, key=lambda x: x.get("sort_order", 0)):
            if img.get("is_thumbnail"):
                return img.get("image_url")
        if images:
            return images[0].get("image_url")

    # 3. 기본 placeholder
    pid = product_id or "item"
    return f"https://picsum.photos/seed/vibe_{pid}/600/750"
