-- =====================================================
-- Day 5: 상품별 색상 + 사이즈 조합 옵션 Seed SQL
-- =====================================================

-- 1. 각 상품(products) 전체를 대상으로 색상(Black, White, Gray) × 사이즈(S, M, L) 조합 생성
-- 2. 재고(stock)는 품절(0), 품절임박(1), 충분(10~25)을 조합 순서별로 다양하게 배정
-- 3. 이미 존재하는 동일 조합(product_id, color, size)은 stock을 갱신(ON CONFLICT DO UPDATE)

WITH colors AS (
    SELECT 'Black' AS color, 1 AS color_order
    UNION ALL
    SELECT 'White' AS color, 2 AS color_order
    UNION ALL
    SELECT 'Gray'  AS color, 3 AS color_order
),
sizes AS (
    SELECT 'S' AS size, 1 AS size_order
    UNION ALL
    SELECT 'M' AS size, 2 AS size_order
    UNION ALL
    SELECT 'L' AS size, 3 AS size_order
),
product_combos AS (
    SELECT
        p.id AS product_id,
        c.color,
        s.size,
        -- 품절 테스트 시나리오용 다양한 재고 배정 로직:
        -- 각 색상/사이즈 순번 조합에 따라 품절(0), 품절임박(1), 여유(12, 15, 20, 25 등) 골고루 분배
        CASE 
            WHEN c.color_order = 1 AND s.size_order = 1 THEN 0   -- Black / S: 품절 (0개)
            WHEN c.color_order = 1 AND s.size_order = 2 THEN 1   -- Black / M: 품절 임박 (1개)
            WHEN c.color_order = 1 AND s.size_order = 3 THEN 15  -- Black / L: 충분 (15개)
            WHEN c.color_order = 2 AND s.size_order = 1 THEN 20  -- White / S: 충분 (20개)
            WHEN c.color_order = 2 AND s.size_order = 2 THEN 0   -- White / M: 품절 (0개)
            WHEN c.color_order = 2 AND s.size_order = 3 THEN 1   -- White / L: 품절 임박 (1개)
            WHEN c.color_order = 3 AND s.size_order = 1 THEN 10  -- Gray / S: 충분 (10개)
            WHEN c.color_order = 3 AND s.size_order = 2 THEN 25  -- Gray / M: 충분 (25개)
            WHEN c.color_order = 3 AND s.size_order = 3 THEN 0   -- Gray / L: 품절 (0개)
            ELSE 10
        END AS stock_qty,
        '색상/사이즈' AS opt_name,
        c.color || ' / ' || s.size AS opt_val
    FROM products p
    CROSS JOIN colors c
    CROSS JOIN sizes s
)
INSERT INTO product_options (
    product_id,
    option_name,
    option_value,
    color,
    size,
    stock,
    stock_quantity,
    additional_price
)
SELECT
    pc.product_id,
    pc.opt_name,
    pc.opt_val,
    pc.color,
    pc.size,
    pc.stock_qty,
    pc.stock_qty, -- 기존 stock_quantity 컬럼과의 호환성 유지
    0
FROM product_combos pc
ON CONFLICT (product_id, color, size) WHERE color IS NOT NULL AND size IS NOT NULL
DO UPDATE SET
    stock = EXCLUDED.stock,
    stock_quantity = EXCLUDED.stock_quantity,
    option_name = EXCLUDED.option_name,
    option_value = EXCLUDED.option_value;
