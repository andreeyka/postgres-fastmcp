-- Initialize 4 databases with different access roles

-- Create databases
CREATE DATABASE user_ro_db;
CREATE DATABASE user_rw_db;
CREATE DATABASE admin_ro_db;
CREATE DATABASE admin_rw_db;

-- Create users
CREATE USER user_ro WITH PASSWORD 'password';
CREATE USER user_rw WITH PASSWORD 'password';
CREATE USER admin_ro WITH PASSWORD 'password';

-- ============================================
-- USER_RO_DB - read-only, public schema only
-- ============================================
\c user_ro_db

-- Connection privileges
GRANT CONNECT ON DATABASE user_ro_db TO user_ro;

-- Public schema privileges (read-only)
GRANT USAGE ON SCHEMA public TO user_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO user_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO user_ro;
-- Grant privileges on prefixed tables (will be created later)
-- These will be granted automatically via ALTER DEFAULT PRIVILEGES, but we grant explicitly for existing tables

-- Create test tables
CREATE TABLE test_users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE test_orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES test_users(id),
    amount DECIMAL(10,2) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create tables with prefix for table_prefix testing
CREATE TABLE app_users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE app_orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES app_users(id),
    amount DECIMAL(10,2) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create tables without prefix (should be hidden when table_prefix is set)
CREATE TABLE other_users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL
);

CREATE TABLE other_data (
    id SERIAL PRIMARY KEY,
    value VARCHAR(100) NOT NULL
);

-- Insert test data
INSERT INTO test_users (name, email) VALUES
    ('John Doe', 'john@example.com'),
    ('Jane Smith', 'jane@example.com'),
    ('Bob Johnson', 'bob@example.com');

INSERT INTO test_orders (user_id, amount, status) VALUES
    (1, 100.50, 'completed'),
    (1, 250.00, 'pending'),
    (2, 75.25, 'completed'),
    (2, 300.00, 'completed'),
    (3, 150.00, 'pending');

-- Insert data into prefixed tables
INSERT INTO app_users (name, email) VALUES
    ('App User 1', 'app1@example.com'),
    ('App User 2', 'app2@example.com');

INSERT INTO app_orders (user_id, amount, status) VALUES
    (1, 50.00, 'completed'),
    (2, 75.00, 'pending');

-- Insert data into non-prefixed tables
INSERT INTO other_users (name, email) VALUES
    ('Other User 1', 'other1@example.com');

INSERT INTO other_data (value) VALUES
    ('Secret Data 1'),
    ('Secret Data 2');

-- ============================================
-- USER_RW_DB - read-write, public schema only
-- ============================================
\c user_rw_db

-- Connection privileges
GRANT CONNECT ON DATABASE user_rw_db TO user_rw;

-- Public schema privileges (read-write)
GRANT USAGE ON SCHEMA public TO user_rw;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO user_rw;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO user_rw;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO user_rw;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO user_rw;
-- Grant privileges on prefixed tables (will be created later)
-- These will be granted automatically via ALTER DEFAULT PRIVILEGES, but we grant explicitly for existing tables

-- Create test tables
CREATE TABLE test_users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE test_orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES test_users(id),
    amount DECIMAL(10,2) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create tables with prefix for table_prefix testing
CREATE TABLE app_users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE app_orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES app_users(id),
    amount DECIMAL(10,2) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create tables without prefix (should be hidden when table_prefix is set)
CREATE TABLE other_users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL
);

CREATE TABLE other_data (
    id SERIAL PRIMARY KEY,
    value VARCHAR(100) NOT NULL
);

-- Insert test data
INSERT INTO test_users (name, email) VALUES
    ('John Doe', 'john@example.com'),
    ('Jane Smith', 'jane@example.com'),
    ('Bob Johnson', 'bob@example.com');

INSERT INTO test_orders (user_id, amount, status) VALUES
    (1, 100.50, 'completed'),
    (1, 250.00, 'pending'),
    (2, 75.25, 'completed'),
    (2, 300.00, 'completed'),
    (3, 150.00, 'pending');

-- Insert data into prefixed tables
INSERT INTO app_users (name, email) VALUES
    ('App User 1', 'app1@example.com'),
    ('App User 2', 'app2@example.com');

INSERT INTO app_orders (user_id, amount, status) VALUES
    (1, 50.00, 'completed'),
    (2, 75.00, 'pending');

-- Insert data into non-prefixed tables
INSERT INTO other_users (name, email) VALUES
    ('Other User 1', 'other1@example.com');

INSERT INTO other_data (value) VALUES
    ('Secret Data 1'),
    ('Secret Data 2');

-- ============================================
-- ADMIN_RO_DB - read-only, all schemas
-- ============================================
\c admin_ro_db

-- Connection privileges
GRANT CONNECT ON DATABASE admin_ro_db TO admin_ro;

-- All schemas privileges (read-only)
GRANT USAGE ON SCHEMA public TO admin_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO admin_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO admin_ro;

-- System schemas privileges (read-only)
GRANT USAGE ON SCHEMA pg_catalog TO admin_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA pg_catalog TO admin_ro;
GRANT USAGE ON SCHEMA information_schema TO admin_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA information_schema TO admin_ro;

-- Create test tables
CREATE TABLE test_users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE test_orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES test_users(id),
    amount DECIMAL(10,2) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create additional schema for testing
CREATE SCHEMA test_schema;
CREATE TABLE test_schema.test_table (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100)
);

-- Insert test data
INSERT INTO test_users (name, email) VALUES
    ('John Doe', 'john@example.com'),
    ('Jane Smith', 'jane@example.com'),
    ('Bob Johnson', 'bob@example.com');

INSERT INTO test_orders (user_id, amount, status) VALUES
    (1, 100.50, 'completed'),
    (1, 250.00, 'pending'),
    (2, 75.25, 'completed'),
    (2, 300.00, 'completed'),
    (3, 150.00, 'pending');

INSERT INTO test_schema.test_table (name) VALUES ('Test 1'), ('Test 2');

-- Monitoring extensions
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS hypopg;

-- ============================================
-- ADMIN_RW_DB - full access, all schemas
-- ============================================
\c admin_rw_db

-- Using postgres user (superuser)
-- All privileges are available by default

-- Create test tables
CREATE TABLE test_users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE test_orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES test_users(id),
    amount DECIMAL(10,2) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create additional schema for testing
CREATE SCHEMA test_schema;
CREATE TABLE test_schema.test_table (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100)
);

-- Insert test data
INSERT INTO test_users (name, email) VALUES
    ('John Doe', 'john@example.com'),
    ('Jane Smith', 'jane@example.com'),
    ('Bob Johnson', 'bob@example.com');

INSERT INTO test_orders (user_id, amount, status) VALUES
    (1, 100.50, 'completed'),
    (1, 250.00, 'pending'),
    (2, 75.25, 'completed'),
    (2, 300.00, 'completed'),
    (3, 150.00, 'pending');

INSERT INTO test_schema.test_table (name) VALUES ('Test 1'), ('Test 2');

-- Monitoring extensions
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS hypopg;

-- Create indexes for testing
CREATE INDEX idx_user_email ON test_users(email);
CREATE INDEX idx_order_user_id ON test_orders(user_id);
CREATE INDEX idx_order_status ON test_orders(status);
