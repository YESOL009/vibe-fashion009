-- ==============================================================================
-- VIBE-FASHION 쇼핑몰 Supabase Database Schema
-- 실행 위치: Supabase Dashboard > SQL Editor
-- ==============================================================================

-- 1. 확장 기능 활성화 (UUID 생성 등)
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ==============================================================================
-- 2. 테이블 생성
-- ==============================================================================

-- [1] 회원 프로필 테이블 (auth.users와 1:1 연동)
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT,
    full_name TEXT,
    avatar_url TEXT,
    phone TEXT,
    grade TEXT NOT NULL DEFAULT 'BRONZE' CHECK (grade IN ('BRONZE', 'SILVER', 'GOLD', 'VIP')),
    total_spent NUMERIC(12, 0) NOT NULL DEFAULT 0 CHECK (total_spent >= 0),
    points INTEGER NOT NULL DEFAULT 1000 CHECK (points >= 0), -- 신규 가입 포인트
    role TEXT NOT NULL DEFAULT 'customer' CHECK (role IN ('customer', 'admin', 'seller')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- [2] 상품 카테고리 테이블
CREATE TABLE IF NOT EXISTS public.categories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,          -- 예: OUTER, TOP, BOTTOM, ACC
    slug TEXT NOT NULL UNIQUE,          -- 예: outer, top, bottom, acc
    description TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- [3] 상품 기본 정보 테이블
CREATE TABLE IF NOT EXISTS public.products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    category_id UUID REFERENCES public.categories(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    description TEXT,
    price NUMERIC(12, 0) NOT NULL CHECK (price >= 0),
    original_price NUMERIC(12, 0) CHECK (original_price >= price),
    badge TEXT,                         -- 예: BEST, NEW, SALE 20%, HOT
    badge_class TEXT DEFAULT 'bg-dark', -- 예: bg-danger, bg-primary, bg-warning text-dark
    rating_avg NUMERIC(3, 2) NOT NULL DEFAULT 0.0 CHECK (rating_avg >= 0.0 AND rating_avg <= 5.0),
    review_count INTEGER NOT NULL DEFAULT 0 CHECK (review_count >= 0),
    sales_count INTEGER NOT NULL DEFAULT 0 CHECK (sales_count >= 0),
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- [4] 상품 옵션 테이블 (사이즈, 색상, 재고 등)
CREATE TABLE IF NOT EXISTS public.product_options (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID NOT NULL REFERENCES public.products(id) ON DELETE CASCADE,
    option_name TEXT NOT NULL,          -- 예: 사이즈, 색상
    option_value TEXT NOT NULL,         -- 예: M (95~100), 블랙
    additional_price NUMERIC(12, 0) NOT NULL DEFAULT 0, -- 옵션 추가금
    stock_quantity INTEGER NOT NULL DEFAULT 0 CHECK (stock_quantity >= 0),
    sku TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- [5] 상품 이미지 테이블
CREATE TABLE IF NOT EXISTS public.product_images (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID NOT NULL REFERENCES public.products(id) ON DELETE CASCADE,
    image_url TEXT NOT NULL,
    is_thumbnail BOOLEAN NOT NULL DEFAULT false,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- [6] 장바구니 테이블
CREATE TABLE IF NOT EXISTS public.carts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES public.products(id) ON DELETE CASCADE,
    option_id UUID REFERENCES public.product_options(id) ON DELETE CASCADE,
    quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    UNIQUE(user_id, product_id, option_id)
);

-- [7] 주문 정보 테이블
CREATE TABLE IF NOT EXISTS public.orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_number TEXT NOT NULL UNIQUE,  -- 예: ORD-20260923-XXXX
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE RESTRICT,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (
        status IN ('PENDING', 'PAID', 'PREPARING', 'SHIPPED', 'DELIVERED', 'CANCELLED', 'REFUNDED')
    ),
    total_amount NUMERIC(12, 0) NOT NULL CHECK (total_amount >= 0),    -- 상품 원금 합계
    discount_amount NUMERIC(12, 0) NOT NULL DEFAULT 0 CHECK (discount_amount >= 0),
    shipping_fee NUMERIC(12, 0) NOT NULL DEFAULT 0 CHECK (shipping_fee >= 0),
    final_amount NUMERIC(12, 0) NOT NULL CHECK (final_amount >= 0),    -- 실 결제 금액
    recipient_name TEXT NOT NULL,
    recipient_phone TEXT NOT NULL,
    postal_code TEXT NOT NULL,
    shipping_address TEXT NOT NULL,
    shipping_address_detail TEXT,
    delivery_request TEXT,
    paid_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- [8] 주문 상세 항목 테이블
CREATE TABLE IF NOT EXISTS public.order_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES public.orders(id) ON DELETE CASCADE,
    product_id UUID REFERENCES public.products(id) ON DELETE SET NULL,
    option_id UUID REFERENCES public.product_options(id) ON DELETE SET NULL,
    product_name TEXT NOT NULL,
    option_name TEXT,
    price NUMERIC(12, 0) NOT NULL CHECK (price >= 0),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    subtotal NUMERIC(12, 0) NOT NULL CHECK (subtotal >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- [9] 환불/반품 요청 테이블
CREATE TABLE IF NOT EXISTS public.refunds (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES public.orders(id) ON DELETE CASCADE,
    order_item_id UUID REFERENCES public.order_items(id) ON DELETE SET NULL,
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE RESTRICT,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'REQUESTED' CHECK (
        status IN ('REQUESTED', 'APPROVED', 'REJECTED', 'COMPLETED')
    ),
    refund_amount NUMERIC(12, 0) NOT NULL CHECK (refund_amount >= 0),
    admin_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- [10] 알림 테이블
CREATE TABLE IF NOT EXISTS public.notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'INFO' CHECK (
        type IN ('INFO', 'ORDER', 'DELIVERY', 'EVENT', 'PROMOTION')
    ),
    is_read BOOLEAN NOT NULL DEFAULT false,
    link_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- [11] 상품 리뷰 테이블
CREATE TABLE IF NOT EXISTS public.reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES public.products(id) ON DELETE CASCADE,
    order_item_id UUID REFERENCES public.order_items(id) ON DELETE SET NULL,
    rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
    content TEXT NOT NULL,
    image_urls TEXT[],                  -- 이미지 다중 첨부
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- ==============================================================================
-- 3. 인덱스 생성 (조회 성능 최적화)
-- ==============================================================================
CREATE INDEX IF NOT EXISTS idx_products_category ON public.products(category_id);
CREATE INDEX IF NOT EXISTS idx_products_is_active ON public.products(is_active);
CREATE INDEX IF NOT EXISTS idx_product_options_product ON public.product_options(product_id);
CREATE INDEX IF NOT EXISTS idx_product_images_product ON public.product_images(product_id);
CREATE INDEX IF NOT EXISTS idx_carts_user ON public.carts(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_user ON public.orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON public.orders(status);
CREATE INDEX IF NOT EXISTS idx_order_items_order ON public.order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_refunds_order ON public.refunds(order_id);
CREATE INDEX IF NOT EXISTS idx_notifications_user_read ON public.notifications(user_id, is_read);
CREATE INDEX IF NOT EXISTS idx_reviews_product ON public.reviews(product_id);

-- ==============================================================================
-- 4. 트리거 및 함수
-- ==============================================================================

-- [A] 신규 회원 가입(소셜 로그인 포함) 시 profiles 자동 생성 함수 및 트리거
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    INSERT INTO public.profiles (
        id,
        email,
        full_name,
        avatar_url,
        phone,
        grade,
        total_spent,
        points,
        role
    )
    VALUES (
        NEW.id,
        NEW.email,
        -- 카카오, 구글, 깃허브 등 소셜 공급자 및 이메일 가입 메타데이터 파싱
        COALESCE(
            NEW.raw_user_meta_data->>'full_name',
            NEW.raw_user_meta_data->>'name',
            NEW.raw_user_meta_data->>'user_name',
            split_part(NEW.email, '@', 1)
        ),
        COALESCE(
            NEW.raw_user_meta_data->>'avatar_url',
            NEW.raw_user_meta_data->>'picture',
            ''
        ),
        COALESCE(NEW.raw_user_meta_data->>'phone', ''),
        'BRONZE',
        0,
        1000,
        'customer'
    )
    ON CONFLICT (id) DO UPDATE
    SET
        email = EXCLUDED.email,
        full_name = COALESCE(EXCLUDED.full_name, profiles.full_name),
        avatar_url = COALESCE(EXCLUDED.avatar_url, profiles.avatar_url),
        updated_at = timezone('utc'::text, now());

    RETURN NEW;
END;
$$;

-- auth.users 테이블에 트리거 연결
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_new_user();


-- [B] 고객 등급 자동 업데이트 함수 (update_customer_grade)
-- 기준:
-- VIP:    누적 구매액 1,000,000원 이상
-- GOLD:   누적 구매액 500,000원 이상
-- SILVER: 누적 구매액 200,000원 이상
-- BRONZE: 누적 구매액 200,000원 미만
CREATE OR REPLACE FUNCTION public.update_customer_grade(target_user_id UUID)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_total_spent NUMERIC(12, 0);
    v_new_grade TEXT;
BEGIN
    -- 결제 완료(PAID), 배송준비(PREPARING), 배송중(SHIPPED), 배송완료(DELIVERED) 주문 실 결제액 합산
    SELECT COALESCE(SUM(final_amount), 0)
    INTO v_total_spent
    FROM public.orders
    WHERE user_id = target_user_id
      AND status IN ('PAID', 'PREPARING', 'SHIPPED', 'DELIVERED');

    -- 등급 산정
    IF v_total_spent >= 1000000 THEN
        v_new_grade := 'VIP';
    ELSIF v_total_spent >= 500000 THEN
        v_new_grade := 'GOLD';
    ELSIF v_total_spent >= 200000 THEN
        v_new_grade := 'SILVER';
    ELSE
        v_new_grade := 'BRONZE';
    END IF;

    -- 회원 정보 갱신
    UPDATE public.profiles
    SET
        total_spent = v_total_spent,
        grade = v_new_grade,
        updated_at = timezone('utc'::text, now())
    WHERE id = target_user_id;
END;
$$;


-- [C] 주문 상태 변경 시 고객 등급 자동 재산정 트리거
CREATE OR REPLACE FUNCTION public.trigger_order_customer_grade_update()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    -- 주문 추가/수정 시 주문자의 등급을 자동 계산
    IF (TG_OP = 'INSERT' OR TG_OP = 'UPDATE') THEN
        PERFORM public.update_customer_grade(NEW.user_id);
    ELSIF (TG_OP = 'DELETE') THEN
        PERFORM public.update_customer_grade(OLD.user_id);
    END IF;
    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS on_order_status_grade_sync ON public.orders;
CREATE TRIGGER on_order_status_grade_sync
    AFTER INSERT OR UPDATE OR DELETE ON public.orders
    FOR EACH ROW
    EXECUTE FUNCTION public.trigger_order_customer_grade_update();


-- [D] 리뷰 등록/삭제 시 상품 평균 평점 및 리뷰 개수 동기화 함수
CREATE OR REPLACE FUNCTION public.sync_product_review_stats()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_product_id UUID;
BEGIN
    IF (TG_OP = 'DELETE') THEN
        v_product_id := OLD.product_id;
    ELSE
        v_product_id := NEW.product_id;
    END IF;

    UPDATE public.products
    SET
        rating_avg = COALESCE((
            SELECT ROUND(AVG(rating)::numeric, 1)
            FROM public.reviews
            WHERE product_id = v_product_id
        ), 0.0),
        review_count = (
            SELECT COUNT(*)
            FROM public.reviews
            WHERE product_id = v_product_id
        ),
        updated_at = timezone('utc'::text, now())
    WHERE id = v_product_id;

    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS on_review_stat_sync ON public.reviews;
CREATE TRIGGER on_review_stat_sync
    AFTER INSERT OR UPDATE OR DELETE ON public.reviews
    FOR EACH ROW
    EXECUTE FUNCTION public.sync_product_review_stats();


-- ==============================================================================
-- 5. Row Level Security (RLS) 정책 설정
-- ==============================================================================
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.categories ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.products ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.product_options ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.product_images ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.carts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.order_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.refunds ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reviews ENABLE ROW LEVEL SECURITY;

-- profiles RLS
CREATE POLICY "본인 프로필 조회" ON public.profiles FOR SELECT USING (auth.uid() = id);
CREATE POLICY "본인 프로필 수정" ON public.profiles FOR UPDATE USING (auth.uid() = id);

-- categories / products / product_options / product_images (공개 읽기)
CREATE POLICY "카테고리 누구나 조회" ON public.categories FOR SELECT USING (true);
CREATE POLICY "상품 누구나 조회" ON public.products FOR SELECT USING (is_active = true);
CREATE POLICY "상품 옵션 누구나 조회" ON public.product_options FOR SELECT USING (true);
CREATE POLICY "상품 이미지 누구나 조회" ON public.product_images FOR SELECT USING (true);

-- carts RLS (본인 장바구니만 제어)
CREATE POLICY "본인 장바구니 조회" ON public.carts FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "본인 장바구니 추가" ON public.carts FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "본인 장바구니 수정" ON public.carts FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "본인 장바구니 삭제" ON public.carts FOR DELETE USING (auth.uid() = user_id);

-- orders & order_items RLS
CREATE POLICY "본인 주문 목록 조회" ON public.orders FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "본인 주문 생성" ON public.orders FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "본인 주문 상세 조회" ON public.order_items FOR SELECT USING (
    EXISTS (SELECT 1 FROM public.orders WHERE orders.id = order_items.order_id AND orders.user_id = auth.uid())
);
CREATE POLICY "본인 주문 상세 생성" ON public.order_items FOR INSERT WITH CHECK (
    EXISTS (SELECT 1 FROM public.orders WHERE orders.id = order_items.order_id AND orders.user_id = auth.uid())
);

-- refunds RLS
CREATE POLICY "본인 환불 내역 조회" ON public.refunds FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "본인 환불 요청 생성" ON public.refunds FOR INSERT WITH CHECK (auth.uid() = user_id);

-- notifications RLS
CREATE POLICY "본인 알림 조회" ON public.notifications FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "본인 알림 상태 업데이트" ON public.notifications FOR UPDATE USING (auth.uid() = user_id);

-- reviews RLS
CREATE POLICY "리뷰 누구나 조회" ON public.reviews FOR SELECT USING (true);
CREATE POLICY "본인 리뷰 작성" ON public.reviews FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "본인 리뷰 수정" ON public.reviews FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "본인 리뷰 삭제" ON public.reviews FOR DELETE USING (auth.uid() = user_id);


-- ==============================================================================
-- 6. 초기 카테고리 시드 데이터 (선택 사항)
-- ==============================================================================
INSERT INTO public.categories (name, slug, sort_order)
VALUES 
    ('OUTER', 'outer', 1),
    ('TOP', 'top', 2),
    ('BOTTOM', 'bottom', 3),
    ('ACC', 'acc', 4)
ON CONFLICT (name) DO NOTHING;
