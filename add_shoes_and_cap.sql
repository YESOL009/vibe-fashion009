-- ==============================================================================
-- 신발 및 모자 상품 추가 SQL
-- 실행 위치: Supabase Dashboard > SQL Editor
-- ==============================================================================

DO $$
DECLARE
    v_cat_shoes UUID;
    v_cat_acc UUID;
    v_prod_shoes UUID;
    v_prod_cap UUID;
BEGIN
    -- 1. 카테고리 ID 조회
    SELECT id INTO v_cat_shoes FROM public.categories WHERE slug = 'shoes' LIMIT 1;
    SELECT id INTO v_cat_acc FROM public.categories WHERE slug = 'acc' LIMIT 1;

    -- 2. 신발 상품 등록
    INSERT INTO public.products (
        category_id, name, description, price, original_price,
        badge, badge_class, rating_avg, review_count, sales_count, is_active
    )
    VALUES (
        v_cat_shoes,
        '청키 스트릿 스니커즈',
        '볼드한 아웃솔과 편안한 쿠셔닝으로 장시간 착용에도 편안하며 스트릿 무드를 극대화해주는 스니커즈입니다.',
        69000,
        89000,
        'BEST',
        'bg-primary',
        4.9,
        78,
        180,
        true
    )
    RETURNING id INTO v_prod_shoes;

    -- 신발 사이즈 옵션
    INSERT INTO public.product_options (product_id, option_name, option_value, stock_quantity, sku)
    VALUES
        (v_prod_shoes, '사이즈', '240', 30, 'SHS-SNK-240'),
        (v_prod_shoes, '사이즈', '250', 50, 'SHS-SNK-250'),
        (v_prod_shoes, '사이즈', '260', 50, 'SHS-SNK-260'),
        (v_prod_shoes, '사이즈', '270', 40, 'SHS-SNK-270');

    -- 신발 이미지
    INSERT INTO public.product_images (product_id, image_url, is_thumbnail, sort_order)
    VALUES
        (v_prod_shoes, 'https://images.unsplash.com/photo-1549298916-b41d501d3772?w=800&auto=format&fit=crop&q=80', true, 1),
        (v_prod_shoes, 'https://images.unsplash.com/photo-1595950653106-6c9ebd614d3a?w=800&auto=format&fit=crop&q=80', false, 2);


    -- 3. 모자 상품 등록
    INSERT INTO public.products (
        category_id, name, description, price, original_price,
        badge, badge_class, rating_avg, review_count, sales_count, is_active
    )
    VALUES (
        v_cat_acc,
        '빈티지 워싱 볼캡',
        '자연스러운 워싱 가공과 세련된 자수 로고 포인트로 어느 룩에나 쉽게 매치하기 좋은 데일리 볼캡 모자입니다.',
        25000,
        NULL,
        'NEW',
        'bg-dark',
        4.8,
        34,
        95,
        true
    )
    RETURNING id INTO v_prod_cap;

    -- 모자 사이즈 옵션
    INSERT INTO public.product_options (product_id, option_name, option_value, stock_quantity, sku)
    VALUES
        (v_prod_cap, '사이즈', 'FREE', 80, 'ACC-CAP-FREE');

    -- 모자 이미지
    INSERT INTO public.product_images (product_id, image_url, is_thumbnail, sort_order)
    VALUES
        (v_prod_cap, 'https://images.unsplash.com/photo-1588850561407-ed78c282e89b?w=800&auto=format&fit=crop&q=80', true, 1),
        (v_prod_cap, 'https://images.unsplash.com/photo-1575428652377-a2d80e2277fc?w=800&auto=format&fit=crop&q=80', false, 2);

END $$;
