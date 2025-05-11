-- 기본 user 생성
DO
$do$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'vd2') THEN
      CREATE USER vd2 WITH PASSWORD 'vd2';
      ALTER ROLE vd2 WITH SUPERUSER;
   END IF;
END
$do$;

-- 시스템 설정 변경
ALTER SYSTEM SET timezone TO 'UTC';
-- 설정 즉시 적용
SELECT pg_reload_conf();
-- 현재 세션에도 적용
SET timezone TO 'UTC';