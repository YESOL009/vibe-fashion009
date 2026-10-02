"""
관리자(Admin) 전용 라우트 블루프린트 모듈 (admin_routes.py)
- 관리자 로그인/로그아웃 (/admin/login, /admin/logout)
- 관리자 대시보드 (/admin/dashboard)
- KPI 지표 계산 (오늘/전일 주문수, 판매량, 매출액, 재고 상태)
- orders, order_items, products, product_options, profiles 테이블 결합
- 주문/판매 현황 검색/필터 (주문자, 상품명, 날짜, 상태)
- 시간대별 차트 데이터 (판매량 Line Chart, 매출액 Bar Chart)
- 엑셀(CSV) 다운로드 (/admin/orders/export)
"""

import os
import sys
import io
import csv
import datetime
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify,
    Response,
    abort
)
from dotenv import load_dotenv
from routes.admin_auth import (
    admin_required,
    is_admin_user,
    get_admin_supabase_client,
    get_anon_supabase_client
)

load_dotenv()

# 'admin' 블루프린트 생성 (url_prefix="/admin")
admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


# -----------------------------------------------------------------------------
# 1. 관리자 전용 로그인 / 로그아웃
# -----------------------------------------------------------------------------

@admin_bp.route("/login", methods=["GET", "POST"])
def admin_login():
    """
    [GET/POST /admin/login]
    - 관리자 전용 로그인 화면 및 인증 처리
    - profiles 테이블의 role='admin'인 사용자만 로그인 가능
    - 로그인 성공 시 /admin/dashboard 로 이동
    - 비관리자 접근 시 403 페이지 표시
    """
    # 이미 관리자로 로그인되어 있으면 대시보드로 이동
    if session.get("user_id") and session.get("role") == "admin":
        return redirect(url_for("admin.admin_dashboard"))

    error_msg = None

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        if not email or not password:
            error_msg = "이메일과 비밀번호를 모두 입력해주세요."
            return render_template("admin_login.html", error_msg=error_msg, brand_name="VIBE-FASHION")

        anon_client = get_anon_supabase_client()
        admin_client = get_admin_supabase_client() or anon_client

        if not anon_client:
            error_msg = "데이터베이스 서비스에 연결할 수 없습니다."
            return render_template("admin_login.html", error_msg=error_msg, brand_name="VIBE-FASHION")

        try:
            # 1. Supabase Auth 로그인 시도
            auth_res = anon_client.auth.sign_in_with_password({
                "email": email,
                "password": password
            })

            user = auth_res.user
            if not user:
                error_msg = "이메일 또는 비밀번호가 올바르지 않습니다."
                return render_template("admin_login.html", error_msg=error_msg, brand_name="VIBE-FASHION")

            # 2. profiles 테이블에서 role 컬럼 확인 (관리자 권한 여부)
            profile_res = (
                admin_client.table("profiles")
                .select("id, email, full_name, role")
                .eq("id", user.id)
                .maybe_single()
                .execute()
            )

            profile_data = profile_res.data if profile_res else None
            role = (profile_data.get("role") if profile_data else "customer") or "customer"

            # 3. 비관리자(role != 'admin') 접근 시 403 페이지 표시
            if role != "admin":
                # 일반 회원 로그아웃 처리
                try:
                    anon_client.auth.sign_out()
                except Exception:
                    pass
                # 비관리자는 403 Forbidden 렌더링
                return render_template("403.html", brand_name="VIBE-FASHION"), 403

            # 4. 관리자 로그인 성공: 세션에 관리자 정보 저장
            session["user_id"] = user.id
            session["role"] = "admin"
            admin_name = (profile_data.get("full_name") if profile_data else None) or email.split("@")[0]
            session["user"] = {
                "id": user.id,
                "email": email,
                "name": admin_name,
                "role": "admin"
            }
            session.modified = True

            flash(f"관리자({admin_name})님, 환영합니다.", "success")
            next_url = request.args.get("next")
            return redirect(next_url or url_for("admin.admin_dashboard"))

        except Exception as e:
            print(f"[관리자 로그인 오류] {e}", file=sys.stderr)
            error_msg = "이메일 또는 비밀번호가 올바르지 않습니다."
            return render_template("admin_login.html", error_msg=error_msg, brand_name="VIBE-FASHION")

    return render_template("admin_login.html", error_msg=error_msg, brand_name="VIBE-FASHION")


@admin_bp.route("/logout", methods=["GET", "POST"])
def admin_logout():
    """[GET /admin/logout] 관리자 로그아웃"""
    session.pop("user_id", None)
    session.pop("role", None)
    session.pop("user", None)
    session.modified = True

    try:
        anon_client = get_anon_supabase_client()
        if anon_client:
            anon_client.auth.sign_out()
    except Exception:
        pass

    flash("관리자 로그아웃되었습니다.", "info")
    return redirect(url_for("admin.admin_login"))


# -----------------------------------------------------------------------------
# 2. 관리자 대시보드 (/admin/dashboard)
# -----------------------------------------------------------------------------

def _parse_datetime(dt_str: str):
    """ISO 날짜 문자열을 datetime 객체로 파싱"""
    if not dt_str:
        return None
    try:
        clean_str = dt_str.replace("Z", "+00:00")
        if "+" in clean_str:
            base, tz = clean_str.split("+", 1)
            # 마이크로초 절삭
            if "." in base:
                base = base[:26]
            clean_str = f"{base}+{tz}"
        return datetime.datetime.fromisoformat(clean_str)
    except Exception:
        try:
            return datetime.datetime.strptime(dt_str[:19], "%Y-%m-%dT%H:%M:%S")
        except Exception:
            return None


