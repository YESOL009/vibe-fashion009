"""
메인 라우트 블루프린트 모듈
- 쇼핑몰 메인 페이지 및 상품 목록/상세 화면을 처리합니다.
"""

import os
import sys
import traceback
from flask import Blueprint, render_template, session, jsonify, request, redirect, url_for
from dotenv import load_dotenv
from supabase import create_client, Client

# .env 파일에서 환경변수 로드
load_dotenv()

# Supabase 클라이언트 초기화
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

supabase: Client | None = None
if SUPABASE_URL and SUPABASE_ANON_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    except Exception as e:
        print(f"[Supabase 초기화 오류] {e}", file=sys.stderr)
        traceback.print_exc()

# 'main'이라는 이름의 블루프린트를 생성합니다.
main_bp = Blueprint("main", __name__)

# 특정 상품 정적 이미지 우선 매핑
LOCAL_IMAGE_MAP = {
    "베이직 크롭 티셔츠": "/static/images/crop_tee.png",
    "와이드 데님 팬츠": "/static/images/denim_pants.png",
    "오버핏 코튼 자켓": "/static/images/cotton_jacket.png",
}


def get_featured_products(limit: int = 4):
    """
    Supabase products 테이블에서 is_active=true이고 is_featured=true인 상품을 조회합니다.
    - 실패 시 빈 리스트를 반환하며 터미널에 에러 로그를 출력합니다.
    - 가격 포맷팅({:,}원) 및 thumbnail_url 처리를 수행합니다.
    """
    if not supabase:
        print("[Supabase 오류] SUPABASE_URL 또는 SUPABASE_ANON_KEY 설정이 올바르지 않습니다.", file=sys.stderr)
        return []

    try:
        # 1차 시도: is_active=true 및 is_featured=true 조건으로 최대 4개 조회
        try:
            query = (
                supabase.table("products")
                .select("*, categories(name, slug), product_images(*)")
                .eq("is_active", True)
                .eq("is_featured", True)
                .limit(limit)
            )
            response = query.execute()
            data = response.data or []
        except Exception as filter_err:
            # DB 컬럼에 is_featured가 없을 경우 콘솔에 알림 후 is_active=True로 안전 대체
            err_msg = str(filter_err)
            if "is_featured" in err_msg:
                print("[Supabase 알림] products 테이블에 is_featured 컬럼이 없어 is_active=true 상품을 조회합니다.", file=sys.stderr)
                query = (
                    supabase.table("products")
                    .select("*, categories(name, slug), product_images(*)")
                    .eq("is_active", True)
                    .limit(limit)
                )
                response = query.execute()
                data = response.data or []
            else:
                raise filter_err

        seen_names = set()
        formatted_products = []
        for item in data:
            name = item.get("name")
            if name in seen_names:
                continue
            seen_names.add(name)

            # 1. 가격 포맷팅 ({:,}원)
            raw_price = item.get("price") or 0
            price_int = int(raw_price)
            price_formatted = f"{price_int:,}원"

            # 2. thumbnail_url 추출 (로컬 매핑 우선 -> product_images 테이블 연동 -> 기본 placeholder)
            thumbnail_url = LOCAL_IMAGE_MAP.get(name) or item.get("thumbnail_url")
            if not thumbnail_url:
                images = item.get("product_images") or []
                # is_thumbnail=True인 이미지를 우선 탐색
                for img in sorted(images, key=lambda x: x.get("sort_order", 0)):
                    if img.get("is_thumbnail"):
                        thumbnail_url = img.get("image_url")
                        break
                # is_thumbnail이 없으면 첫 번째 이미지 사용
                if not thumbnail_url and images:
                    thumbnail_url = images[0].get("image_url")

            # fallback 썸네일
            if not thumbnail_url:
                thumbnail_url = f"https://picsum.photos/seed/vibe_{item.get('id', 'item')}/600/750"

            # 3. 카테고리명 정리
            category_data = item.get("categories")
            if isinstance(category_data, dict):
                category_name = category_data.get("name") or "FASHION"
            else:
                category_name = "FASHION"

            formatted_products.append({
                "id": item.get("id"),
                "name": item.get("name"),
                "category": category_name,
                "price": price_int,
                "price_formatted": price_formatted,
                "thumbnail_url": thumbnail_url,
                "image": thumbnail_url,  # 템플릿 호환성
                "description": item.get("description") or "",
                "badge": item.get("badge") or "NEW",
                "badge_class": item.get("badge_class") or "bg-dark",
                "rating": item.get("rating_avg") or 5.0,
            })

        return formatted_products

    except Exception as e:
        print(f"[Supabase 상품 조회 실패] {e}", file=sys.stderr)
        traceback.print_exc()
        return []


