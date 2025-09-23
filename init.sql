-- init.sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Создаем пользователя postgres если его нет (для совместимости)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'postgres') THEN
        CREATE ROLE postgres WITH LOGIN SUPERUSER CREATEDB CREATEROLE PASSWORD 'postgres';
    END IF;
END
$$;

-- Создаем дополнительные роли если нужно
CREATE ROLE read_only;
CREATE ROLE read_write;

-- Настраиваем привилегии (опционально)
GRANT CONNECT ON DATABASE instagram_db TO read_only;
GRANT CONNECT ON DATABASE instagram_db TO read_write;