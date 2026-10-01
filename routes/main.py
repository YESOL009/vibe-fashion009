"""
메인 라우트 블루프린트 모듈
- 쇼핑몰 메인 페이지 및 상품 목록/상세 화면을 처리합니다.
"""

import os
import sys
import traceback
from flask import Blueprint, render_template, session, jsonify, request, redirect, url_for, flash
from dotenv import load_dotenv
from supabase import create_client, Client
from app.routes.auth import login_required, get_supabase_client

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

# Supabase Service Key 관리자 클라이언트 헬퍼
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")


def get_admin_client() -> Client | None:
    """Supabase 서비스 키 관리자 클라이언트 반환 (profiles 등 서비스 전용 작업용)"""
    if SUPABASE_URL and (SUPABASE_SERVICE_KEY or SUPABASE_ANON_KEY):
        try:
            return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY or SUPABASE_ANON_KEY)
        except Exception as e:
            print(f"[Supabase Admin 클라이언트 오류] {e}", file=sys.stderr)
    return None

# 특정 상품 정적 이미지 우선 매핑
LOCAL_IMAGE_MAP = {
    "베이직 크롭 티셔츠": "/static/images/crop_tee.png",
    "와이드 데님 팬츠": "/static/images/denim_pants.png",
    "오버핏 코튼 자켓": "/static/images/cotton_jacket.png",
    "플로럴 미디 원피스": "/static/images/floral_dress.png",
}

# 기본 정상가(원가) 매핑 (DB 컬럼에 original_price가 없을 경우 적용)
DEFAULT_ORIGINAL_PRICES = {
    "베이직 크롭 티셔츠": 29900,
    "와이드 데님 팬츠": 49900,
    "오버핏 코튼 자켓": 89000,
    "플로럴 미디 원피스": 59900,
    "청키 스트릿 스니커즈": 89000,
    "빈티지 워싱 볼캡": 35000,
}