@main_bp.route("/")
def index():
    """
    쇼핑몰 메인 페이지 라우트
    - Supabase products 테이블의 추천 상품 목록을 템플릿에 전달하여 렌더링합니다.
    """
    products = get_featured_products(limit=12)

    return render_template(
        "index.html",
        brand_name="VIBE-FASHION",
        products=products
    )


@main_bp.route("/product/<product_id>")
def product_detail(product_id):
    """
    상품 상세 페이지 라우트 (단일 상품 보기)
    """
    product = None
    if supabase:
        try:
            res = (
                supabase.table("products")
                .select("*, categories(name, slug), product_images(*)")
                .eq("id", product_id)
                .single()
                .execute()
            )
            item = res.data
            if item:
                prod_name = item.get("name")
                images = item.get("product_images") or []
                thumbnail_url = LOCAL_IMAGE_MAP.get(prod_name) or item.get("thumbnail_url")
                if not thumbnail_url and images:
                    thumbnail_url = images[0].get("image_url")
                if not thumbnail_url:
                    thumbnail_url = f"https://picsum.photos/seed/vibe_{product_id}/600/750"

                raw_price = item.get("price") or 0
                price_int = int(raw_price)

                category_data = item.get("categories")
                category_name = category_data.get("name") if isinstance(category_data, dict) else "FASHION"

                product = {
                    "id": item.get("id"),
                    "name": prod_name,
                    "category": category_name,
                    "price": price_int,
                    "price_formatted": f"{price_int:,}원",
                    "thumbnail_url": thumbnail_url,
                    "image": thumbnail_url,
                    "description": item.get("description") or "",
                    "badge": item.get("badge") or "HOT",
                    "badge_class": item.get("badge_class") or "bg-primary",
                    "rating": item.get("rating_avg") or 5.0,
                }
        except Exception as e:
            print(f"[Supabase 상품 상세 조회 실패] {e}", file=sys.stderr)
            traceback.print_exc()

    return render_template(
        "detail.html",
        brand_name="VIBE-FASHION",
        product=product
    )


def _get_cart():
    """세션에 저장된 장바구니 딕셔너리 반환 (key: product_id)"""
    return session.setdefault("cart", {})


def _get_wishlist():
    """세션에 저장된 관심 상품 세트(리스트) 반환"""
    return session.setdefault("wishlist", [])


@main_bp.route("/cart")
def cart_page():
    """
    장바구니 페이지 라우트
    - 세션에 저장된 장바구니 품목을 바탕으로 합계 계산 및 렌더링
    """
    cart = _get_cart()
    items = []
    total_price = 0

    for pid, info in cart.items():
        qty = int(info.get("quantity", 1))
        price = int(info.get("price", 0))
        item_total = price * qty
        total_price += item_total

        items.append({
            "id": pid,
            "name": info.get("name"),
            "price": price,
            "price_formatted": f"{price:,}원",
            "quantity": qty,
            "subtotal": item_total,
            "subtotal_formatted": f"{item_total:,}원",
            "thumbnail_url": info.get("thumbnail_url"),
            "option": info.get("option", "기본 옵션")
        })

    shipping_fee = 0 if (total_price >= 30000 or total_price == 0) else 3000
    final_total = total_price + shipping_fee

    return render_template(
        "cart.html",
        brand_name="VIBE-FASHION",
        items=items,
        total_price=total_price,
        total_price_formatted=f"{total_price:,}원",
        shipping_fee=shipping_fee,
        shipping_fee_formatted=f"{shipping_fee:,}원" if shipping_fee > 0 else "무료배송",
        final_total=final_total,
        final_total_formatted=f"{final_total:,}원",
        cart_count=sum(item["quantity"] for item in items)
    )


@main_bp.route("/wishlist")
def wishlist_page():
    """
    관심 상품(위시리스트) 페이지 라우트
    """
    wishlist = _get_wishlist()
    return render_template(
        "wishlist.html",
        brand_name="VIBE-FASHION",
        items=wishlist,
        wishlist_count=len(wishlist)
    )


