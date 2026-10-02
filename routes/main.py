"""
메인 라우트 블루프린트 모듈
- 쇼핑몰 메인 페이지 및 상품 목록/상세 화면을 처리합니다.
- 장바구니, 위시리스트, 주문/결제, 마이페이지 기능을 제공합니다.
"""

import os
import sys
import re
import time
import random
import datetime
import traceback
from flask import (
    Blueprint,
    render_template,
    session,
    jsonify,
    request,
    redirect,
    url_for,
    flash,
)
from dotenv import load_dotenv
from supabase import Client
from app.routes.auth import login_required
from utils.db import (
    get_supabase_client,
    get_admin_client,
    is_valid_uuid,
    parse_datetime,
    get_product_thumbnail,
    LOCAL_IMAGE_MAP,
    DEFAULT_ORIGINAL_PRICES,
)

# .env 파일에서 환경변수 로드
load_dotenv()

# 'main' 블루프린트 생성
main_bp = Blueprint("main", __name__)

# 공통 클라이언트 및 하위 호환 alias
supabase = None
try:
    supabase = get_supabase_client()
except Exception as e:
    print(f"[Supabase 초기화 오류] {e}", file=sys.stderr)

_is_valid_uuid = is_valid_uuid
_parse_datetime = parse_datetime