@admin_bp.route("/dashboard", methods=["GET"])
@admin_required
def admin_dashboard():
    """
    [GET /admin/dashboard]
    - 관리자 대시보드 메인 화면
    - 상단 KPI 카드 6개 (오늘 기준 건수, 수량, 매출액, 판매중/품절/재고부족 상품수 및 전일대비 증가율)
    - 주문/판매 현황 테이블 (검색/필터 지원)
    - 시간대별 차트 데이터 (Line Chart, Bar Chart)
    """
    admin_client = get_admin_supabase_client() or get_anon_supabase_client()
    if not admin_client:
        flash("데이터베이스 연결에 실패했습니다.", "danger")
        return render_template("admin_dashboard.html", brand_name="VIBE-FASHION")

    # 검색 및 필터 파라미터 수신
    search_buyer = (request.args.get("buyer") or "").strip()
    search_product = (request.args.get("product") or "").strip()
    filter_date = (request.args.get("date") or "").strip()  # 예: 'YYYY-MM-DD' 또는 'all'
    filter_status = (request.args.get("status") or "ALL").strip().upper()

    # 기준 시각 계산 (한국 시간 UTC+9 기준)
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    kst_now = now_utc + datetime.timedelta(hours=9)
    today_str = kst_now.strftime("%Y-%m-%d")
    yesterday_str = (kst_now - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    # 기본 날짜 필터는 오늘('YYYY-MM-DD')로 설정하지 않고 전체 또는 전달받은 날짜
    # 필터 날짜가 없으면 전체(또는 검색조건에 따름)

    # 1. orders, order_items, products, product_options, profiles 전체 조회
    try:
        orders_data = admin_client.table("orders").select("*").order("created_at", desc=True).execute().data or []
    except Exception as e:
        print(f"[orders 조회 오류] {e}", file=sys.stderr)
        orders_data = []

    try:
        order_items_data = admin_client.table("order_items").select("*").execute().data or []
    except Exception as e:
        print(f"[order_items 조회 오류] {e}", file=sys.stderr)
        order_items_data = []

    try:
        products_data = admin_client.table("products").select("id, name, price, is_active").execute().data or []
    except Exception as e:
        print(f"[products 조회 오류] {e}", file=sys.stderr)
        products_data = []

    try:
        options_data = admin_client.table("product_options").select("id, product_id, color, size, stock, stock_quantity").execute().data or []
    except Exception as e:
        print(f"[product_options 조회 오류] {e}", file=sys.stderr)
        options_data = []

    try:
        profiles_data = admin_client.table("profiles").select("id, full_name, email, phone").execute().data or []
    except Exception as e:
        print(f"[profiles 조회 오류] {e}", file=sys.stderr)
        profiles_data = []

    # 2. 빠른 매핑 딕셔너리 생성
    orders_map = {str(o.get("id")): o for o in orders_data}
    profiles_map = {str(p.get("id")): p for p in profiles_data}
    products_map = {str(pr.get("id")): pr for pr in products_data}
    options_map = {str(opt.get("id")): opt for opt in options_data}

    # 3. 오늘(today) 및 전일(yesterday) 실적 집계 (KPI용)
    today_order_ids = set()
    yesterday_order_ids = set()
    today_revenue = 0
    yesterday_revenue = 0

    # 시간대별 집계 배열 (0시~23시)
    hourly_item_qty = [0] * 24
    hourly_revenue = [0] * 24

    # 상품별 오늘 판매량 및 매출액 집계용 dict: {product_name: {'qty': 0, 'revenue': 0}}
    product_today_stats = {}

    for o in orders_data:
        dt = _parse_datetime(o.get("created_at"))
        if not dt:
            continue
        # 한국시간 변환 (dt가 aware면 변환, naive면 9시간 가산)
        if dt.tzinfo is not None:
            dt_kst = dt.astimezone(datetime.timezone(datetime.timedelta(hours=9)))
        else:
            dt_kst = dt + datetime.timedelta(hours=9)

        order_day = dt_kst.strftime("%Y-%m-%d")
        order_status = (o.get("status") or "").upper()
        # 유효 결제 주문만 매출 집계
        is_paid_order = order_status in ("PAID", "PREPARING", "SHIPPED", "DELIVERED")

        if order_day == today_str:
            today_order_ids.add(str(o.get("id")))
            if is_paid_order:
                amount = int(o.get("final_amount") or o.get("total_amount") or 0)
                today_revenue += amount
                hour = dt_kst.hour
                if 0 <= hour < 24:
                    hourly_revenue[hour] += amount

        elif order_day == yesterday_str:
            yesterday_order_ids.add(str(o.get("id")))
            if is_paid_order:
                yesterday_revenue += int(o.get("final_amount") or o.get("total_amount") or 0)

    today_sales_qty = 0
    yesterday_sales_qty = 0

    for it in order_items_data:
        oid = str(it.get("order_id"))
        qty = int(it.get("quantity") or 0)
        subtotal = int(it.get("subtotal") or 0)
        pname = it.get("product_name") or "상품"

        if oid in today_order_ids:
            today_sales_qty += qty
            # 시간대별 판매량 집계
            order_obj = orders_map.get(oid)
            if order_obj:
                dt = _parse_datetime(order_obj.get("created_at"))
                if dt:
                    dt_kst = dt.astimezone(datetime.timezone(datetime.timedelta(hours=9))) if dt.tzinfo else dt + datetime.timedelta(hours=9)
                    hour = dt_kst.hour
                    if 0 <= hour < 24:
                        hourly_item_qty[hour] += qty

            # 상품별 오늘 판매량/매출 합산
            if pname not in product_today_stats:
                product_today_stats[pname] = {"qty": 0, "revenue": 0}
            product_today_stats[pname]["qty"] += qty
            product_today_stats[pname]["revenue"] += subtotal

        elif oid in yesterday_order_ids:
            yesterday_sales_qty += qty

    # 전일 대비 증가율 계산 헬퍼
    def calc_growth_rate(today_val, yest_val):
        if yest_val == 0:
            return "+100%" if today_val > 0 else "0%"
        diff = ((today_val - yest_val) / yest_val) * 100
        sign = "+" if diff > 0 else ""
        return f"{sign}{diff:.1f}%"

    today_order_count = len(today_order_ids)
    yesterday_order_count = len(yesterday_order_ids)

    kpi = {
        "today_orders": today_order_count,
        "today_orders_growth": calc_growth_rate(today_order_count, yesterday_order_count),
        "today_qty": today_sales_qty,
        "today_qty_growth": calc_growth_rate(today_sales_qty, yesterday_sales_qty),
        "today_sales": today_revenue,
        "today_sales_formatted": f"{today_revenue:,}원",
        "today_sales_growth": calc_growth_rate(today_revenue, yesterday_revenue),
        "active_products": sum(1 for pr in products_data if pr.get("is_active", True)),
        "out_of_stock_products": sum(
            1 for opt in options_data
            if (opt.get("stock") if opt.get("stock") is not None else opt.get("stock_quantity", 0)) == 0
        ),
        "low_stock_products": sum(
            1 for opt in options_data
            if 1 <= (opt.get("stock") if opt.get("stock") is not None else opt.get("stock_quantity", 0)) <= 10
        ),
    }

    # 4. 주문/판매 현황 테이블 결합 (orders + order_items + products + product_options + profiles)
    table_rows = []

    for it in order_items_data:
        oid = str(it.get("order_id"))
        order = orders_map.get(oid)
        if not order:
            continue

        # 주문 일시 파싱
        dt = _parse_datetime(order.get("created_at"))
        dt_kst_str = ""
        dt_kst_day = ""
        if dt:
            dt_kst = dt.astimezone(datetime.timezone(datetime.timedelta(hours=9))) if dt.tzinfo else dt + datetime.timedelta(hours=9)
            dt_kst_str = dt_kst.strftime("%Y-%m-%d %H:%M:%S")
            dt_kst_day = dt_kst.strftime("%Y-%m-%d")

        # 주문자 정보 (profiles 매핑 -> 없으면 orders.recipient_name)
        uid = str(order.get("user_id") or "")
        profile = profiles_map.get(uid) or {}
        buyer_name = profile.get("full_name") or order.get("recipient_name") or "구매자"
        buyer_phone = order.get("recipient_phone") or profile.get("phone") or "-"

        # 수령인 정보 (orders 테이블 기준)
        recipient_name = order.get("recipient_name") or buyer_name
        recipient_phone = order.get("recipient_phone") or buyer_phone

        # 상품명 및 옵션 정보
        prod_name = it.get("product_name") or "상품"
        opt_id = str(it.get("option_id") or "")
        option_obj = options_map.get(opt_id) or {}

        # 색상/사이즈 추출
        color = option_obj.get("color") or ""
        size = option_obj.get("size") or ""
        if not color or not size:
            raw_opt = it.get("option_name") or ""
            if "/" in raw_opt:
                parts = raw_opt.split("/", 1)
                color = color or parts[0].strip()
                size = size or parts[1].strip()
            else:
                color = color or raw_opt or "FREE"
                size = size or "FREE"

        # 현재 남은 재고
        stock_val = (
            option_obj.get("stock")
            if option_obj.get("stock") is not None
            else option_obj.get("stock_quantity", 0)
        )
        current_stock = int(stock_val or 0)

        # 재고 상태 색상 및 배지 텍스트
        if current_stock == 0:
            stock_badge_class = "danger"
            stock_status_text = "품절"
        elif current_stock <= 10:
            stock_badge_class = "warning text-dark"
            stock_status_text = "품절임박"
        else:
            stock_badge_class = "success"
            stock_status_text = "여유"

        # 주문 수량 및 금액
        qty = int(it.get("quantity") or 1)
        price = int(it.get("price") or 0)
        subtotal = int(it.get("subtotal") or (price * qty))

        # 상품 기준 오늘 누적 판매량 및 누적 매출액
        today_stats = product_today_stats.get(prod_name, {"qty": 0, "revenue": 0})

        # 주문 상태 및 배지 색상
        order_status = (order.get("status") or "PAID").upper()
        status_map = {
            "PAID": ("결제완료", "success"),
            "PREPARING": ("배송준비", "info text-dark"),
            "SHIPPED": ("배송중", "primary"),
            "DELIVERED": ("배송완료", "secondary"),
            "CANCELLED": ("주문취소", "danger"),
            "REFUNDED": ("환불완료", "dark"),
            "PENDING": ("결제대기", "warning text-dark")
        }
        status_label, status_badge_class = status_map.get(order_status, (order_status, "secondary"))

        # 필터링 조건 검사 (주문자명 또는 수령인명 검색 가능)
        if search_buyer and (search_buyer.lower() not in buyer_name.lower() and search_buyer.lower() not in recipient_name.lower()):
            continue
        if search_product and search_product.lower() not in prod_name.lower():
            continue
        if filter_date and filter_date != "all":
            if dt_kst_day != filter_date:
                continue
        if filter_status and filter_status != "ALL":
            if order_status != filter_status:
                continue

        table_rows.append({
            "order_id": str(order.get("id")),
            "order_number": order.get("order_number") or str(order.get("id"))[:8],
            "order_date": dt_kst_str,
            "order_date_day": dt_kst_day,
            "buyer_name": buyer_name,
            "buyer_phone": buyer_phone,
            "recipient_name": recipient_name,
            "recipient_phone": recipient_phone,
            "shipping_address": f"{order.get('shipping_address') or ''} {order.get('shipping_address_detail') or ''}".strip(),
            "product_name": prod_name,
            "option_id": opt_id,
            "color": color,
            "size": size,
            "quantity": qty,
            "price": price,
            "price_formatted": f"{price:,}원",
            "subtotal": subtotal,
            "subtotal_formatted": f"{subtotal:,}원",
            "current_stock": current_stock,
            "stock_badge_class": stock_badge_class,
            "stock_status_text": stock_status_text,
            "today_product_sales_qty": today_stats["qty"],
            "today_product_sales_revenue": today_stats["revenue"],
            "today_product_sales_revenue_formatted": f"{today_stats['revenue']:,}원",
            "status": order_status,
            "status_label": status_label,
            "status_badge_class": status_badge_class,
        })

    # 최신 주문 일시 순 정렬
    table_rows.sort(key=lambda r: r["order_date"], reverse=True)

    # 전체 상품 옵션별 재고 현황 리스트 (재고 관리 모달용)
    all_stock_items = []
    for opt in options_data:
        pid = str(opt.get("product_id") or "")
        pr = products_map.get(pid) or {}
        st_val = opt.get("stock") if opt.get("stock") is not None else opt.get("stock_quantity", 0)
        st_int = int(st_val or 0)
        c_val = opt.get("color") or ""
        s_val = opt.get("size") or ""
        if not c_val and not s_val:
            raw_v = opt.get("option_value") or opt.get("option_name") or "기본"
            c_val = raw_v
            s_val = "-"

        if st_int == 0:
            badge_cls = "danger"
            st_text = "품절"
        elif st_int <= 10:
            badge_cls = "warning text-dark"
            st_text = "품절임박"
        else:
            badge_cls = "success"
            st_text = "여유"

        all_stock_items.append({
            "option_id": str(opt.get("id")),
            "product_id": pid,
            "product_name": pr.get("name", "상품"),
            "color": c_val,
            "size": s_val,
            "stock": st_int,
            "badge_class": badge_cls,
            "status_text": st_text,
            "is_active": pr.get("is_active", True)
        })

    all_stock_items.sort(key=lambda x: (x["product_name"], x["color"], x["size"]))

    # 5. 사용자(회원) 관리 목록 가공 (주문 통계 결합)
    # 각 사용자별 총 주문 건수 및 실 결제 총액 계산
    user_order_stats = {}
    for o in orders_data:
        uid = str(o.get("user_id") or "")
        if not uid:
            continue
        if uid not in user_order_stats:
            user_order_stats[uid] = {"order_count": 0, "total_spent": 0}
        user_order_stats[uid]["order_count"] += 1
        if (o.get("status") or "").upper() in ("PAID", "PREPARING", "SHIPPED", "DELIVERED"):
            user_order_stats[uid]["total_spent"] += int(o.get("final_amount") or o.get("total_amount") or 0)

    users_list = []
    grade_badge_map = {
        "VIP": "danger",
        "GOLD": "warning text-dark",
        "SILVER": "secondary",
        "BRONZE": "dark"
    }

    for p in profiles_data:
        p_id = str(p.get("id"))
        p_email = p.get("email") or "-"
        p_name = p.get("full_name") or p_email.split("@")[0] or "회원"
        p_role = (p.get("role") or "customer").lower()
        p_grade = (p.get("grade") or "BRONZE").upper()
        p_points = int(p.get("points") or 0)
        p_phone = p.get("phone") or "-"

        stats = user_order_stats.get(p_id, {"order_count": 0, "total_spent": 0})
        # profiles 테이블의 total_spent 또는 계산된 주문 실 결제액
        db_spent = int(p.get("total_spent") or 0)
        actual_spent = max(db_spent, stats["total_spent"])

        p_created = _parse_datetime(p.get("created_at"))
        created_str = p_created.strftime("%Y-%m-%d") if p_created else "-"

        users_list.append({
            "id": p_id,
            "email": p_email,
            "name": p_name,
            "phone": p_phone,
            "role": p_role,
            "role_badge_class": "warning text-dark" if p_role == "admin" else ("info text-dark" if p_role == "seller" else "light text-dark border"),
            "grade": p_grade,
            "grade_badge_class": grade_badge_map.get(p_grade, "secondary"),
            "points": p_points,
            "points_formatted": f"{p_points:,}P",
            "total_spent": actual_spent,
            "total_spent_formatted": f"{actual_spent:,}원",
            "order_count": stats["order_count"],
            "created_at": created_str
        })

    # 최신 가입 순 또는 이름 순 정렬
    users_list.sort(key=lambda u: u["created_at"], reverse=True)

    # 차트용 라벨(0시~23시)
    chart_labels = [f"{h}시" for h in range(24)]

    return render_template(
        "admin_dashboard.html",
        brand_name="VIBE-FASHION",
        kpi=kpi,
        rows=table_rows,
        all_stock_items=all_stock_items,
        users_list=users_list,
        total_rows=len(table_rows),
        total_users=len(users_list),
        today_str=today_str,
        # 필터 상태 유지용
        search_buyer=search_buyer,
        search_product=search_product,
        filter_date=filter_date,
        filter_status=filter_status,
        # 차트 데이터 전달
        chart_labels=chart_labels,
        chart_hourly_qty=hourly_item_qty,
        chart_hourly_revenue=hourly_revenue
    )


# -----------------------------------------------------------------------------
# 3. 엑셀(CSV) 다운로드 라우트 (/admin/orders/export)
# -----------------------------------------------------------------------------

@admin_bp.route("/orders/export", methods=["GET"])
@admin_required
def export_orders_csv():
    """
    [GET /admin/orders/export]
    - 현재 필터 조건(검색어, 날짜, 상태)이 적용된 주문/판매 현황을 CSV 파일로 다운로드
    - MS 엑셀에서 한글이 깨지지 않도록 UTF-8 with BOM 인코딩 적용
    """
    admin_client = get_admin_supabase_client() or get_anon_supabase_client()
    if not admin_client:
        return Response("DB 연결 오류", status=500)

    # 필터 파라미터 수신
    search_buyer = (request.args.get("buyer") or "").strip().lower()
    search_product = (request.args.get("product") or "").strip().lower()
    filter_date = (request.args.get("date") or "").strip()
    filter_status = (request.args.get("status") or "ALL").strip().upper()

    try:
        orders_data = admin_client.table("orders").select("*").order("created_at", desc=True).execute().data or []
        order_items_data = admin_client.table("order_items").select("*").execute().data or []
        options_data = admin_client.table("product_options").select("*").execute().data or []
        profiles_data = admin_client.table("profiles").select("*").execute().data or []
    except Exception as e:
        print(f"[CSV 내보내기 조회 오류] {e}", file=sys.stderr)
        return Response(f"조회 실패: {e}", status=500)

    orders_map = {str(o.get("id")): o for o in orders_data}
    profiles_map = {str(p.get("id")): p for p in profiles_data}
    options_map = {str(opt.get("id")): opt for opt in options_data}

    # CSV 데이터 생성 (In-Memory 문자열 버퍼 + UTF-8-SIG)
    output = io.StringIO()
    writer = csv.writer(output)

    # 헤더 작성
    headers = [
        "주문번호",
        "주문일시",
        "주문자명",
        "수령인",
        "연락처",
        "주문상품",
        "색상",
        "사이즈",
        "주문수량",
        "상품가격",
        "주문금액",
        "현재재고",
        "주문상태"
    ]
    writer.writerow(headers)

    for it in order_items_data:
        oid = str(it.get("order_id"))
        order = orders_map.get(oid)
        if not order:
            continue

        dt = _parse_datetime(order.get("created_at"))
        dt_str = ""
        dt_day = ""
        if dt:
            dt_kst = dt.astimezone(datetime.timezone(datetime.timedelta(hours=9))) if dt.tzinfo else dt + datetime.timedelta(hours=9)
            dt_str = dt_kst.strftime("%Y-%m-%d %H:%M:%S")
            dt_day = dt_kst.strftime("%Y-%m-%d")

        uid = str(order.get("user_id") or "")
        profile = profiles_map.get(uid) or {}
        buyer_name = profile.get("full_name") or order.get("recipient_name") or "구매자"
        buyer_phone = order.get("recipient_phone") or profile.get("phone") or "-"
        recipient_name = order.get("recipient_name") or buyer_name

        prod_name = it.get("product_name") or "상품"
        opt_id = str(it.get("option_id") or "")
        option_obj = options_map.get(opt_id) or {}

        color = option_obj.get("color") or ""
        size = option_obj.get("size") or ""
        if not color or not size:
            raw_opt = it.get("option_name") or ""
            if "/" in raw_opt:
                parts = raw_opt.split("/", 1)
                color = color or parts[0].strip()
                size = size or parts[1].strip()
            else:
                color = color or raw_opt or "FREE"
                size = size or "FREE"

        stock_val = (
            option_obj.get("stock")
            if option_obj.get("stock") is not None
            else option_obj.get("stock_quantity", 0)
        )
        current_stock = int(stock_val or 0)

        qty = int(it.get("quantity") or 1)
        price = int(it.get("price") or 0)
        subtotal = int(it.get("subtotal") or (price * qty))
        order_status = (order.get("status") or "PAID").upper()

        # 필터 검사
        if search_buyer and (search_buyer not in buyer_name.lower() and search_buyer not in recipient_name.lower()):
            continue
        if search_product and search_product not in prod_name.lower():
            continue
        if filter_date and filter_date != "all" and dt_day != filter_date:
            continue
        if filter_status and filter_status != "ALL" and order_status != filter_status:
            continue

        writer.writerow([
            order.get("order_number") or oid[:8],
            dt_str,
            buyer_name,
            recipient_name,
            buyer_phone,
            prod_name,
            color,
            size,
            qty,
            price,
            subtotal,
            current_stock,
            order_status
        ])

    csv_data = output.getvalue()
    # 엑셀 한글 깨짐 방지를 위해 UTF-8 BOM 인코딩 적용
    csv_bytes = csv_data.encode("utf-8-sig")

    filename = f"vibe_fashion_orders_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        csv_bytes,
        mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Type": "text/csv; charset=utf-8"
        }
    )


