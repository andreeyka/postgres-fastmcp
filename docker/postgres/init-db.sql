-- Создание трех тестовых баз данных с тестовыми пользователями

-- База данных 1: test_db1
CREATE DATABASE test_db1;
CREATE USER test_user1 WITH PASSWORD 'test_pass1';
GRANT ALL PRIVILEGES ON DATABASE test_db1 TO test_user1;

-- База данных 2: test_db2
CREATE DATABASE test_db2;
CREATE USER test_user2 WITH PASSWORD 'test_pass2';
GRANT ALL PRIVILEGES ON DATABASE test_db2 TO test_user2;

-- База данных 3: test_db3
CREATE DATABASE test_db3;
CREATE USER test_user3 WITH PASSWORD 'test_pass3';
GRANT ALL PRIVILEGES ON DATABASE test_db3 TO test_user3;

-- Подключаемся к каждой базе и даем полные права на схему public
\c test_db1
GRANT ALL ON SCHEMA public TO test_user1;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO test_user1;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO test_user1;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO test_user1;

\c test_db2
GRANT ALL ON SCHEMA public TO test_user2;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO test_user2;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO test_user2;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO test_user2;

\c test_db3
GRANT ALL ON SCHEMA public TO test_user3;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO test_user3;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO test_user3;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO test_user3;