def get_featured_products(limit: int = 4):
    """
    Supabase products 테이블에서 is_active=true인 추천 상품을 조회합니다.
    - 실패 시 빈 리스트를 반환하며 터미널에 에러 로그를 출력합니다.
    - 가격 포맷팅({:,}원) 및 thumbnail_url 처리를 수행합니다.
    """
    client = get_admin_client() or supabase
    if not client:
        print("[Supabase 오류] SUPABASE_URL 또는 SUPABASE_ANON_KEY 설정이 올바르지 않습니다.", file=sys.stderr)
        return []

    try:
        query = (
            client.table("products")
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

            # 2. thumbnail_url 추출 (공통 헬퍼 활용)
            thumbnail_url = get_product_thumbnail(name, item.get("id"), item.get("product_images"))

            # 3. 카테고리명 정리
            category_data = item.get("categories")
            category_name = category_data.get("name") if isinstance(category_data, dict) else "FASHION"

            formatted_products.append({
                "id": item.get("id"),
                "name": item.get("name"),
                "category": category_name or "FASHION",
                "price": price_int,
                "price_formatted": price_formatted,
                "original_price": orig_price,
                "original_price_formatted": orig_price_formatted,
                "discount_rate": discount_rate,
                "thumbnail_url": thumbnail_url,
                "image": thumbnail_url,
                "description": item.get("description") or "",
                "badge": item.get("badge") or "NEW",
                "badge_class": item.get("badge_class") or "bg-dark",
                "rating": item.get("rating_avg") or 5.0,
            })

        return formatted_products

    except Exception as e:
        print(f"[Supabase 상품 조회 실패] {e}", file=sys.stderr)
        return []
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
            .select("id, size, stock, stock_quantity, option_value")
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
                "id": opt.get("id"),
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


@main_bp.route("/cart/add", methods=["POST"])
def cart_add():
    """
    [POST /cart/add] 장바구니 담기 라우트
    - 요청 body: product_option_id, quantity
    - 로그인 안 했으면 /auth/login 으로 리다이렉트 (JSON 또는 302)
    - 담기 전에 product_options.stock을 조회해서 요청 수량보다 적으면
      "재고가 부족합니다(현재 N개)" 에러 반환, DB에 쓰지 않음
    - carts 테이블에 upsert (같은 옵션이면 수량 누적)
    - 누적 후 수량이 재고를 초과하게 되는 경우도 동일하게 에러 처리
    - 성공 시 JSON: {"success": true, "message": "장바구니에 담겼습니다"}
    """
    # 1. 로그인 여부 확인
    user_id = session.get("user_id")
    if not user_id:
        if request.is_json:
            return jsonify({
                "success": False,
                "error": "로그인이 필요한 서비스입니다.",
                "redirect_url": url_for("auth.login")
            }), 401
        return redirect(url_for("auth.login"))

    # 2. 요청 파라미터 파싱
    data = request.get_json(silent=True) or request.form.to_dict()
    product_option_id = str(data.get("product_option_id") or "").strip()
    try:
        quantity = int(data.get("quantity", 1))
    except (ValueError, TypeError):
        quantity = 1

    if not product_option_id:
        return jsonify({"success": False, "error": "옵션을 선택해주세요."}), 400

    if quantity <= 0:
        return jsonify({"success": False, "error": "수량은 1개 이상이어야 합니다."}), 400

    admin_client = get_admin_client() or supabase
    if not admin_client:
        return jsonify({"success": False, "error": "데이터베이스 연결에 실패했습니다."}), 500

    # 3. product_options 조회 및 재고 확인
    try:
        opt_res = (
            admin_client.table("product_options")
            .select("id, product_id, size, color, stock, stock_quantity, option_value, additional_price")
            .eq("id", product_option_id)
            .maybe_single()
            .execute()
        )
    except Exception as e:
        print(f"[장바구니 옵션 조회 오류] {e}", file=sys.stderr)
        return jsonify({"success": False, "error": "옵션 정보를 확인할 수 없습니다."}), 500

    if not opt_res or not opt_res.data:
        return jsonify({"success": False, "error": "유효하지 않은 상품 옵션입니다."}), 404

    option_data = opt_res.data
    product_id = option_data.get("product_id")
    stock_val = option_data.get("stock") if option_data.get("stock") is not None else option_data.get("stock_quantity", 0)
    current_stock = int(stock_val or 0)

    # 4. 담기 전 요청 수량이 재고보다 많은 경우 에러
    if quantity > current_stock:
        return jsonify({
            "success": False,
            "error": f"재고가 부족합니다(현재 {current_stock}개)"
        }), 400

    # 5. 기존 장바구니 수량 조회 (누적 후 초과 여부 검증)
    existing_qty = 0
    try:
        cart_item_res = (
            admin_client.table("carts")
            .select("id, quantity")
            .eq("user_id", user_id)
            .eq("option_id", product_option_id)
            .maybe_single()
            .execute()
        )
        if cart_item_res and cart_item_res.data:
            existing_qty = int(cart_item_res.data.get("quantity") or 0)
    except Exception as e:
        print(f"[기존 장바구니 항목 조회 오류] {e}", file=sys.stderr)

    new_total_qty = existing_qty + quantity

    # 6. 누적 후 수량이 재고를 초과하는 경우 에러
    if new_total_qty > current_stock:
        return jsonify({
            "success": False,
            "error": f"재고가 부족합니다(현재 {current_stock}개)"
        }), 400

    # 7. carts 테이블에 upsert
    import datetime
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        upsert_payload = {
            "user_id": user_id,
            "product_id": product_id,
            "option_id": product_option_id,
            "quantity": new_total_qty,
            "updated_at": now_iso
        }
        admin_client.table("carts").upsert(
            upsert_payload,
            on_conflict="user_id,product_id,option_id"
        ).execute()
    except Exception as e:
        print(f"[carts 테이블 upsert 오류] {e}", file=sys.stderr)
        return jsonify({"success": False, "error": "장바구니 저장 중 오류가 발생했습니다."}), 500

    # 세션 장바구니 및 뱃지 카운트 동기화
    try:
        user_carts = admin_client.table("carts").select("quantity").eq("user_id", user_id).execute()
        total_cart_count = sum(int(item.get("quantity") or 0) for item in (user_carts.data or []))
    except Exception:
        total_cart_count = None

    return jsonify({
        "success": True,
        "message": "장바구니에 담겼습니다",
        "cart_count": total_cart_count
    })


@main_bp.route("/cart/<cart_id>", methods=["PATCH"])
def cart_update(cart_id):
    """
    [PATCH /cart/<cart_id>] 장바구니 수량 변경 라우트
    - 요청 body: quantity (변경할 새 수량)
    - 본인 소유의 장바구니 아이템인지 확인 (다른 사용자의 cart_id 접근 차단)
    - quantity가 1 미만이면 에러
    - 변경하려는 quantity가 해당 옵션의 stock을 초과하면
      "재고가 부족합니다(현재 N개)" 에러, 변경하지 않음
    - 성공 시 UPDATE 후 새 소계(subtotal) 반환
    """
    # 1. 로그인 여부 확인
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"success": False, "error": "로그인이 필요한 서비스입니다."}), 401

    # 2. 요청 파라미터 파싱
    data = request.get_json(silent=True) or request.form.to_dict()
    try:
        new_quantity = int(data.get("quantity", 1))
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "수량은 정수여야 합니다."}), 400

    if new_quantity < 1:
        return jsonify({"success": False, "error": "수량은 1개 이상이어야 합니다."}), 400

    admin_client = get_admin_client() or supabase
    if not admin_client:
        return jsonify({"success": False, "error": "데이터베이스 연결에 실패했습니다."}), 500

    # 3. carts 테이블에서 해당 cart_id 조회
    try:
        cart_res = (
            admin_client.table("carts")
            .select("id, user_id, option_id, product_id, quantity")
            .eq("id", cart_id)
            .maybe_single()
            .execute()
        )
    except Exception as e:
        print(f"[장바구니 항목 조회 오류] {e}", file=sys.stderr)
        return jsonify({"success": False, "error": "장바구니 항목을 조회할 수 없습니다."}), 500

    if not cart_res or not cart_res.data:
        return jsonify({"success": False, "error": "해당 장바구니 항목을 찾을 수 없습니다."}), 404

    cart_item = cart_res.data
    cart_user_id = cart_item.get("user_id")
    option_id = cart_item.get("option_id")
    product_id = cart_item.get("product_id")

    # 4. 본인 소유 확인
    if str(cart_user_id) != str(user_id):
        return jsonify({"success": False, "error": "다른 사용자의 장바구니에 접근할 수 없습니다."}), 403

    # 5. product_options에서 stock 조회
    if not option_id:
        return jsonify({"success": False, "error": "장바구니 항목의 옵션 정보가 없습니다."}), 400

    try:
        opt_res = (
            admin_client.table("product_options")
            .select("stock, stock_quantity")
            .eq("id", option_id)
            .maybe_single()
            .execute()
        )
    except Exception as e:
        print(f"[상품 옵션 재고 조회 오류] {e}", file=sys.stderr)
        return jsonify({"success": False, "error": "상품 옵션 정보를 조회할 수 없습니다."}), 500

    if not opt_res or not opt_res.data:
        return jsonify({"success": False, "error": "상품 옵션을 찾을 수 없습니다."}), 404

    option_data = opt_res.data
    stock_val = option_data.get("stock") if option_data.get("stock") is not None else option_data.get("stock_quantity", 0)
    current_stock = int(stock_val or 0)

    # 6. 변경하려는 수량이 재고를 초과하는 경우 에러
    if new_quantity > current_stock:
        return jsonify({
            "success": False,
            "error": f"재고가 부족합니다(현재 {current_stock}개)"
        }), 400

    # 7. carts 테이블 UPDATE
    import datetime
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        admin_client.table("carts").update(
            {"quantity": new_quantity, "updated_at": now_iso}
        ).eq("id", cart_id).execute()
    except Exception as e:
        print(f"[carts 테이블 업데이트 오류] {e}", file=sys.stderr)
        return jsonify({"success": False, "error": "장바구니 수량 변경 중 오류가 발생했습니다."}), 500

    # 8. 상품 가격 조회하여 새 소계 계산
    try:
        product_res = (
            admin_client.table("products")
            .select("price")
            .eq("id", product_id)
            .maybe_single()
            .execute()
        )
    except Exception as e:
        print(f"[상품 가격 조회 오류] {e}", file=sys.stderr)
        return jsonify({"success": False, "error": "상품 가격을 조회할 수 없습니다."}), 500

    if not product_res or not product_res.data:
        return jsonify({"success": False, "error": "상품을 찾을 수 없습니다."}), 404

    price = int(product_res.data.get("price") or 0)
    new_subtotal = price * new_quantity

    # 9. 사용자의 전체 카트 수량 계산
    user_carts_res = admin_client.table("carts").select("quantity").eq("user_id", user_id).execute()
    total_cart_count = sum(int(item.get("quantity") or 0) for item in user_carts_res.data or [])

    return jsonify({
        "success": True,
        "message": "장바구니 수량이 변경되었습니다",
        "quantity": new_quantity,
        "subtotal": new_subtotal,
        "subtotal_formatted": f"{new_subtotal:,}원",
        "cart_count": total_cart_count
    })