def get_featured_products(limit: int = 4):
    """
    Supabase products 테이블에서 is_active=true인 추천 상품을 조회합니다.
    - 실패 시 빈 리스트를 반환하며 터미널에 에러 로그를 출력합니다.
    - 가격 포맷팅({:,}원) 및 thumbnail_url 처리를 수행합니다.
    """
    if not supabase:
        print("[Supabase 오류] SUPABASE_URL 또는 SUPABASE_ANON_KEY 설정이 올바르지 않습니다.", file=sys.stderr)
        return []

    try:
        query = (
            supabase.table("products")
            .select("*, categories(name, slug), product_images(*)")
            .eq("is_active", True)
            .limit(limit)
        )
        response = query.execute()
        data = response.data or []

        seen_names = set()
        formatted_products = []
        for item in data:
            name = item.get("name")
            if name in seen_names:
                continue
            seen_names.add(name)

            # 1. 가격 및 원가/할인율 포맷팅
            raw_price = item.get("price") or 0
            price_int = int(raw_price)
            price_formatted = f"{price_int:,}원"

            raw_orig_price = item.get("original_price")
            if raw_orig_price:
                orig_price = int(raw_orig_price)
            else:
                orig_price = DEFAULT_ORIGINAL_PRICES.get(name) or (int(price_int * 1.3 // 1000 * 1000) if price_int else 0)

            orig_price_formatted = f"{orig_price:,}원" if orig_price else ""
            discount_rate = int(round((orig_price - price_int) / orig_price * 100)) if (orig_price and orig_price > price_int) else 0

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
                "original_price": orig_price,
                "original_price_formatted": orig_price_formatted,
                "discount_rate": discount_rate,
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
@main_bp.route("/products/<product_id>")
def product_detail(product_id):
    """
    상품 상세 페이지 라우트 (단일 상품 보기)
    - GET /product/<product_id> 및 GET /products/<product_id> 호환
    - Supabase에서 product_id로 상품 정보 조회
    - product_options 테이블에서 색상(color) DISTINCT 조회
    """
    product = None
    colors = []
    if supabase:
        try:
            res = (
                supabase.table("products")
                .select("*, categories(name, slug), product_images(*), product_options(*)")
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

                raw_orig_price = item.get("original_price")
                if raw_orig_price:
                    orig_price = int(raw_orig_price)
                else:
                    orig_price = DEFAULT_ORIGINAL_PRICES.get(prod_name) or (int(price_int * 1.3 // 1000 * 1000) if price_int else 0)

                orig_price_formatted = f"{orig_price:,}원" if orig_price else ""
                discount_rate = int(round((orig_price - price_int) / orig_price * 100)) if (orig_price and orig_price > price_int) else 0

                category_data = item.get("categories")
                category_name = category_data.get("name") if isinstance(category_data, dict) else "FASHION"

                # product_options에서 color가 존재하는 고유 색상 목록(DISTINCT) 추출
                raw_options = item.get("product_options") or []
                for opt in raw_options:
                    c = opt.get("color")
                    if c and c not in colors:
                        colors.append(c)

                # 옵션 파싱 (기존 옵션 호환용)
                parsed_options = []
                for opt in raw_options:
                    val = opt.get("option_value")
                    # 베이직 크롭 티셔츠의 경우 요청에 따라 '베이지' 색상 제외
                    if prod_name == "베이직 크롭 티셔츠" and "베이지" in str(val):
                        continue
                    if val and val not in parsed_options:
                        parsed_options.append(val)

                if not parsed_options:
                    if prod_name == "베이직 크롭 티셔츠":
                        parsed_options = ["화이트 / S", "화이트 / M", "화이트 / L", "블랙 / S", "블랙 / M", "블랙 / L"]
                    elif "스니커즈" in prod_name or "신발" in category_name:
                        parsed_options = ["240", "250", "260", "270", "280"]
                    elif "팬츠" in prod_name or "하의" in category_name:
                        parsed_options = ["S (28)", "M (30)", "L (32)", "XL (34)"]
                    elif "모자" in prod_name or "볼캡" in prod_name or "acc" in str(category_data).lower():
                        parsed_options = ["FREE"]
                    else:
                        parsed_options = ["S (90)", "M (95)", "L (100)", "XL (105)"]

                product = {
                    "id": item.get("id"),
                    "name": prod_name,
                    "category": category_name,
                    "price": price_int,
                    "price_formatted": f"{price_int:,}원",
                    "original_price": orig_price,
                    "original_price_formatted": orig_price_formatted,
                    "discount_rate": discount_rate,
                    "thumbnail_url": thumbnail_url,
                    "image": thumbnail_url,
                    "description": item.get("description") or "",
                    "badge": item.get("badge") or "HOT",
                    "badge_class": item.get("badge_class") or "bg-primary",
                    "rating": item.get("rating_avg") or 5.0,
                    "options": parsed_options,
                    "colors": colors,
                }
        except Exception as e:
            print(f"[Supabase 상품 상세 조회 실패] {e}", file=sys.stderr)
            traceback.print_exc()

    # 위시리스트 여부 확인
    is_in_wishlist = False
    if product:
        wishlist = _get_wishlist()
        is_in_wishlist = any(w.get("id") == str(product["id"]) or w.get("name") == product["name"] for w in wishlist)

    return render_template(
        "detail.html",
        brand_name="VIBE-FASHION",
        product=product,
        colors=colors,
        is_in_wishlist=is_in_wishlist
    )


@main_bp.route("/api/products/<product_id>/sizes")
def api_product_sizes(product_id):
    """
    상품 색상별 사이즈 및 재고 조회 API
    GET /api/products/<product_id>/sizes?color=<선택한 색상>
    - product_options 테이블에서 product_id + color로 필터링
    - size, stock을 JSON 배열로 반환
      예: [{"size": "S", "stock": 3}, {"size": "M", "stock": 0}]
    """
    selected_color = request.args.get("color", "").strip()
    if not supabase or not product_id or not selected_color:
        return jsonify([])

    try:
        # product_options 테이블에서 product_id 및 color로 필터링
        res = (
            supabase.table("product_options")
            .select("size, stock, stock_quantity, option_value")
            .eq("product_id", product_id)
            .ilike("color", selected_color)
            .execute()
        )
        options = res.data or []

        # 사이즈 표기 기본 정렬 (XS -> S -> M -> L -> XL -> XXL -> 기타)
        size_priority = {"XS": 1, "S": 2, "M": 3, "L": 4, "XL": 5, "XXL": 6, "FREE": 99}
        options.sort(key=lambda o: size_priority.get(str(o.get("size") or "").upper(), 50))

        sizes = []
        for opt in options:
            size_val = opt.get("size") or opt.get("option_value") or "FREE"
            # stock 컬럼 우선 참조, 없으면 stock_quantity 호환 적용
            stock_val = opt.get("stock") if opt.get("stock") is not None else opt.get("stock_quantity", 0)
            sizes.append({
                "size": size_val,
                "stock": int(stock_val or 0)
            })

        # size, stock 형태의 JSON 배열 반환
        return jsonify(sizes)
    except Exception as e:
        print(f"[색상별 사이즈 조회 오류] {e}", file=sys.stderr)
        return jsonify([]), 500


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


# -----------------------------------------------------------------------------
# 주문 및 결제 (Checkout) 라우트
# -----------------------------------------------------------------------------

def _get_available_coupons(is_logged_in: bool = False):
    """
    사용자가 사용 가능한 쿠폰 목록 반환
    - 로그인된 회원에게만 신규회원 웰컴 쿠폰 제공
    - 비로그인(게스트)은 회원 전용 쿠폰 사용 불가
    """
    if not is_logged_in:
        return []

    # 로그인 회원 전용 쿠폰 목록
    return [
        {
            "code": "WELCOME15",
            "name": "신규회원 가입 15% 웰컴 쿠폰",
            "discount_rate": 15,
            "badge": "15% 할인",
            "description": "전 상품 결제 시 15% 즉시 할인",
            "min_amount": 0
        },
        {
            "code": "VIBE10",
            "name": "2026 S/S 시즌 오프닝 10% 쿠폰",
            "discount_rate": 10,
            "badge": "10% 할인",
            "description": "봄/여름 컬렉션 10% 추가 할인",
            "min_amount": 0
        }
    ]


@main_bp.route("/checkout", methods=["GET"])
def checkout_page():
    """
    주문/결제 화면
    """
    cart = _get_cart()
    if not cart:
        flash("장바구니가 비어 있습니다. 상품을 먼저 담아주세요.", "info")
        return redirect(url_for("main.cart_page"))

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

    is_logged_in = bool(session.get("user") or session.get("user_id"))
    coupons = _get_available_coupons(is_logged_in=is_logged_in)

    return render_template(
        "checkout.html",
        brand_name="VIBE-FASHION",
        items=items,
        total_price=total_price,
        total_price_formatted=f"{total_price:,}원",
        shipping_fee=shipping_fee,
        shipping_fee_formatted=f"{shipping_fee:,}원" if shipping_fee > 0 else "무료배송",
        final_total=final_total,
        final_total_formatted=f"{final_total:,}원",
        available_coupons=coupons,
        is_logged_in=is_logged_in,
        user=session.get("user")
    )


@main_bp.route("/checkout/process", methods=["POST"])
def checkout_process():
    """
    결제 처리 및 주문 완료
    """
    cart = _get_cart()
    if not cart:
        flash("주문할 상품이 없습니다.", "error")
        return redirect(url_for("main.index"))

    import time
    buyer_name = request.form.get("buyer_name") or "구매자"
    buyer_phone = request.form.get("buyer_phone") or ""
    address = request.form.get("address") or ""
    address_detail = request.form.get("address_detail") or ""
    payment_method = request.form.get("payment_method") or "신용/체크카드"
    coupon_code = request.form.get("coupon_code") or ""

    is_logged_in = bool(session.get("user") or session.get("user_id"))

    try:
        total_price = int(request.form.get("total_price") or 0)
        discount_amount = int(request.form.get("discount_amount") or 0)
        shipping_fee = int(request.form.get("shipping_fee") or 0)
        final_amount = int(request.form.get("final_amount") or 0)
    except ValueError:
        total_price = sum(int(item.get("price", 0)) * int(item.get("quantity", 1)) for item in cart.values())
        shipping_fee = 0 if total_price >= 30000 else 3000
        discount_amount = 0
        final_amount = total_price + shipping_fee

    # 비로그인 상태에서 쿠폰 적용 시도 시 할인 무효화
    if not is_logged_in and discount_amount > 0:
        discount_amount = 0
        coupon_code = ""
        final_amount = total_price + shipping_fee

    # 고유 주문번호 생성 (예: ORD-20260928-123456)
    order_id = f"ORD-{time.strftime('%Y%m%d')}-{int(time.time() * 1000) % 1000000:06d}"
    order_time = time.strftime('%Y-%m-%d %H:%M:%S')

    order_info = {
        "order_id": order_id,
        "created_at": order_time,
        "buyer_name": buyer_name,
        "buyer_phone": buyer_phone,
        "address": address,
        "address_detail": address_detail,
        "payment_method": payment_method,
        "coupon_code": coupon_code,
        "total_price": total_price,
        "discount_amount": discount_amount,
        "shipping_fee": shipping_fee,
        "final_amount": final_amount,
        "item_count": sum(int(item.get("quantity", 1)) for item in cart.values())
    }

    # 주문 완료 후 장바구니 비우기
    session["cart"] = {}
    session["last_order"] = order_info
    session.modified = True

    return render_template(
        "checkout_success.html",
        brand_name="VIBE-FASHION",
        order=order_info
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

    # product_id와 option 조합으로 고유 키 생성
    key = f"{product_id}_{option}" if product_id else f"{product_name}_{option}"

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


# -----------------------------------------------------------------------------
# 사용자 마이페이지 및 기존 라우트 호환
# -----------------------------------------------------------------------------

@main_bp.route("/mypage", methods=["GET", "POST"])
@login_required
def mypage():
    """마이페이지 - 인증된 회원 정보 조회 및 수정 뼈대"""
    user_id = session.get("user_id")

    admin_client = get_admin_client() or supabase
    profile_data = {}
    auth_user = None

    # Supabase Auth 사용자 정보 조회
    if admin_client:
        try:
            user_resp = admin_client.auth.admin.get_user_by_id(user_id)
            if user_resp and user_resp.user:
                auth_user = user_resp.user
        except Exception as e:
            print(f"[마이페이지 Auth 조회 알림] {e}", file=sys.stderr)

    # Supabase profiles 테이블에서 회원 정보 조회
    if admin_client:
        try:
            res = admin_client.table("profiles").select("*").eq("id", user_id).maybe_single().execute()
            if res and res.data:
                profile_data = res.data
        except Exception as e:
            print(f"[마이페이지 profiles 조회 오류] {e}", file=sys.stderr)

    # profiles 행이 없거나 기본 필드가 비어있을 경우 세션/Auth 메타데이터로 보완
    session_user = session.get("user") or {}
    user_meta = getattr(auth_user, "user_metadata", {}) or {}

    email = (
        profile_data.get("email")
        or getattr(auth_user, "email", None)
        or session_user.get("email", "")
    )
    full_name = (
        profile_data.get("full_name")
        or user_meta.get("full_name")
        or user_meta.get("name")
        or session_user.get("name")
        or (email.split("@")[0] if email else "회원")
    )
    phone = (
        profile_data.get("phone")
        or user_meta.get("phone")
        or ""
    )
    # 기본 배송지 (profiles 컬럼 또는 user_metadata에 저장된 값)
    address = (
        profile_data.get("address")
        or profile_data.get("shipping_address")
        or user_meta.get("address")
        or ""
    )
    address_detail = (
        profile_data.get("address_detail")
        or profile_data.get("shipping_address_detail")
        or user_meta.get("address_detail")
        or ""
    )

    # POST 요청: 회원 정보 (이름, 전화번호, 기본 배송지) 수정 처리
    if request.method == "POST":
        new_name = (request.form.get("full_name") or "").strip()
        new_phone = (request.form.get("phone") or "").strip()
        new_address = (request.form.get("address") or "").strip()
        new_address_detail = (request.form.get("address_detail") or "").strip()

        if not new_name:
            flash("이름을 입력해주세요.", "error")
            return redirect(url_for("main.mypage"))

        # 1. profiles 테이블 갱신 시도
        profile_update = {
            "full_name": new_name,
            "phone": new_phone
        }
        # address 컬럼 존재 여부 체크 후 동적 반영
        if "address" in profile_data:
            profile_update["address"] = new_address
        if "address_detail" in profile_data:
            profile_update["address_detail"] = new_address_detail

        if admin_client:
            try:
                admin_client.table("profiles").upsert({
                    "id": user_id,
                    "email": email,
                    **profile_update
                }).execute()
            except Exception as e:
                print(f"[profiles 테이블 업데이트 오류] {e}", file=sys.stderr)

            # 2. Auth user_metadata에도 배송지 및 이름 동기화 (스키마 컬럼 독립성 보장)
            try:
                updated_meta = {**user_meta, "full_name": new_name, "phone": new_phone, "address": new_address, "address_detail": new_address_detail}
                admin_client.auth.admin.update_user_by_id(user_id, {"user_metadata": updated_meta})
            except Exception as e:
                print(f"[Auth user_metadata 업데이트 오류] {e}", file=sys.stderr)

        # 3. Flask 세션 정보 동기화
        if "user" in session and isinstance(session["user"], dict):
            session["user"]["name"] = new_name
            session.modified = True

        flash("회원 정보가 성공적으로 수정되었습니다.", "success")
        return redirect(url_for("main.mypage"))

    # 이메일/비밀번호 가입 사용자 여부 판별 (소셜 로그인 사용자는 비밀번호 변경 불가)
    is_email_user = False
    social_providers = {"kakao", "azure", "microsoft", "google", "naver", "github", "facebook"}

    if auth_user:
        app_meta = getattr(auth_user, "app_metadata", {}) or {}
        user_meta = getattr(auth_user, "user_metadata", {}) or {}
        providers = app_meta.get("providers") or []
        primary_provider = app_meta.get("provider")
        identities = getattr(auth_user, "identities", []) or []
        identity_providers = [
            getattr(ident, "provider", None) if hasattr(ident, "provider") else (ident.get("provider") if isinstance(ident, dict) else None)
            for ident in identities
        ]
        has_social = bool(
            (set(providers) & social_providers)
            or (primary_provider in social_providers)
            or (set(identity_providers) & social_providers)
            or (user_meta.get("provider") in social_providers)
            or (user_meta.get("iss") or "").startswith("https://kapi.kakao.com")
        )
        if not has_social and ("email" in providers or primary_provider == "email" or "email" in identity_providers):
            is_email_user = True
    else:
        has_social_session = bool(
            session.get("kakao_user_id")
            or session.get("provider_token")
            or session.get("provider") in social_providers
        )
        is_email_user = not has_social_session

    # 템플릿 전달용 프로필 뷰 객체 구성
    profile_view = {
        "id": user_id,
        "email": email,
        "full_name": full_name,
        "phone": phone,
        "address": address,
        "address_detail": address_detail,
        "grade": profile_data.get("grade", "BRONZE"),
        "points": profile_data.get("points", 1000),
        "total_spent": profile_data.get("total_spent", 0),
        "is_email_user": is_email_user
    }

    return render_template(
        "mypage.html",
        brand_name="VIBE-FASHION",
        profile=profile_view,
        user=session_user,
        is_email_user=is_email_user
    )


@main_bp.route("/mypage/change-password", methods=["POST"])
@login_required
def change_password():
    """
    [POST /mypage/change-password] 마이페이지 내 비밀번호 변경 처리
    - 기존 비밀번호 검증 (Supabase 재로그인 확인)
    - 새 비밀번호 검증 (Day 4 규칙: 일치 여부, 6자 이상, 기존 비밀번호와 불일치)
    - Supabase update_user_by_id()를 통한 비밀번호 갱신
    """
    user_id = session.get("user_id")
    admin_client = get_admin_client() or supabase

    if not user_id or not admin_client:
        flash("로그인이 필요한 서비스입니다.", "error")
        return redirect(url_for("auth.login"))

    # 사용자 Auth 정보 조회
    auth_user = None
    try:
        user_resp = admin_client.auth.admin.get_user_by_id(user_id)
        if user_resp and user_resp.user:
            auth_user = user_resp.user
    except Exception as e:
        print(f"[비밀번호 변경 Auth 조회 오류] {e}", file=sys.stderr)

    # 소셜 로그인 가입자 여부 검증 (소셜 회원은 비밀번호가 없음)
    is_email_user = False
    social_providers = {"kakao", "azure", "microsoft", "google", "naver", "github", "facebook"}

    if auth_user:
        app_meta = getattr(auth_user, "app_metadata", {}) or {}
        user_meta = getattr(auth_user, "user_metadata", {}) or {}
        providers = app_meta.get("providers") or []
        primary_provider = app_meta.get("provider")
        identities = getattr(auth_user, "identities", []) or []
        identity_providers = [
            getattr(ident, "provider", None) if hasattr(ident, "provider") else (ident.get("provider") if isinstance(ident, dict) else None)
            for ident in identities
        ]
        has_social = bool(
            (set(providers) & social_providers)
            or (primary_provider in social_providers)
            or (set(identity_providers) & social_providers)
            or (user_meta.get("provider") in social_providers)
            or (user_meta.get("iss") or "").startswith("https://kapi.kakao.com")
        )
        if not has_social and ("email" in providers or primary_provider == "email" or "email" in identity_providers):
            is_email_user = True
    else:
        has_social_session = bool(
            session.get("kakao_user_id")
            or session.get("provider_token")
            or session.get("provider") in social_providers
        )
        is_email_user = not has_social_session

    if not is_email_user:
        flash("소셜 로그인으로 가입된 계정은 비밀번호를 변경할 수 없습니다.", "error")
        return redirect(url_for("main.mypage"))

    # 사용자 이메일 확보
    email = (
        getattr(auth_user, "email", None)
        or (session.get("user") or {}).get("email")
    )
    if not email:
        flash("사용자 계정 정보를 찾을 수 없습니다.", "error")
        return redirect(url_for("main.mypage"))

    current_password = request.form.get("current_password") or ""
    new_password = request.form.get("new_password") or ""
    new_password_confirm = request.form.get("new_password_confirm") or ""

    # 필수값 검증
    if not current_password or not new_password or not new_password_confirm:
        flash("모든 항목을 입력해주세요.", "error")
        return redirect(url_for("main.mypage"))

    # 새 비밀번호와 기존 비밀번호 동일 검증
    if current_password == new_password:
        flash("새로운 비밀번호가 현재 비밀번호와 동일합니다", "error")
        return redirect(url_for("main.mypage"))

    # Day 4 새 비밀번호 검증 조건: 불일치 체크 & 6자 이상
    if new_password != new_password_confirm:
        flash("비밀번호가 일치하지 않습니다.", "error")
        return redirect(url_for("main.mypage"))

    if len(new_password) < 6:
        flash("비밀번호는 최소 6자 이상이어야 합니다.", "error")
        return redirect(url_for("main.mypage"))

    # 기존 비밀번호 검증 (재로그인 방식으로 확인)
    try:
        verify_client = get_supabase_client()
        sign_in_res = verify_client.auth.sign_in_with_password({
            "email": email,
            "password": current_password
        })
        if not sign_in_res or not sign_in_res.user:
            flash("현재 비밀번호가 일치하지 않습니다", "error")
            return redirect(url_for("main.mypage"))
    except Exception as e:
        print(f"[현재 비밀번호 불일치/검증 오류] {e}", file=sys.stderr)
        flash("현재 비밀번호가 일치하지 않습니다", "error")
        return redirect(url_for("main.mypage"))

    # Supabase update_user_by_id()를 통한 비밀번호 변경
    try:
        admin_client.auth.admin.update_user_by_id(
            user_id,
            {"password": new_password}
        )
    except Exception as e:
        print(f"[Supabase update_user_by_id 오류] {e}", file=sys.stderr)
        flash("비밀번호 변경 처리 중 오류가 발생했습니다.", "error")
        return redirect(url_for("main.mypage"))

    flash("비밀번호가 변경되었습니다", "success")
    return redirect(url_for("main.mypage"))


@main_bp.route("/register", methods=["GET", "POST"])
def register_page():
    """기존 회원가입 URL 호환 (auth.signup으로 연결)"""
    return redirect(url_for("auth.signup"))


@main_bp.route("/login", methods=["GET", "POST"])
def login_page():
    """기존 로그인 URL 호환 (auth.login으로 연결)"""
    return redirect(url_for("auth.login"))


@main_bp.route("/logout")
def logout():
    """기존 로그아웃 URL 호환 (auth.logout으로 연결)"""
    return redirect(url_for("auth.logout"))
