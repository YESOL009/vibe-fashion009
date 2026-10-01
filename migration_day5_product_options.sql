-- =====================================================
-- Day 5: product_options 테이블 마이그레이션 SQL
-- =====================================================

-- [1] product_options 테이블에 신규 컬럼 추가
ALTER TABLE public.product_options
ADD COLUMN IF NOT EXISTS color TEXT,
ADD COLUMN IF NOT EXISTS size TEXT,
ADD COLUMN IF NOT EXISTS stock INTEGER DEFAULT 0;

-- [2] 조합 행 정합성 검증 CHECK 제약조건
-- 기존 name/value 기반 행은 color, size가 둘 다 NULL인 상태로 유지되고,
-- 신규 조합 행은 color와 size가 둘 다 반드시 값을 가져야 유효한 행으로 취급됩니다.
ALTER TABLE public.product_options
DROP CONSTRAINT IF EXISTS product_options_color_size_pair_check;

ALTER TABLE public.product_options
ADD CONSTRAINT product_options_color_size_pair_check
CHECK (
    (color IS NULL AND size IS NULL)
    OR
    (color IS NOT NULL AND size IS NOT NULL)
);

-- [3] UNIQUE 제약조건 추가: (product_id, color, size)
-- 부분 고유 인덱스(Partial Unique Index)를 생성하여
-- 기존 name/value 행(color, size가 NULL) 간에는 충돌 없이 유지되고,
-- 실제 조합 행(color, size가 존재하는 행)에 대해서만 중복을 완벽히 방지합니다.
CREATE UNIQUE INDEX IF NOT EXISTS product_options_product_color_size_unique
ON public.product_options (product_id, color, size)
WHERE color IS NOT NULL AND size IS NOT NULL;