@main_bp.route("/cart/<cart_id>", methods=["DELETE"])
def cart_delete(cart_id):
    """
    [DELETE /cart/<cart_id>] 장바구니 아이템 삭제 라우트
    - 요청: 경로 매개변수 cart_id
    - 본인 소유의 장바구니 아이템인지 확인 후 삭제
    - 성공 시 JSON 응답 반환
    """
    # 1. 로그인 여부 확인
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"success": False, "error": "로그인이 필요한 서비스입니다."}), 401

    admin_client = get_admin_client() or supabase
    if not admin_client:
        return jsonify({"success": False, "error": "데이터베이스 연결에 실패했습니다."}), 500

    # 2. carts 테이블에서 해당 cart_id 조회
    try:
        cart_res = (
            admin_client.table("carts")
            .select("id, user_id")
            .eq("id", cart_id)
            .maybe_single()
            .execute()
        )
    except Exception as e:
        # UUID 형식이 아닌 경우 등의 DB 에러
        print(f"[장바구니 항목 조회 오류] {e}", file=sys.stderr)
        return jsonify({"success": False, "error": "유효하지 않은 장바구니 ID입니다."}), 400

    if not cart_res or not cart_res.data:
        return jsonify({"success": False, "error": "해당 장바구니 항목을 찾을 수 없습니다."}), 404

    cart_item = cart_res.data
    cart_user_id = cart_item.get("user_id")

    # 3. 본인 소유 확인
    if str(cart_user_id) != str(user_id):
        return jsonify({"success": False, "error": "다른 사용자의 장바구니에 접근할 수 없습니다."}), 403

    # 4. carts 테이블에서 해당 항목 삭제
    try:
        admin_client.table("carts").delete().eq("id", cart_id).execute()
    except Exception as e:
        print(f"[carts 테이블 삭제 오류] {e}", file=sys.stderr)
        return jsonify({"success": False, "error": "장바구니 항목 삭제 중 오류가 발생했습니다."}), 500

    return jsonify({
        "success": True,
        "message": "상품이 장바구니에서 삭제되었습니다"
    })


@main_bp.route("/cart", methods=["DELETE"])
def cart_clear():
    """
    [DELETE /cart] 장바구니 전체 비우기 라우트
    - 로그인한 사용자의 모든 장바구니 아이템 삭제
    - 성공 시 JSON 응답 반환
    """
    # 1. 로그인 여부 확인
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"success": False, "error": "로그인이 필요한 서비스입니다."}), 401

    admin_client = get_admin_client() or supabase
    if not admin_client:
        return jsonify({"success": False, "error": "데이터베이스 연결에 실패했습니다."}), 500

    # 2. 사용자의 모든 카트 항목 삭제
    try:
        admin_client.table("carts").delete().eq("user_id", user_id).execute()
    except Exception as e:
        print(f"[장바구니 전체 삭제 오류] {e}", file=sys.stderr)
        return jsonify({"success": False, "error": "장바구니 비우기 중 오류가 발생했습니다."}), 500

    return jsonify({
        "success": True,
        "message": "장바구니가 비워졌습니다",
        "cart_count": 0
    })


def _get_cart_items_and_total(user_id=None):
    """
    로그인 사용자(DB carts 테이블) 또는 비로그인 사용자(세션 cart)의
    장바구니 아이템 목록과 총 상품금액을 계산하여 반환하는 공통 함수
    """
    items = []
    total_price = 0

    if user_id:
        admin_client = get_admin_client() or supabase
        if admin_client:
            try:
                cart_res = (
                    admin_client.table("carts")
                    .select("id, product_id, option_id, quantity")
                    .eq("user_id", user_id)
                    .execute()
                )
                for cart_item in (cart_res.data or []):
                    cart_id = cart_item.get("id")
                    product_id = cart_item.get("product_id")
                    option_id = cart_item.get("option_id")
                    qty = int(cart_item.get("quantity", 1))

                    product_res = (
                        admin_client.table("products")
                        .select("name, price, product_images(*)")
                        .eq("id", product_id)
                        .maybe_single()
                        .execute()
                    )
                    if not product_res or not product_res.data:
                        continue

                    product = product_res.data
                    prod_name = product.get("name")
                    price = int(product.get("price", 0))
                    item_total = price * qty
                    total_price += item_total

                    thumbnail_url = get_product_thumbnail(prod_name, product_id, product.get("product_images"))

                    option_res = (
                        admin_client.table("product_options")
                        .select("color, size, stock, stock_quantity")
                        .eq("id", option_id)
                        .maybe_single()
                        .execute()
                    )
                    color = "기본"
                    size = "기본"
                    stock = 0
                    if option_res and option_res.data:
                        color = option_res.data.get("color", "기본")
                        size = option_res.data.get("size", "기본")
                        stock_val = (
                            option_res.data.get("stock")
                            if option_res.data.get("stock") is not None
                            else option_res.data.get("stock_quantity", 0)
                        )
                        stock = int(stock_val or 0)

                    items.append({
                        "cart_id": cart_id,
                        "id": product_id,
                        "option_id": option_id,
                        "name": prod_name,
                        "price": price,
                        "price_formatted": f"{price:,}원",
                        "quantity": qty,
                        "stock": stock,
                        "subtotal": item_total,
                        "subtotal_formatted": f"{item_total:,}원",
                        "thumbnail_url": thumbnail_url,
                        "color": color,
                        "size": size,
                        "option": f"{color}/{size}"
                    })
            except Exception as e:
                print(f"[_get_cart_items_and_total DB 조회 오류] {e}", file=sys.stderr)

    if not items:
        cart = _get_cart()
        admin_client = get_admin_client() or supabase
        for pid, info in cart.items():
            qty = int(info.get("quantity", 1))
            price = int(info.get("price", 0))
            item_total = price * qty
            total_price += item_total
            opt_id = info.get("option_id")
            stock = int(info.get("stock", 10))
            if opt_id and admin_client:
                try:
                    opt_res = (
                        admin_client.table("product_options")
                        .select("stock, stock_quantity")
                        .eq("id", opt_id)
                        .maybe_single()
                        .execute()
                    )
                    if opt_res and opt_res.data:
                        stock_val = (
                            opt_res.data.get("stock")
                            if opt_res.data.get("stock") is not None
                            else opt_res.data.get("stock_quantity", 0)
                        )
                        stock = int(stock_val or 0)
                except Exception:
                    pass

            items.append({
                "cart_id": pid,
                "id": info.get("id") or pid,
                "option_id": opt_id,
                "name": info.get("name"),
                "price": price,
                "price_formatted": f"{price:,}원",
                "quantity": qty,
                "stock": stock,
                "subtotal": item_total,
                "subtotal_formatted": f"{item_total:,}원",
                "thumbnail_url": info.get("thumbnail_url"),
                "option": info.get("option", "기본 옵션")
            })

    return items, total_price


@main_bp.route("/cart")
def cart_page():
    """
    장바구니 페이지 라우트
    - DB 기반 carts 테이블 (로그인 사용자만)
    - 세션 기반 cart (비로그인 사용자)
    """
    user_id = session.get("user_id")
    items, total_price = _get_cart_items_and_total(user_id)

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