# -----------------------------------------------------------------------------
# 4. 차트용 시간대별 API (/admin/api/hourly-stats)
# -----------------------------------------------------------------------------

@admin_bp.route("/api/hourly-stats", methods=["GET"])
@admin_required
def api_hourly_stats():
    """
    [GET /admin/api/hourly-stats]
    - 오늘 시간대별 판매량 및 매출액 JSON 반환 (Chart.js 동적 갱신용)
    """
    admin_client = get_admin_supabase_client() or get_anon_supabase_client()
    if not admin_client:
        return jsonify({"success": False, "error": "DB 연결 오류"}), 500

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    kst_now = now_utc + datetime.timedelta(hours=9)
    today_str = kst_now.strftime("%Y-%m-%d")

    try:
        orders = admin_client.table("orders").select("id, status, created_at, final_amount, total_amount").execute().data or []
        items = admin_client.table("order_items").select("order_id, quantity").execute().data or []
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

    today_orders_map = {}
    hourly_revenue = [0] * 24
    for o in orders:
        dt = _parse_datetime(o.get("created_at"))
        if not dt:
            continue
        dt_kst = dt.astimezone(datetime.timezone(datetime.timedelta(hours=9))) if dt.tzinfo else dt + datetime.timedelta(hours=9)
        if dt_kst.strftime("%Y-%m-%d") == today_str:
            oid = str(o.get("id"))
            today_orders_map[oid] = dt_kst.hour
            if (o.get("status") or "").upper() in ("PAID", "PREPARING", "SHIPPED", "DELIVERED"):
                rev = int(o.get("final_amount") or o.get("total_amount") or 0)
                hourly_revenue[dt_kst.hour] += rev

    hourly_qty = [0] * 24
    for it in items:
        oid = str(it.get("order_id"))
        if oid in today_orders_map:
            h = today_orders_map[oid]
            hourly_qty[h] += int(it.get("quantity") or 0)

    return jsonify({
        "success": True,
        "date": today_str,
        "labels": [f"{h}시" for h in range(24)],
        "hourly_quantity": hourly_qty,
        "hourly_revenue": hourly_revenue
    })


