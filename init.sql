-- init.sql
-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create the lun1z user if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'lun1z') THEN
        CREATE ROLE lun1z WITH LOGIN PASSWORD '3b3e3tzp8e' SUPERUSER CREATEDB CREATEROLE;
    END IF;
END
$$;

-- Grant all privileges on the database to lun1z
GRANT ALL PRIVILEGES ON DATABASE instagram_db TO lun1z;
GRANT ALL PRIVILEGES ON SCHEMA public TO lun1z;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO lun1z;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO lun1z;

-- Create additional roles if they don't exist
DO $$
BEGIN
    -- Create read_only role
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'read_only') THEN
        CREATE ROLE read_only;
    END IF;
    
    -- Create read_write role  
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'read_write') THEN
        CREATE ROLE read_write;
    END IF;
END
$$;

-- Grant basic permissions to read_only role
GRANT CONNECT ON DATABASE instagram_db TO read_only;
GRANT USAGE ON SCHEMA public TO read_only;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO read_only;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO read_only;

-- Grant basic permissions to read_write role
GRANT CONNECT ON DATABASE instagram_db TO read_write;
GRANT USAGE ON SCHEMA public TO read_write;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO read_write;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO read_write;

-- Set default privileges for future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO read_only;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO read_write;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON SEQUENCES TO read_only;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO read_write;