def _get_user_used_coupons(user_id=None):
    """
    사용자가 이미 사용한 쿠폰 코드 목록 반환
    - Flask session 및 Supabase Auth user_metadata 연동
    """
    used = set()
    # 1. 세션에서 확인
    sess_used = session.get("used_coupons") or []
    if isinstance(sess_used, list):
        used.update(sess_used)

    # 2. Supabase Auth user_metadata에서 확인
    if user_id and _is_valid_uuid(user_id):
        admin_client = get_admin_client() or supabase
        if admin_client:
            try:
                user_res = admin_client.auth.admin.get_user_by_id(user_id)
                if user_res and hasattr(user_res, "user") and user_res.user:
                    user_meta = getattr(user_res.user, "user_metadata", {}) or {}
                    meta_used = user_meta.get("used_coupons") or []
                    if isinstance(meta_used, list):
                        used.update(meta_used)
            except Exception as e:
                print(f"[사용자 사용 쿠폰 조회 알림] {e}", file=sys.stderr)

    return list(used)


def _mark_coupon_as_used(coupon_code, user_id=None):
    """
    결제 시 사용한 쿠폰을 사용 완료 상태로 저장하여 다시 표시되지 않도록 처리
    - 세션 session['used_coupons'] 및 Supabase Auth user_metadata에 저장
    """
    if not coupon_code:
        return

    # 1. 세션 저장
    sess_used = list(session.get("used_coupons") or [])
    if coupon_code not in sess_used:
        sess_used.append(coupon_code)
        session["used_coupons"] = sess_used
        session.modified = True

    # 2. Supabase Auth user_metadata 저장
    if user_id and _is_valid_uuid(user_id):
        admin_client = get_admin_client() or supabase
        if admin_client:
            try:
                user_res = admin_client.auth.admin.get_user_by_id(user_id)
                if user_res and hasattr(user_res, "user") and user_res.user:
                    user_meta = getattr(user_res.user, "user_metadata", {}) or {}
                    meta_used = list(user_meta.get("used_coupons") or [])
                    if coupon_code not in meta_used:
                        meta_used.append(coupon_code)
                        admin_client.auth.admin.update_user_by_id(
                            user_id,
                            {"user_metadata": {**user_meta, "used_coupons": meta_used}}
                        )
            except Exception as e:
                print(f"[쿠폰 사용 완료 처리 알림] {e}", file=sys.stderr)


def _get_available_coupons(is_logged_in: bool = False, user_id: str = None):
    """
    사용자가 사용 가능한 쿠폰 목록 반환
    - 로그인된 회원에게만 신규회원 웰컴 쿠폰 제공
    - 비로그인(게스트)은 회원 전용 쿠폰 사용 불가
    - 결제 시 이미 사용한 쿠폰은 목록에서 제외(사라지게 처리)
    """
    if not is_logged_in:
        return []

    all_coupons = [
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

    used_coupons = _get_user_used_coupons(user_id)
    # 이미 사용된 쿠폰은 목록에서 제외
    return [c for c in all_coupons if c["code"] not in used_coupons]


def _is_valid_uuid(val):
    """UUID 문자열 형식 유효성 확인 헬퍼"""
    if not val:
        return False
    try:
        import uuid
        uuid.UUID(str(val))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


@main_bp.route("/order/checkout", methods=["GET"])
@login_required
def checkout_page():
    """
    [GET /order/checkout] 주문서 작성 및 결제 화면
    - 로그인 필수 (@login_required)
    - 장바구니 비어있으면 /cart 리다이렉트
    - 장바구니에 품절(stock=0) 아이템이 하나라도 있으면 /cart 리다이렉트 및
      '품절된 상품이 있어 주문할 수 없습니다' 안내
    - 장바구니 아이템 목록 조회 (수정 불가)
    - 마이페이지 기본 배송지 (profiles 테이블) 조회
    - 결제 금액 요약 (상품금액 + 배송비 = 최종금액)
    """
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("auth.login", error="login_required"))

    items, total_price = _get_cart_items_and_total(user_id)

    # 1. 장바구니 비어있으면 /cart 리다이렉트
    if not items:
        flash("장바구니가 비어 있습니다. 상품을 먼저 담아주세요.", "info")
        return redirect(url_for("main.cart_page"))

    # 2. 장바구니에 품절(stock=0) 아이템이 하나라도 있으면 /cart로 리다이렉트하고 안내
    has_out_of_stock = any(int(item.get("stock", 0)) <= 0 for item in items)
    if has_out_of_stock:
        flash("품절된 상품이 있어 주문할 수 없습니다", "danger")
        return redirect(url_for("main.cart_page"))

    # 3. 배송비 및 최종금액 계산
    shipping_fee = 0 if (total_price >= 30000 or total_price == 0) else 3000
    final_total = total_price + shipping_fee

    # 4. 마이페이지에 저장된 기본 배송지 (profiles 테이블) 조회
    admin_client = get_admin_client() or supabase
    profile_data = {}
    auth_user = None

    if admin_client and user_id and _is_valid_uuid(user_id):
        try:
            p_res = (
                admin_client.table("profiles")
                .select("*")
                .eq("id", user_id)
                .maybe_single()
                .execute()
            )
            if p_res and p_res.data:
                profile_data = p_res.data
        except Exception as e:
            print(f"[checkout profiles 조회 오류] {e}", file=sys.stderr)

        try:
            u_res = admin_client.auth.admin.get_user_by_id(user_id)
            if u_res and hasattr(u_res, "user"):
                auth_user = u_res.user
        except Exception:
            pass

    user_meta = getattr(auth_user, "user_metadata", {}) or {}
    session_user = session.get("user") or {}

    default_name = (
        profile_data.get("full_name")
        or user_meta.get("full_name")
        or user_meta.get("name")
        or session_user.get("name")
        or ""
    )
    default_phone = (
        profile_data.get("phone")
        or user_meta.get("phone")
        or ""
    )
    default_address = (
        profile_data.get("address")
        or profile_data.get("shipping_address")
        or user_meta.get("address")
        or ""
    )
    default_address_detail = (
        profile_data.get("address_detail")
        or profile_data.get("shipping_address_detail")
        or user_meta.get("address_detail")
        or ""
    )

    default_delivery = {
        "recipient_name": default_name,
        "recipient_phone": default_phone,
        "shipping_address": default_address,
        "shipping_address_detail": default_address_detail,
        "has_saved_address": bool(default_address or default_phone)
    }

    coupons = _get_available_coupons(is_logged_in=True, user_id=user_id)

    return render_template(
        "checkout.html",
        brand_name="VIBE-FASHION",
        items=items,
        total_price=total_price,
        total_price_formatted=f"{total_price:,}원",
        shipping_fee=shipping_fee,
        shipping_fee_formatted=f"{shipping_fee:,}원" if shipping_fee > 0 else "0원 (무료배송)",
        final_total=final_total,
        final_total_formatted=f"{final_total:,}원",
        available_coupons=coupons,
        is_logged_in=True,
        default_delivery=default_delivery,
        user=session.get("user")
    )