# -----------------------------------------------------------------------------
# 5. 재고 수량 수정 API 및 라우트 (/admin/stock/update)
# -----------------------------------------------------------------------------

@admin_bp.route("/stock/update", methods=["POST"])
@admin_bp.route("/api/stock/update", methods=["POST"])
@admin_required
def update_stock():
    """
    [POST /admin/stock/update, POST /admin/api/stock/update]
    - 관리자가 특정 상품 옵션의 재고 수량을 수정
    - JSON 및 Form 요청 모두 지원
    - 0 이상의 정수만 허용
    - product_options 테이블의 stock 및 stock_quantity 동시 갱신
    """
    data = request.get_json(silent=True) or request.form.to_dict()
    option_id = str(data.get("option_id") or "").strip()
    raw_stock = data.get("stock")
    if raw_stock is None:
        raw_stock = data.get("new_stock")

    if not option_id:
        if request.is_json:
            return jsonify({"success": False, "error": "옵션 ID가 전달되지 않았습니다."}), 400
        flash("옵션 ID가 유효하지 않습니다.", "danger")
        return redirect(request.referrer or url_for("admin.admin_dashboard"))

    try:
        new_stock = int(raw_stock)
        if new_stock < 0:
            raise ValueError()
    except (ValueError, TypeError):
        if request.is_json:
            return jsonify({"success": False, "error": "재고 수량은 0 이상의 정수여야 합니다."}), 400
        flash("재고 수량은 0 이상의 정수여야 합니다.", "danger")
        return redirect(request.referrer or url_for("admin.admin_dashboard"))

    admin_client = get_admin_supabase_client() or get_anon_supabase_client()
    if not admin_client:
        if request.is_json:
            return jsonify({"success": False, "error": "데이터베이스 연결에 실패했습니다."}), 500
        flash("데이터베이스 연결에 실패했습니다.", "danger")
        return redirect(request.referrer or url_for("admin.admin_dashboard"))

    try:
        # product_options 테이블 stock & stock_quantity 동시 갱신
        update_res = (
            admin_client.table("product_options")
            .update({
                "stock": new_stock,
                "stock_quantity": new_stock
            })
            .eq("id", option_id)
            .execute()
        )

        if not update_res or not update_res.data:
            if request.is_json:
                return jsonify({"success": False, "error": "해당 옵션을 찾을 수 없습니다."}), 404
            flash("해당 옵션을 찾을 수 없습니다.", "danger")
            return redirect(request.referrer or url_for("admin.admin_dashboard"))

        updated_opt = update_res.data[0]
        color = updated_opt.get("color") or ""
        size = updated_opt.get("size") or ""
        opt_info = f" ({color}/{size})" if color or size else ""

        # 재고 상태 색상/텍스트 판정
        if new_stock == 0:
            badge_class = "danger"
            status_text = "품절"
        elif new_stock <= 10:
            badge_class = "warning text-dark"
            status_text = "품절임박"
        else:
            badge_class = "success"
            status_text = "여유"

        if request.is_json:
            return jsonify({
                "success": True,
                "message": f"재고가 {new_stock}개로 성공적으로 수정되었습니다.{opt_info}",
                "option_id": option_id,
                "new_stock": new_stock,
                "badge_class": badge_class,
                "status_text": status_text
            })

        flash(f"재고가 {new_stock}개로 성공적으로 수정되었습니다.{opt_info}", "success")
        return redirect(request.referrer or url_for("admin.admin_dashboard"))

    except Exception as e:
        print(f"[재고 수정 오류] {e}", file=sys.stderr)
        if request.is_json:
            return jsonify({"success": False, "error": f"재고 수정 중 오류가 발생했습니다: {str(e)}"}), 500
        flash("재고 수정 중 오류가 발생했습니다.", "danger")
        return redirect(request.referrer or url_for("admin.admin_dashboard"))


