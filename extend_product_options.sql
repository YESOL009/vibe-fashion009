-- =====================================================
-- product_options 테이블 확장
-- Day 5: 색상 + 사이즈 조합 재고 관리
-- =====================================================

-- 1. 신규 컬럼 추가
ALTER TABLE product_options
ADD COLUMN IF NOT EXISTS color text,
ADD COLUMN IF NOT EXISTS size text,
ADD COLUMN IF NOT EXISTS stock integer DEFAULT 0;

-- 2. 기존 stock_quantity 값을 stock으로 복사 (선택 사항)
-- 기존 데이터의 재고를 새 컬럼에도 반영하고 싶다면 실행
UPDATE product_options
SET stock = COALESCE(stock_quantity, 0)
WHERE stock IS NULL OR stock = 0;

-- 3. 조합 행 검증용 CHECK 제약조건
-- color 와 size 는 둘 다 NULL 이거나 둘 다 값이 있어야 함
ALTER TABLE product_options
DROP CONSTRAINT IF EXISTS product_options_color_size_pair_check;

ALTER TABLE product_options
ADD CONSTRAINT product_options_color_size_pair_check
CHECK (
    (color IS NULL AND size IS NULL)
    OR
    (color IS NOT NULL AND size IS NOT NULL)
);

-- 4. 색상 + 사이즈 조합 중복 방지
-- 기존 name/value 행(color,size가 NULL)은 허용
-- 실제 조합 행(color,size가 존재하는 경우)만 UNIQUE 적용
CREATE UNIQUE INDEX IF NOT EXISTS product_options_product_color_size_unique
ON product_options(product_id, color, size)
WHERE color IS NOT NULL
  AND size IS NOT NULL;