@main_bp.route("/api/cart/add", methods=["POST"])
def api_cart_add():
    """
    장바구니 추가 API
    """
    data = request.get_json(silent=True) or request.form.to_dict()
    product_id = str(data.get("product_id") or "")
    product_name = data.get("name") or "상품"
    raw_price = data.get("price") or 0
    thumbnail_url = data.get("thumbnail_url") or ""
    option = data.get("option") or "FREE"
    quantity = int(data.get("quantity", 1))

    # product_id가 없으면 상품명 기반 키 생성
    key = product_id if product_id else product_name

    cart = _get_cart()
    if key in cart:
        cart[key]["quantity"] += quantity
    else:
        try:
            price_val = int(str(raw_price).replace(",", "").replace("원", "").strip())
        except ValueError:
            price_val = 0

        cart[key] = {
            "id": product_id,
            "name": product_name,
            "price": price_val,
            "thumbnail_url": thumbnail_url,
            "option": option,
            "quantity": quantity
        }

    session.modified = True
    total_qty = sum(item.get("quantity", 1) for item in cart.values())

    return jsonify({
        "success": True,
        "message": f"[{product_name}] 상품이 장바구니에 담겼습니다.",
        "cart_count": total_qty
    })


@main_bp.route("/api/cart/update", methods=["POST"])
def api_cart_update():
    """
    장바구니 수량 변경 API
    """
    data = request.get_json(silent=True) or {}
    key = str(data.get("id") or "")
    action = data.get("action")  # 'increase', 'decrease', 'set'
    qty = data.get("quantity")

    cart = _get_cart()
    if key in cart:
        if action == "increase":
            cart[key]["quantity"] += 1
        elif action == "decrease":
            if cart[key]["quantity"] > 1:
                cart[key]["quantity"] -= 1
            else:
                del cart[key]
        elif action == "set" and qty is not None:
            new_qty = int(qty)
            if new_qty > 0:
                cart[key]["quantity"] = new_qty
            else:
                del cart[key]

        session.modified = True

    total_qty = sum(item.get("quantity", 1) for item in cart.values())
    return jsonify({"success": True, "cart_count": total_qty})


@main_bp.route("/api/cart/remove", methods=["POST"])
def api_cart_remove():
    """
    장바구니 항목 삭제 API
    """
    data = request.get_json(silent=True) or {}
    key = str(data.get("id") or "")
    cart = _get_cart()
    if key in cart:
        del cart[key]
        session.modified = True

    total_qty = sum(item.get("quantity", 1) for item in cart.values())
    return jsonify({"success": True, "cart_count": total_qty})


@main_bp.route("/api/cart/clear", methods=["POST"])
def api_cart_clear():
    """
    장바구니 전체 비우기 API
    """
    session["cart"] = {}
    session.modified = True
    return jsonify({"success": True, "cart_count": 0})


@main_bp.route("/api/wishlist/toggle", methods=["POST"])
def api_wishlist_toggle():
    """
    관심 상품 토글 API (추가/삭제)
    """
    data = request.get_json(silent=True) or {}
    product_id = str(data.get("product_id") or "")
    product_name = data.get("name") or "상품"
    raw_price = data.get("price") or 0
    thumbnail_url = data.get("thumbnail_url") or ""

    try:
        price_val = int(str(raw_price).replace(",", "").replace("원", "").strip())
    except ValueError:
        price_val = 0

    wishlist = _get_wishlist()
    # 이미 존재하는지 검사
    existing_idx = next((i for i, item in enumerate(wishlist) if item.get("id") == product_id or item.get("name") == product_name), None)

    if existing_idx is not None:
        wishlist.pop(existing_idx)
        is_active = False
        message = f"[{product_name}] 관심 상품에서 해제되었습니다."
    else:
        wishlist.append({
            "id": product_id,
            "name": product_name,
            "price": price_val,
            "price_formatted": f"{price_val:,}원",
            "thumbnail_url": thumbnail_url
        })
        is_active = True
        message = f"[{product_name}] 관심 상품에 등록되었습니다."

    session.modified = True
    return jsonify({
        "success": True,
        "is_active": is_active,
        "message": message,
        "wishlist_count": len(wishlist)
    })


@main_bp.route("/api/counts")
def api_counts():
    """현재 장바구니 및 관심 상품 카운트 반환"""
    cart = _get_cart()
    wishlist = _get_wishlist()
    return jsonify({
        "cart_count": sum(item.get("quantity", 1) for item in cart.values()),
        "wishlist_count": len(wishlist)
    })