# -----------------------------------------------------------------------------
# 6. 사용자(회원) 관리 API 및 라우트 (/admin/users/update)
# -----------------------------------------------------------------------------

@admin_bp.route("/users/update", methods=["POST"])
@admin_bp.route("/api/users/update", methods=["POST"])
@admin_required
def update_user_profile():
    """
    [POST /admin/users/update, POST /admin/api/users/update]
    - 관리자가 특정 회원의 등급(grade), 역할(role), 적립금(points), 이름, 연락처 수정
    - JSON 및 Form 요청 모두 지원
    - profiles 테이블 업데이트 및 Supabase Auth user_metadata 동기화
    """
    data = request.get_json(silent=True) or request.form.to_dict()
    target_user_id = str(data.get("user_id") or "").strip()

    if not target_user_id:
        if request.is_json:
            return jsonify({"success": False, "error": "회원 ID가 전달되지 않았습니다."}), 400
        flash("회원 ID가 유효하지 않습니다.", "danger")
        return redirect(request.referrer or url_for("admin.admin_dashboard"))

    new_role = data.get("role")
    new_grade = data.get("grade")
    new_points = data.get("points")
    new_name = data.get("full_name")
    new_phone = data.get("phone")

    # 유효성 검증
    valid_roles = ("customer", "admin", "seller")
    valid_grades = ("BRONZE", "SILVER", "GOLD", "VIP")

    update_payload = {}
    if new_role:
        new_role = new_role.strip().lower()
        if new_role not in valid_roles:
            err = f"역할은 {', '.join(valid_roles)} 중 하나여야 합니다."
            return (jsonify({"success": False, "error": err}), 400) if request.is_json else (flash(err, "danger"), redirect(request.referrer or url_for("admin.admin_dashboard")))[1]
        update_payload["role"] = new_role

    if new_grade:
        new_grade = new_grade.strip().upper()
        if new_grade not in valid_grades:
            err = f"등급은 {', '.join(valid_grades)} 중 하나여야 합니다."
            return (jsonify({"success": False, "error": err}), 400) if request.is_json else (flash(err, "danger"), redirect(request.referrer or url_for("admin.admin_dashboard")))[1]
        update_payload["grade"] = new_grade

    if new_points is not None and str(new_points).strip() != "":
        try:
            pts_int = int(new_points)
            if pts_int < 0:
                raise ValueError()
            update_payload["points"] = pts_int
        except (ValueError, TypeError):
            err = "적립금은 0 이상의 정수여야 합니다."
            return (jsonify({"success": False, "error": err}), 400) if request.is_json else (flash(err, "danger"), redirect(request.referrer or url_for("admin.admin_dashboard")))[1]

    if new_name is not None and new_name.strip():
        update_payload["full_name"] = new_name.strip()

    if new_phone is not None:
        update_payload["phone"] = new_phone.strip()

    if not update_payload:
        err = "수정할 항목이 지정되지 않았습니다."
        return (jsonify({"success": False, "error": err}), 400) if request.is_json else (flash(err, "warning"), redirect(request.referrer or url_for("admin.admin_dashboard")))[1]

    update_payload["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    admin_client = get_admin_supabase_client() or get_anon_supabase_client()
    if not admin_client:
        err = "데이터베이스 연결에 실패했습니다."
        return (jsonify({"success": False, "error": err}), 500) if request.is_json else (flash(err, "danger"), redirect(request.referrer or url_for("admin.admin_dashboard")))[1]

    try:
        # 1. profiles 테이블 갱신
        res = (
            admin_client.table("profiles")
            .update(update_payload)
            .eq("id", target_user_id)
            .execute()
        )

        if not res or not res.data:
            err = "해당 회원을 찾을 수 없거나 수정에 실패했습니다."
            return (jsonify({"success": False, "error": err}), 404) if request.is_json else (flash(err, "danger"), redirect(request.referrer or url_for("admin.admin_dashboard")))[1]

        updated_profile = res.data[0]

        # 2. Supabase Auth user_metadata에도 동기화 (스키마 컬럼 독립성 보장)
        try:
            auth_update_meta = {}
            if "full_name" in update_payload:
                auth_update_meta["full_name"] = update_payload["full_name"]
            if "phone" in update_payload:
                auth_update_meta["phone"] = update_payload["phone"]
            if auth_update_meta:
                admin_client.auth.admin.update_user_by_id(target_user_id, {"user_metadata": auth_update_meta})
        except Exception as auth_err:
            print(f"[Auth user_metadata 동기화 알림] {auth_err}", file=sys.stderr)

        msg = f"[{updated_profile.get('full_name') or updated_profile.get('email')}] 회원 정보가 성공적으로 수정되었습니다."

        if request.is_json:
            return jsonify({
                "success": True,
                "message": msg,
                "user": updated_profile
            })

        flash(msg, "success")
        return redirect(request.referrer or url_for("admin.admin_dashboard"))

    except Exception as e:
        print(f"[사용자 정보 수정 오류] {e}", file=sys.stderr)
        err = f"회원 정보 수정 중 오류가 발생했습니다: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": err}), 500
        flash(err, "danger")
        return redirect(request.referrer or url_for("admin.admin_dashboard"))


