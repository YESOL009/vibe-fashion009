-- ==============================================================================
-- VIBE-FASHION 쇼핑몰 초기 데이터(Seed) SQL
-- 실행 위치: Supabase Dashboard > SQL Editor
-- ==============================================================================

-- 1. 카테고리 7개 등록 (중복 실행 시 업데이트)
INSERT INTO public.categories (name, slug, description, sort_order, is_active)
VALUES
    ('상의', 'top', '티셔츠, 셔츠, 니트, 맨투맨 등', 1, true),
    ('하의', 'bottom', '팬츠, 데님, 슬랙스, 쇼츠 등', 2, true),
    ('아우터', 'outer', '자켓, 코트, 점퍼, 가디건 등', 3, true),
    ('원피스/세트', 'dress', '미디/롱 원피스, 셋업 수트 등', 4, true),
    ('액세서리', 'acc', '모자, 주얼리, 벨트, 머플러 등', 5, true),
    ('가방', 'bag', '숄더백, 토트백, 백팩, 크로스백 등', 6, true),
    ('신발', 'shoes', '스니커즈, 로퍼, 부츠, 샌들 등', 7, true)
ON CONFLICT (slug) DO UPDATE
SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    sort_order = EXCLUDED.sort_order,
    is_active = EXCLUDED.is_active;

-- 2. 상품 4개 등록 및 옵션/이미지 연결 (DO 블록 사용으로 안전한 ID 참조)
DO $$
DECLARE
    -- 카테고리 ID 변수
    v_cat_top UUID;
    v_cat_bottom UUID;
    v_cat_outer UUID;
    v_cat_dress UUID;
    v_cat_shoes UUID;
    v_cat_acc UUID;

    -- 상품 ID 변수
    v_prod_crop_t UUID;
    v_prod_denim_pants UUID;
    v_prod_cotton_jacket UUID;
    v_prod_floral_dress UUID;
    v_prod_chunky_sneakers UUID;
    v_prod_vintage_ballcap UUID;

    -- 옵션 생성용 배열
    v_colors TEXT[] := ARRAY['블랙', '화이트', '베이지'];
    v_sizes TEXT[] := ARRAY['S', 'M', 'L'];
    v_color TEXT;
    v_size TEXT;