@main_bp.route("/checkout", methods=["GET"])
def checkout_redirect():
    """/checkout 접속 시 canonical 엔드포인트 /order/checkout 으로 리다이렉트"""
    return redirect(url_for("main.checkout_page"))


@main_bp.route("/api/user/default-address", methods=["GET"])
@login_required
def api_get_default_address():
    """
    [GET /api/user/default-address]
    - profiles 테이블에서 현재 로그인 사용자의 기본 배송지 정보 조회
    """
    user_id = session.get("user_id")
    admin_client = get_admin_client() or supabase
    profile_data = {}
    auth_user = None

    if admin_client and user_id and _is_valid_uuid(user_id):
        try:
            p_res = (
                admin_client.table("profiles")
                .select("*")
                .eq("id", user_id)
                .maybe_single()
                .execute()
            )
            if p_res and p_res.data:
                profile_data = p_res.data
        except Exception as e:
            print(f"[api_get_default_address profiles 조회 오류] {e}", file=sys.stderr)

        try:
            u_res = admin_client.auth.admin.get_user_by_id(user_id)
            if u_res and hasattr(u_res, "user"):
                auth_user = u_res.user
        except Exception:
            pass

    user_meta = getattr(auth_user, "user_metadata", {}) or {}
    session_user = session.get("user") or {}

    recipient_name = (
        profile_data.get("full_name")
        or user_meta.get("full_name")
        or user_meta.get("name")
        or session_user.get("name")
        or ""
    )
    phone = (
        profile_data.get("phone")
        or user_meta.get("phone")
        or ""
    )
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

    has_address = bool(address or phone)
    return jsonify({
        "success": True,
        "has_address": has_address,
        "data": {
            "recipient_name": recipient_name,
            "recipient_phone": phone,
            "shipping_address": address,
            "shipping_address_detail": address_detail
        }
    })


def _generate_order_number() -> str:
    """'VF-' + 오늘날짜(YYYYMMDD) + '-' + 4자리 랜덤숫자 + 밀리초 타임스탬프 뒷 3자리 고유 주문번호 생성"""
    now = datetime.datetime.now(datetime.timezone.utc)
    date_str = now.strftime("%Y%m%d")
    random_4digit = f"{random.randint(0, 9999):04d}"
    millis_last3 = f"{int(time.time() * 1000) % 1000:03d}"
    return f"VF-{date_str}-{random_4digit}{millis_last3}"


