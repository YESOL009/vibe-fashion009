-- ==============================================================================
-- VIBE-FASHION 관리자(Admin) 권한 설정 및 운영 SQL 스크립트
-- 실행 위치: Supabase Dashboard > SQL Editor
-- ==============================================================================

-- 1. profiles 테이블 role 컬럼의 CHECK 제약조건 확인 (customer, admin, seller)
-- 기존 schema.sql: role TEXT NOT NULL DEFAULT 'customer' CHECK (role IN ('customer', 'admin', 'seller'))

-- 2. 특정 회원을 관리자(Admin)로 승격하기
-- (아래 이메일 주소를 실제 관리자 계정 이메일로 변경 후 실행하세요)
UPDATE public.profiles
SET role = 'admin',
    updated_at = timezone('utc'::text, now())
WHERE email = 'example@vibe-fashion.com';

-- 3. 현재 관리자(admin) 권한 보유자 목록 조회
SELECT id, email, full_name, role, grade, created_at
FROM public.profiles
WHERE role = 'admin';

-- 4. 관리자 권한 회수 (필요시 일반 고객으로 복원)
-- UPDATE public.profiles
-- SET role = 'customer',
--     updated_at = timezone('utc'::text, now())
-- WHERE email = 'example@vibe-fashion.com';