BEGIN
    -- [1] 카테고리 ID 조회
    SELECT id INTO v_cat_top FROM public.categories WHERE slug = 'top' LIMIT 1;
    SELECT id INTO v_cat_bottom FROM public.categories WHERE slug = 'bottom' LIMIT 1;
    SELECT id INTO v_cat_outer FROM public.categories WHERE slug = 'outer' LIMIT 1;
    SELECT id INTO v_cat_dress FROM public.categories WHERE slug = 'dress' LIMIT 1;
    SELECT id INTO v_cat_shoes FROM public.categories WHERE slug = 'shoes' LIMIT 1;
    SELECT id INTO v_cat_acc FROM public.categories WHERE slug = 'acc' LIMIT 1;

    -- [2] 상품 등록

    -- 상품 1: 베이직 크롭 티셔츠 (상의, 19,900원, 원래가격/할인전 29,900원)
    INSERT INTO public.products (
        category_id, name, description, price, original_price,
        badge, badge_class, rating_avg, review_count, sales_count, is_active
    )
    VALUES (
        v_cat_top,
        '베이직 크롭 티셔츠',
        '트렌디한 크롭 기장감과 부드러운 코튼 소재로 제작되어 단독 또는 이너로 다양하게 연출 가능한 데일리 티셔츠입니다.',
        19900,
        29900,
        'SALE 33%',
        'bg-danger',
        4.8,
        42,
        150,
        true
    )
    RETURNING id INTO v_prod_crop_t;

    -- 상품 2: 와이드 데님 팬츠 (하의, 39,900원)
    INSERT INTO public.products (
        category_id, name, description, price, original_price,
        badge, badge_class, rating_avg, review_count, sales_count, is_active
    )
    VALUES (
        v_cat_bottom,
        '와이드 데님 팬츠',
        '자연스러운 워싱과 여유로운 와이드 핏으로 체형을 보완해주며 편안한 착용감을 선사하는 데님 팬츠입니다.',
        39900,
        NULL,
        'BEST',
        'bg-primary',
        4.9,
        89,
        230,
        true
    )
    RETURNING id INTO v_prod_denim_pants;

    -- 상품 3: 오버핏 코튼 자켓 (아우터, 59,900원)
    INSERT INTO public.products (
        category_id, name, description, price, original_price,
        badge, badge_class, rating_avg, review_count, sales_count, is_active
    )
    VALUES (
        v_cat_outer,
        '오버핏 코튼 자켓',
        '탄탄한 고밀도 코튼 원단과 모던한 오버핏 실루엣으로 간절기 시즌 감각적인 룩을 완성해주는 아우터입니다.',
        59900,
        NULL,
        'NEW',
        'bg-dark',
        4.7,
        18,
        64,
        true
    )
    RETURNING id INTO v_prod_cotton_jacket;

    -- 상품 4: 플로럴 미디 원피스 (원피스, 45,900원)
    INSERT INTO public.products (
        category_id, name, description, price, original_price,
        badge, badge_class, rating_avg, review_count, sales_count, is_active
    )
    VALUES (
        v_cat_dress,
        '플로럴 미디 원피스',
        '은은하고 로맨틱한 플로럴 패턴과 허리 스트링 라인으로 우아하고 화사한 무드를 연출하는 미디 원피스입니다.',
        45900,
        NULL,
        'HOT',
        'bg-warning text-dark',
        4.9,
        56,
        112,
        true
    )
    RETURNING id INTO v_prod_floral_dress;

    -- 상품 5: 청키 스트릿 스니커즈 (신발, 69,000원, 원래가격 89,000원)
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
    RETURNING id INTO v_prod_chunky_sneakers;

    -- 상품 6: 빈티지 워싱 볼캡 (액세서리/모자, 25,000원)
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
    RETURNING id INTO v_prod_vintage_ballcap;


    -- [3] 첫 번째 상품(베이직 크롭 티셔츠) 옵션 9개 등록 (블랙/화이트/베이지 × S/M/L)
    FOREACH v_color IN ARRAY v_colors LOOP
        FOREACH v_size IN ARRAY v_sizes LOOP
            INSERT INTO public.product_options (
                product_id, option_name, option_value, additional_price, stock_quantity, sku
            )
            VALUES (
                v_prod_crop_t,
                '컬러/사이즈',
                v_color || ' / ' || v_size,
                0,
                50,
                'TOP-CROP-' || UPPER(
                    CASE v_color
                        WHEN '블랙' THEN 'BLK'
                        WHEN '화이트' THEN 'WHT'
                        WHEN '베이지' THEN 'BEG'
                    END
                ) || '-' || v_size
            );
        END LOOP;
    END LOOP;

    -- 나머지 상품 기본 옵션 추가 (구매 가능하도록 기본 옵션 세팅)
    INSERT INTO public.product_options (product_id, option_name, option_value, stock_quantity, sku)
    VALUES
        (v_prod_denim_pants, '사이즈', 'S', 40, 'BTM-DNM-S'),
        (v_prod_denim_pants, '사이즈', 'M', 60, 'BTM-DNM-M'),
        (v_prod_denim_pants, '사이즈', 'L', 30, 'BTM-DNM-L'),
        (v_prod_cotton_jacket, '사이즈', 'FREE', 50, 'OUT-JKT-FREE'),
        (v_prod_floral_dress, '사이즈', 'FREE', 40, 'DRS-FLR-FREE'),
        (v_prod_chunky_sneakers, '사이즈', '240', 30, 'SHS-SNK-240'),
        (v_prod_chunky_sneakers, '사이즈', '250', 50, 'SHS-SNK-250'),
        (v_prod_chunky_sneakers, '사이즈', '260', 50, 'SHS-SNK-260'),
        (v_prod_chunky_sneakers, '사이즈', '270', 40, 'SHS-SNK-270'),
        (v_prod_vintage_ballcap, '사이즈', 'FREE', 80, 'ACC-CAP-FREE');


    -- [4] 상품별 썸네일 및 이미지 등록
    -- 상품 1: 베이직 크롭 티셔츠
    INSERT INTO public.product_images (product_id, image_url, is_thumbnail, sort_order)
    VALUES
        (v_prod_crop_t, '/static/images/crop_tee.png', true, 1),
        (v_prod_crop_t, '/static/images/crop_tee.png', false, 2);

    -- 상품 2: 와이드 데님 팬츠
    INSERT INTO public.product_images (product_id, image_url, is_thumbnail, sort_order)
    VALUES
        (v_prod_denim_pants, 'https://picsum.photos/seed/vibe_denim_pants/800/1000', true, 1),
        (v_prod_denim_pants, 'https://picsum.photos/seed/vibe_denim_detail/800/1000', false, 2);

    -- 상품 3: 오버핏 코튼 자켓
    INSERT INTO public.product_images (product_id, image_url, is_thumbnail, sort_order)
    VALUES
        (v_prod_cotton_jacket, 'https://picsum.photos/seed/vibe_cotton_jacket/800/1000', true, 1),
        (v_prod_cotton_jacket, 'https://picsum.photos/seed/vibe_jacket_detail/800/1000', false, 2);

    -- 상품 4: 플로럴 미디 원피스
    INSERT INTO public.product_images (product_id, image_url, is_thumbnail, sort_order)
    VALUES
        (v_prod_floral_dress, 'https://picsum.photos/seed/vibe_floral_dress/800/1000', true, 1),
        (v_prod_floral_dress, 'https://picsum.photos/seed/vibe_dress_detail/800/1000', false, 2);

    -- 상품 5: 청키 스트릿 스니커즈 (신발)
    INSERT INTO public.product_images (product_id, image_url, is_thumbnail, sort_order)
    VALUES
        (v_prod_chunky_sneakers, 'https://picsum.photos/seed/vibe_sneakers/800/1000', true, 1),
        (v_prod_chunky_sneakers, 'https://picsum.photos/seed/vibe_sneakers_detail/800/1000', false, 2);

    -- 상품 6: 빈티지 워싱 볼캡 (모자)
    INSERT INTO public.product_images (product_id, image_url, is_thumbnail, sort_order)
    VALUES
        (v_prod_vintage_ballcap, 'https://picsum.photos/seed/vibe_ballcap/800/1000', true, 1),
        (v_prod_vintage_ballcap, 'https://picsum.photos/seed/vibe_ballcap_detail/800/1000', false, 2);

END $$;