def _calculate_order_pricing(total_price: int, coupon_code: str):
    """배송비, 쿠폰 할인금액 및 최종 결제금액 계산"""
    shipping_fee = 0 if total_price >= 30000 else 3000
    discount_amount = 0
    if coupon_code == "WELCOME15":
        discount_amount = int((total_price * 0.15) // 10 * 10)
    elif coupon_code == "VIBE10":
        discount_amount = int((total_price * 0.10) // 10 * 10)

    final_amount = max(0, total_price - discount_amount) + shipping_fee
    return shipping_fee, discount_amount, final_amount


def _validate_shipping_input(form_data: dict):
    """배송지 폼 입력값 검증 (수령인 이름, 010-0000-0000 패턴, 주소 5자 이상)"""
    recipient_name = (form_data.get("recipient_name") or form_data.get("buyer_name") or "").strip()
    recipient_phone = (form_data.get("recipient_phone") or form_data.get("buyer_phone") or "").strip()
    shipping_address = (form_data.get("shipping_address") or form_data.get("address") or "").strip()

    if not recipient_name:
        return False, "수령인 이름을 입력해주세요."

    if not re.match(r"^010-\d{4}-\d{4}$", recipient_phone):
        return False, "휴대폰 번호는 010-0000-0000 형식이어야 합니다."

    if len(shipping_address) < 5:
        return False, "배송 주소는 최소 5자 이상이어야 합니다."

    return True, ""


def _rollback_order(admin_client, order_id: str, deducted_options: list):
    """주문 실패 또는 재고 소진 시 차감된 옵션 재고 복구 및 orders 레코드 삭제 (롤백)"""
    if not admin_client:
        return
    # 1. 차감했던 재고 원복
    for opt_id, qty in deducted_options:
        try:
            cur_res = (
                admin_client.table("product_options")
                .select("stock, stock_quantity")
                .eq("id", opt_id)
                .maybe_single()
                .execute()
            )
            if cur_res and cur_res.data:
                cur_val = cur_res.data.get("stock") or 0
                restored = int(cur_val) + qty
                admin_client.table("product_options").update({
                    "stock": restored,
                    "stock_quantity": restored
                }).eq("id", opt_id).execute()
        except Exception as restore_err:
            print(f"[재고 롤백 실패] {restore_err}", file=sys.stderr)

    # 2. orders 레코드 삭제 (ON DELETE CASCADE로 order_items도 동시 삭제)
    if order_id and _is_valid_uuid(order_id):
        try:
            admin_client.table("orders").delete().eq("id", order_id).execute()
        except Exception as del_err:
            print(f"[주문 레코드 롤백 삭제 실패] {del_err}", file=sys.stderr)


@main_bp.route("/order/create", methods=["POST"])
@main_bp.route("/order/checkout", methods=["POST"])
@main_bp.route("/checkout/process", methods=["POST"])
@login_required
def order_create():
    """
    [POST /order/create] 주문 생성 및 결제 처리
    처리 순서:
    1. 장바구니 조회 + 재고 확인 (재고 부족 시 에러, 처리 중단, 아무 것도 쓰지 않음)
    2. 배송지 입력값 서버 측 재검증 (휴대폰 번호 패턴, 주소 최소 길이)
    3. 주문번호 생성 및 금액 산정
    4. orders 테이블 INSERT (status='PAID', paid_at=now())
    5. order_items INSERT (상품명, 색상, 사이즈, 가격 스냅샷)
    6. product_options.stock 조건부 차감 (실패 시 롤백)
    7. carts 아이템 DELETE
    8. /order/complete/<order_id> 리다이렉트
    """
    user_id = session.get("user_id")
    if not user_id:
        flash("로그인이 필요한 서비스입니다.", "error")
        return redirect(url_for("auth.login"))

    # 1. 장바구니 조회 및 최신 재고 검증
    items, total_price = _get_cart_items_and_total(user_id)
    if not items:
        flash("장바구니가 비어 있습니다.", "info")
        return redirect(url_for("main.cart_page"))

    admin_client = get_admin_client() or supabase

    for it in items:
        opt_id = it.get("option_id")
        qty = int(it.get("quantity", 1))
        current_stock = int(it.get("stock", 0))

        if opt_id and admin_client and _is_valid_uuid(opt_id):
            try:
                opt_check = (
                    admin_client.table("product_options")
                    .select("stock, stock_quantity")
                    .eq("id", opt_id)
                    .maybe_single()
                    .execute()
                )
                if opt_check and opt_check.data:
                    val = (
                        opt_check.data.get("stock")
                        if opt_check.data.get("stock") is not None
                        else opt_check.data.get("stock_quantity", 0)
                    )
                    current_stock = int(val or 0)
            except Exception as e:
                print(f"[재고 사전 확인 오류] {e}", file=sys.stderr)

        if current_stock <= 0:
            flash("품절된 상품이 있어 주문할 수 없습니다", "danger")
            return redirect(url_for("main.cart_page"))
        if qty > current_stock:
            prod_name = it.get("name") or "상품"
            flash(f"[{prod_name}] 재고가 부족합니다 (현재 재고: {current_stock}개)", "danger")
            return redirect(url_for("main.cart_page"))

    # 2. 배송지 입력값 서버 측 재검증
    is_valid, val_err = _validate_shipping_input(request.form)
    if not is_valid:
        flash(val_err, "danger")
        return redirect(url_for("main.checkout_page"))

    recipient_name = (request.form.get("recipient_name") or request.form.get("buyer_name") or "").strip()
    recipient_phone = (request.form.get("recipient_phone") or request.form.get("buyer_phone") or "").strip()
    shipping_address = (request.form.get("shipping_address") or request.form.get("address") or "").strip()
    shipping_address_detail = (request.form.get("shipping_address_detail") or request.form.get("address_detail") or "").strip()
    delivery_request = (request.form.get("delivery_request") or request.form.get("shipping_message") or request.form.get("memo") or "").strip()
    postal_code = (request.form.get("postal_code") or "06000").strip()
    payment_method = request.form.get("payment_method") or "신용/체크카드"
    coupon_code = (request.form.get("coupon_code") or "").strip()

    # 이미 사용된 쿠폰인지 검증 (재사용 방지)
    used_coupons = _get_user_used_coupons(user_id)
    if coupon_code and coupon_code in used_coupons:
        coupon_code = ""

    # 3. 주문번호 생성 및 금액 산정
    shipping_fee, discount_amount, final_amount = _calculate_order_pricing(total_price, coupon_code)
    order_number = _generate_order_number()
    order_time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    inserted_order_id = None
    deducted_options = []

    try:
        # 4. orders 테이블에 INSERT
        if admin_client and _is_valid_uuid(user_id):
            order_row = {
                "order_number": order_number,
                "user_id": user_id,
                "status": "PAID",
                "total_amount": total_price,
                "discount_amount": discount_amount,
                "shipping_fee": shipping_fee,
                "final_amount": final_amount,
                "recipient_name": recipient_name,
                "recipient_phone": recipient_phone,
                "postal_code": postal_code,
                "shipping_address": shipping_address,
                "shipping_address_detail": shipping_address_detail,
                "delivery_request": delivery_request,
                "paid_at": now_iso
            }
            order_res = admin_client.table("orders").insert(order_row).execute()
            if not order_res or not order_res.data:
                raise RuntimeError("주문 테이블 생성 실패")
            inserted_order_id = order_res.data[0].get("id")

            # 5. order_items INSERT (상품명, 색상, 사이즈, 가격 스냅샷)
            order_items_rows = []
            for it in items:
                opt_color = it.get("color") or ""
                opt_size = it.get("size") or ""
                opt_label = it.get("option") or "기본"
                option_snapshot = f"{opt_color}/{opt_size}" if (opt_color and opt_size) else opt_label

                order_items_rows.append({
                    "order_id": inserted_order_id,
                    "product_id": it.get("id") if _is_valid_uuid(it.get("id")) else None,
                    "option_id": it.get("option_id") if _is_valid_uuid(it.get("option_id")) else None,
                    "product_name": it.get("name") or "상품",
                    "option_name": option_snapshot,
                    "price": it.get("price", 0),
                    "quantity": it.get("quantity", 1),
                    "subtotal": it.get("subtotal", 0)
                })

            if order_items_rows:
                items_res = admin_client.table("order_items").insert(order_items_rows).execute()
                if not items_res or not items_res.data:
                    raise RuntimeError("주문 상세 아이템 생성 실패")

            # 6. product_options.stock 조건부 차감
            for it in items:
                opt_id = it.get("option_id")
                qty = int(it.get("quantity", 1))
                if opt_id and _is_valid_uuid(opt_id):
                    cur_res = (
                        admin_client.table("product_options")
                        .select("stock, stock_quantity")
                        .eq("id", opt_id)
                        .maybe_single()
                        .execute()
                    )
                    if not cur_res or not cur_res.data:
                        raise ValueError("방금 재고가 소진되었습니다")

                    cur_stock = int(cur_res.data.get("stock") if cur_res.data.get("stock") is not None else cur_res.data.get("stock_quantity", 0) or 0)
                    if cur_stock < qty:
                        raise ValueError("방금 재고가 소진되었습니다")

                    new_stock = cur_stock - qty

                    update_res = (
                        admin_client.table("product_options")
                        .update({"stock": new_stock, "stock_quantity": new_stock})
                        .eq("id", opt_id)
                        .gte("stock", qty)
                        .execute()
                    )

                    if not update_res or not update_res.data or len(update_res.data) == 0:
                        raise ValueError("방금 재고가 소진되었습니다")

                    deducted_options.append((opt_id, qty))

            # 7. carts 아이템 DELETE
            admin_client.table("carts").delete().eq("user_id", user_id).execute()

        else:
            inserted_order_id = f"test-{order_number}"

    except ValueError as ve:
        err_msg = str(ve)
        print(f"[주문 처리 중 롤백 발생] {err_msg}", file=sys.stderr)
        _rollback_order(admin_client, inserted_order_id, deducted_options)
        flash("방금 재고가 소진되었습니다", "danger")
        return redirect(url_for("main.cart_page"))

    except Exception as ex:
        print(f"[주문 생성 오류] {ex}", file=sys.stderr)
        _rollback_order(admin_client, inserted_order_id, deducted_options)
        flash("주문 처리 중 오류가 발생했습니다. 다시 시도해주세요.", "danger")
        return redirect(url_for("main.checkout_page"))

    # 세션 장바구니 비우기 및 주문 정보 저장
    session["cart"] = {}
    order_info = {
        "id": inserted_order_id,
        "order_id": order_number,
        "order_number": order_number,
        "created_at": order_time_str,
        "buyer_name": recipient_name,
        "buyer_phone": recipient_phone,
        "address": shipping_address,
        "address_detail": shipping_address_detail,
        "delivery_request": delivery_request,
        "payment_method": payment_method,
        "coupon_code": coupon_code,
        "total_price": total_price,
        "discount_amount": discount_amount,
        "shipping_fee": shipping_fee,
        "final_amount": final_amount,
        "item_count": sum(int(it.get("quantity", 1)) for it in items),
        "items": items
    }
    session["last_order"] = order_info
    session.modified = True

    # 결제에 사용된 쿠폰은 소진 처리
    if coupon_code:
        _mark_coupon_as_used(coupon_code, user_id)

    # 8. /order/complete/<order_id> 리다이렉트
    return redirect(url_for("main.order_complete", order_id=inserted_order_id or order_number))


def _format_order_view(order_data: dict, is_session: bool = False) -> dict:
    """DB 또는 세션의 주문 데이터를 템플릿 렌더링용 딕셔너리로 일관되게 변환"""
    created_dt = order_data.get("created_at") or ""
    created_formatted = created_dt.replace("T", " ")[:19] if ("T" in created_dt) else created_dt

    order_items = []
    items_raw = order_data.get("order_items") or order_data.get("items") or []
    for item in items_raw:
        price_val = int(item.get("price") or 0)
        subtotal_val = int(item.get("subtotal") or 0)
        prod_name = item.get("product_name") or item.get("name") or "상품"
        pid = item.get("product_id") or item.get("id")
        thumbnail_url = item.get("thumbnail_url") or get_product_thumbnail(prod_name, pid)

        order_items.append({
            "id": item.get("id"),
            "product_id": pid,
            "product_name": prod_name,
            "option_name": item.get("option_name") or item.get("option") or "기본",
            "price": price_val,
            "price_formatted": item.get("price_formatted") or f"{price_val:,}원",
            "quantity": int(item.get("quantity") or 1),
            "subtotal": subtotal_val,
            "subtotal_formatted": item.get("subtotal_formatted") or f"{subtotal_val:,}원",
            "thumbnail_url": thumbnail_url
        })

    total_amount = int(order_data.get("total_amount") or order_data.get("total_price") or 0)
    discount_amount = int(order_data.get("discount_amount") or 0)
    shipping_fee = int(order_data.get("shipping_fee") or 0)
    final_amount = int(order_data.get("final_amount") or 0)
    order_num = order_data.get("order_number") or order_data.get("order_id")

    return {
        "id": order_data.get("id"),
        "order_id": order_num,
        "order_number": order_num,
        "created_at": created_formatted,
        "buyer_name": order_data.get("buyer_name") or order_data.get("recipient_name"),
        "buyer_phone": order_data.get("buyer_phone") or order_data.get("recipient_phone"),
        "address": order_data.get("address") or order_data.get("shipping_address"),
        "address_detail": order_data.get("address_detail") or order_data.get("shipping_address_detail") or "",
        "delivery_request": order_data.get("delivery_request") or "",
        "payment_method": order_data.get("payment_method") or "신용/체크카드",
        "coupon_code": order_data.get("coupon_code") or "",
        "total_amount": total_amount,
        "total_price": total_amount,
        "total_amount_formatted": f"{total_amount:,}원",
        "discount_amount": discount_amount,
        "discount_amount_formatted": f"{discount_amount:,}원",
        "shipping_fee": shipping_fee,
        "shipping_fee_formatted": f"{shipping_fee:,}원" if shipping_fee > 0 else "무료배송",
        "final_amount": final_amount,
        "final_amount_formatted": f"{final_amount:,}원",
        "order_items": order_items,
        "items": order_items,
        "items_count": len(order_items)
    }


@main_bp.route("/order/complete/<order_id>", methods=["GET"])
@login_required
def order_complete(order_id):
    """
    [GET /order/complete/<order_id>]
    - 주문 완료 결과 화면 표시
    - 본인 주문이 맞는지 엄격히 확인 (다른 사용자의 order_id 접근 차단)
    - 주문번호, 배송지, 주문 상품 목록, 결제 금액 표시
    - 마이페이지로 / 쇼핑 계속하기 버튼 제공
    """
    user_id = session.get("user_id")
    if not user_id:
        flash("로그인이 필요한 서비스입니다.", "error")
        return redirect(url_for("auth.login"))

    admin_client = get_admin_client() or supabase
    order_info = None

    # 1. DB에서 해당 order_id / order_number 조회
    if admin_client and _is_valid_uuid(user_id):
        try:
            base_query = admin_client.table("orders").select("*, order_items(*)")
            if _is_valid_uuid(order_id):
                base_query = base_query.eq("id", order_id)
            else:
                base_query = base_query.eq("order_number", order_id)

            res = base_query.maybe_single().execute()
            if res and res.data:
                o = res.data
                # 타인 주문 접근 차단
                if str(o.get("user_id")) != str(user_id):
                    flash("다른 사용자의 주문 정보에는 접근할 수 없습니다.", "danger")
                    return redirect(url_for("main.mypage"))

                order_info = _format_order_view(o)
        except Exception as e:
            print(f"[order_complete 조회 오류] {e}", file=sys.stderr)

    # 2. DB 조회 결과가 없는 경우 세션 last_order 확인 및 본인 검증
    if not order_info and session.get("last_order"):
        lo = session.get("last_order")
        if str(lo.get("id")) == str(order_id) or str(lo.get("order_id")) == str(order_id) or str(lo.get("order_number")) == str(order_id):
            order_info = _format_order_view(lo, is_session=True)

    if not order_info:
        flash("주문 정보를 찾을 수 없습니다.", "warning")
        return redirect(url_for("main.mypage"))

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
    user_id = session.get("user_id")
    
    # 로그인된 사용자: DB carts 테이블에서 조회
    if user_id:
        admin_client = get_admin_client() or supabase
        if admin_client:
            try:
                cart_res = (
                    admin_client.table("carts")
                    .select("quantity")
                    .eq("user_id", user_id)
                    .execute()
                )
                cart_count = sum(int(item.get("quantity", 0)) for item in (cart_res.data or []))
            except Exception as e:
                print(f"[api_counts DB 조회 오류] {e}", file=sys.stderr)
                cart_count = 0
        else:
            cart_count = 0
    else:
        # 비로그인: 세션 cart 사용
        cart = _get_cart()
        cart_count = sum(item.get("quantity", 1) for item in cart.values())
    
    wishlist = _get_wishlist()
    return jsonify({
        "cart_count": cart_count,
        "wishlist_count": len(wishlist)
    })


# -----------------------------------------------------------------------------
# 사용자 마이페이지 및 기존 라우트 호환
# -----------------------------------------------------------------------------

def _get_user_orders_for_mypage(admin_client, user_id: str) -> list:
    """마이페이지 표시용 사용자의 주문 내역 조회 및 가공"""
    orders_list = []
    status_map = {
        "PENDING": ("결제 대기", "secondary"),
        "PAID": ("결제 완료", "success"),
        "PREPARING": ("배송 준비중", "info"),
        "SHIPPED": ("배송중", "primary"),
        "DELIVERED": ("배송 완료", "dark"),
        "CANCELLED": ("주문 취소", "danger"),
        "REFUNDED": ("환불 완료", "warning"),
    }

    if admin_client and user_id and _is_valid_uuid(user_id):
        try:
            orders_res = (
                admin_client.table("orders")
                .select("*, order_items(*)")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .execute()
            )
            for o in (orders_res.data or []):
                created_dt = o.get("created_at") or ""
                created_formatted = created_dt.replace("T", " ")[:19] if created_dt else ""

                status_raw = o.get("status", "PAID")
                status_label, status_badge_class = status_map.get(status_raw, (status_raw, "secondary"))

                order_items_raw = o.get("order_items") or []
                order_items = []
                for item in order_items_raw:
                    price_val = int(item.get("price") or 0)
                    subtotal_val = int(item.get("subtotal") or 0)
                    prod_name = item.get("product_name") or "상품"
                    thumbnail_url = get_product_thumbnail(prod_name, item.get("product_id"))

                    order_items.append({
                        "id": item.get("id"),
                        "product_id": item.get("product_id"),
                        "product_name": prod_name,
                        "option_name": item.get("option_name") or "기본",
                        "price": price_val,
                        "price_formatted": f"{price_val:,}원",
                        "quantity": int(item.get("quantity") or 1),
                        "subtotal": subtotal_val,
                        "subtotal_formatted": f"{subtotal_val:,}원",
                        "thumbnail_url": thumbnail_url
                    })

                total_amount = int(o.get("total_amount") or 0)
                discount_amount = int(o.get("discount_amount") or 0)
                shipping_fee = int(o.get("shipping_fee") or 0)
                final_amount = int(o.get("final_amount") or 0)

                orders_list.append({
                    "id": o.get("id"),
                    "order_number": o.get("order_number"),
                    "status": status_raw,
                    "status_label": status_label,
                    "status_badge_class": status_badge_class,
                    "created_at": created_formatted,
                    "recipient_name": o.get("recipient_name"),
                    "recipient_phone": o.get("recipient_phone"),
                    "shipping_address": o.get("shipping_address"),
                    "shipping_address_detail": o.get("shipping_address_detail") or "",
                    "delivery_request": o.get("delivery_request") or "",
                    "total_amount": total_amount,
                    "total_amount_formatted": f"{total_amount:,}원",
                    "discount_amount": discount_amount,
                    "discount_amount_formatted": f"{discount_amount:,}원",
                    "shipping_fee": shipping_fee,
                    "shipping_fee_formatted": f"{shipping_fee:,}원" if shipping_fee > 0 else "무료배송",
                    "final_amount": final_amount,
                    "final_amount_formatted": f"{final_amount:,}원",
                    "order_items": order_items,
                    "items_count": len(order_items)
                })
        except Exception as e:
            print(f"[마이페이지 orders 조회 오류] {e}", file=sys.stderr)

    # DB에 아직 주문이 없거나 비회원/세션 기반일 경우 session['last_order'] 보완 연동
    if not orders_list and session.get("last_order"):
        lo = session.get("last_order")
        last_items = []
        for it in (lo.get("items") or []):
            last_items.append({
                "id": it.get("cart_id"),
                "product_id": it.get("id"),
                "product_name": it.get("name") or "상품",
                "option_name": it.get("option") or "기본",
                "price": it.get("price", 0),
                "price_formatted": it.get("price_formatted", f"{it.get('price', 0):,}원"),
                "quantity": it.get("quantity", 1),
                "subtotal": it.get("subtotal", 0),
                "subtotal_formatted": it.get("subtotal_formatted", f"{it.get('subtotal', 0):,}원"),
                "thumbnail_url": it.get("thumbnail_url")
            })

        orders_list.append({
            "id": lo.get("order_id"),
            "order_number": lo.get("order_id"),
            "status": "PAID",
            "status_label": "결제 완료",
            "status_badge_class": "success",
            "created_at": lo.get("created_at"),
            "recipient_name": lo.get("buyer_name"),
            "recipient_phone": lo.get("buyer_phone"),
            "shipping_address": lo.get("address"),
            "shipping_address_detail": lo.get("address_detail") or "",
            "delivery_request": lo.get("delivery_request") or "",
            "total_amount": lo.get("total_price", 0),
            "total_amount_formatted": f"{lo.get('total_price', 0):,}원",
            "discount_amount": lo.get("discount_amount", 0),
            "discount_amount_formatted": f"{lo.get('discount_amount', 0):,}원",
            "shipping_fee": lo.get("shipping_fee", 0),
            "shipping_fee_formatted": f"{lo.get('shipping_fee', 0):,}원" if lo.get("shipping_fee", 0) > 0 else "무료배송",
            "final_amount": lo.get("final_amount", 0),
            "final_amount_formatted": f"{lo.get('final_amount', 0):,}원",
            "order_items": last_items,
            "items_count": len(last_items)
        })

    return orders_list


@main_bp.route("/mypage", methods=["GET", "POST"])
@login_required
def mypage():
    """마이페이지 - 인증된 회원 정보 조회 및 수정 뼈대"""
    user_id = session.get("user_id")

    admin_client = get_admin_client() or supabase
    profile_data = {}
    auth_user = None

    # Supabase Auth 사용자 정보 조회
    if admin_client and user_id and _is_valid_uuid(user_id):
        try:
            user_resp = admin_client.auth.admin.get_user_by_id(user_id)
            if user_resp and user_resp.user:
                auth_user = user_resp.user
        except Exception as e:
            print(f"[마이페이지 Auth 조회 알림] {e}", file=sys.stderr)

    # Supabase profiles 테이블에서 회원 정보 조회
    if admin_client and user_id and _is_valid_uuid(user_id):
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

        profile_update = {
            "full_name": new_name,
            "phone": new_phone
        }
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

            try:
                updated_meta = {**user_meta, "full_name": new_name, "phone": new_phone, "address": new_address, "address_detail": new_address_detail}
                admin_client.auth.admin.update_user_by_id(user_id, {"user_metadata": updated_meta})
            except Exception as e:
                print(f"[Auth user_metadata 업데이트 오류] {e}", file=sys.stderr)

        if "user" in session and isinstance(session["user"], dict):
            session["user"]["name"] = new_name
            session.modified = True

        flash("회원 정보가 성공적으로 수정되었습니다.", "success")
        return redirect(url_for("main.mypage"))

    # 이메일/비밀번호 가입 사용자 여부 판별
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

    orders_list = _get_user_orders_for_mypage(admin_client, user_id)

    return render_template(
        "mypage.html",
        brand_name="VIBE-FASHION",
        profile=profile_view,
        orders=orders_list,
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
