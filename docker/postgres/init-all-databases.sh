#!/bin/bash
set -e

# Wait for databases to be created (they are created by init-4-test-databases.sql)
sleep 2

# Initialize db1
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "db1" <<-EOSQL
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

    CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
    CREATE EXTENSION IF NOT EXISTS hypopg;
EOSQL

# Initialize db2
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "db2" <<-EOSQL
    CREATE TABLE products (
        id SERIAL PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        price DECIMAL(10,2) NOT NULL,
        category VARCHAR(50),
        created_at TIMESTAMP DEFAULT NOW()
    );

    CREATE TABLE inventory (
        id SERIAL PRIMARY KEY,
        product_id INTEGER REFERENCES products(id),
        quantity INTEGER NOT NULL,
        location VARCHAR(100),
        updated_at TIMESTAMP DEFAULT NOW()
    );

    INSERT INTO products (name, price, category) VALUES
        ('Laptop', 999.99, 'Electronics'),
        ('Mouse', 29.99, 'Electronics'),
        ('Keyboard', 79.99, 'Electronics'),
        ('Monitor', 299.99, 'Electronics');

    INSERT INTO inventory (product_id, quantity, location) VALUES
        (1, 10, 'Warehouse A'),
        (2, 50, 'Warehouse B'),
        (3, 30, 'Warehouse A'),
        (4, 15, 'Warehouse C');

    CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
    CREATE EXTENSION IF NOT EXISTS hypopg;
EOSQL

# Initialize db3
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "db3" <<-EOSQL
    CREATE TABLE employees (
        id SERIAL PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        department VARCHAR(50),
        salary DECIMAL(10,2),
        hire_date DATE,
        created_at TIMESTAMP DEFAULT NOW()
    );

    CREATE TABLE projects (
        id SERIAL PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        description TEXT,
        start_date DATE,
        end_date DATE,
        status VARCHAR(50) DEFAULT 'active',
        created_at TIMESTAMP DEFAULT NOW()
    );

    INSERT INTO employees (name, department, salary, hire_date) VALUES
        ('Alice Brown', 'Engineering', 120000.00, '2020-01-15'),
        ('Charlie Davis', 'Marketing', 80000.00, '2021-03-20'),
        ('Diana Wilson', 'Sales', 90000.00, '2019-06-10'),
        ('Eve Martinez', 'Engineering', 130000.00, '2022-01-05');

    INSERT INTO projects (name, description, start_date, end_date, status) VALUES
        ('Project Alpha', 'Main product development', '2023-01-01', '2024-12-31', 'active'),
        ('Project Beta', 'Marketing campaign', '2023-06-01', '2023-12-31', 'completed'),
        ('Project Gamma', 'Infrastructure upgrade', '2024-01-01', NULL, 'active');

    CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
    CREATE EXTENSION IF NOT EXISTS hypopg;
EOSQL

# Initialize db4
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "db4" <<-EOSQL
    CREATE TABLE customers (
        id SERIAL PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        email VARCHAR(255) UNIQUE NOT NULL,
        phone VARCHAR(20),
        address TEXT,
        created_at TIMESTAMP DEFAULT NOW()
    );

    CREATE TABLE transactions (
        id SERIAL PRIMARY KEY,
        customer_id INTEGER REFERENCES customers(id),
        amount DECIMAL(10,2) NOT NULL,
        transaction_type VARCHAR(50),
        description TEXT,
        transaction_date TIMESTAMP DEFAULT NOW()
    );

    INSERT INTO customers (name, email, phone, address) VALUES
        ('Frank Taylor', 'frank@example.com', '+1-555-0101', '123 Main St, City'),
        ('Grace Lee', 'grace@example.com', '+1-555-0102', '456 Oak Ave, City'),
        ('Henry White', 'henry@example.com', '+1-555-0103', '789 Pine Rd, City');

    INSERT INTO transactions (customer_id, amount, transaction_type, description) VALUES
        (1, 500.00, 'purchase', 'Product purchase'),
        (1, 250.00, 'refund', 'Product return'),
        (2, 750.00, 'purchase', 'Service payment'),
        (2, 100.00, 'purchase', 'Additional service'),
        (3, 300.00, 'purchase', 'Subscription payment');

    CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
    CREATE EXTENSION IF NOT EXISTS hypopg;
EOSQL

echo "All databases initialized successfully!"

