-- init.sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Создаем дополнительные роли если нужно
CREATE ROLE read_only;
CREATE ROLE read_write;

-- Настраиваем привилегии (опционально)
GRANT CONNECT ON DATABASE instagram_db TO read_only;
GRANT CONNECT ON DATABASE instagram_db TO read_write;