# -----------------------------------------------------------------------------
# 7. 주문 및 배송 상태 변경 API (/admin/orders/status/update)
# -----------------------------------------------------------------------------

@admin_bp.route("/orders/status/update", methods=["POST"])
@admin_bp.route("/api/orders/status/update", methods=["POST"])
@admin_required
def update_order_status():
    """
    [POST /admin/orders/status/update, POST /admin/api/orders/status/update]
    - 관리자가 주문의 배송 및 결제 상태 변경 (결제완료, 배송준비, 배송중, 배송완료, 주문취소, 환불완료)
    - JSON 및 Form 요청 모두 지원
    - orders 테이블 status 업데이트
    """
    data = request.get_json(silent=True) or request.form.to_dict()
    order_identifier = str(data.get("order_id") or data.get("order_number") or "").strip()
    new_status = str(data.get("status") or "").strip().upper()

    status_map = {
        "PENDING": ("결제대기", "warning text-dark"),
        "PAID": ("결제완료", "success"),
        "PREPARING": ("배송준비", "info text-dark"),
        "SHIPPED": ("배송중", "primary"),
        "DELIVERED": ("배송완료", "secondary"),
        "CANCELLED": ("주문취소", "danger"),
        "REFUNDED": ("환불완료", "dark"),
    }

    if not order_identifier:
        err = "주문 번호가 전달되지 않았습니다."
        return (jsonify({"success": False, "error": err}), 400) if request.is_json else (flash(err, "danger"), redirect(request.referrer or url_for("admin.admin_dashboard")))[1]

    if new_status not in status_map:
        err = f"유효하지 않은 주문 상태입니다. ({', '.join(status_map.keys())})"
        return (jsonify({"success": False, "error": err}), 400) if request.is_json else (flash(err, "danger"), redirect(request.referrer or url_for("admin.admin_dashboard")))[1]

    admin_client = get_admin_supabase_client() or get_anon_supabase_client()
    if not admin_client:
        err = "데이터베이스 연결에 실패했습니다."
        return (jsonify({"success": False, "error": err}), 500) if request.is_json else (flash(err, "danger"), redirect(request.referrer or url_for("admin.admin_dashboard")))[1]

    try:
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        update_payload = {
            "status": new_status,
            "updated_at": now_iso
        }
        if new_status == "PAID":
            update_payload["paid_at"] = now_iso

        # UUID인지 주문번호(VF-xxx 등)인지 판단하여 쿼리
        query = admin_client.table("orders").update(update_payload)
        import uuid
        is_uuid = False
        try:
            uuid.UUID(order_identifier)
            is_uuid = True
        except (ValueError, TypeError):
            is_uuid = False

        if is_uuid:
            query = query.eq("id", order_identifier)
        else:
            query = query.eq("order_number", order_identifier)

        res = query.execute()

        if not res or not res.data:
            # id로 실패 시 order_number로 재시도
            res = admin_client.table("orders").update(update_payload).eq("order_number", order_identifier).execute()

        if not res or not res.data:
            err = f"주문({order_identifier})을 찾을 수 없거나 상태 업데이트에 실패했습니다."
            return (jsonify({"success": False, "error": err}), 404) if request.is_json else (flash(err, "danger"), redirect(request.referrer or url_for("admin.admin_dashboard")))[1]

        updated_order = res.data[0]
        status_label, badge_class = status_map[new_status]
        order_num = updated_order.get("order_number") or order_identifier

        msg = f"주문 [{order_num}] 상태가 '{status_label}'(으)로 변경되었습니다."

        if request.is_json:
            return jsonify({
                "success": True,
                "message": msg,
                "order_number": order_num,
                "order_id": str(updated_order.get("id")),
                "status": new_status,
                "status_label": status_label,
                "badge_class": badge_class
            })

        flash(msg, "success")
        return redirect(request.referrer or url_for("admin.admin_dashboard"))

    except Exception as e:
        print(f"[주문 상태 변경 오류] {e}", file=sys.stderr)
        err = f"주문 상태 변경 중 오류가 발생했습니다: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": err}), 500
        flash(err, "danger")
        return redirect(request.referrer or url_for("admin.admin_dashboard"))



