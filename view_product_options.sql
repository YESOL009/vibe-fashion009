-- =====================================================
-- Day 5: 상품별 색상 x 사이즈 옵션 및 재고 현황 조회 쿼리
-- Supabase SQL Editor에서 실행하면 결과가 표(Table)로 출력됩니다.
-- =====================================================

SELECT 
    p.name AS "상품명",
    po.color AS "색상",
    po.size AS "사이즈",
    po.stock AS "재고수량",
    CASE 
        WHEN po.stock = 0 THEN '❌ 품절'
        WHEN po.stock = 1 THEN '⚠️ 품절 임박 (1개 남음)'
        ELSE '✅ 구매 가능'
    END AS "상태",
    po.additional_price AS "추가금액",
    po.id AS "옵션ID",
    po.product_id AS "상품ID"
FROM public.product_options po
JOIN public.products p ON po.product_id = p.id
WHERE po.color IS NOT NULL AND po.size IS NOT NULL
ORDER BY p.name ASC, po.color ASC, po.size ASC;
