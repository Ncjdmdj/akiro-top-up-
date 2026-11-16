CREATE DATABASE IF NOT EXISTS topup_bot CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- ប្តូរ CHANGE_ME ឱ្យដូច DATABASE_URL ក្នុង .env
CREATE USER IF NOT EXISTS 'topup_user'@'localhost' IDENTIFIED BY 'CHANGE_ME';
CREATE USER IF NOT EXISTS 'topup_user'@'127.0.0.1' IDENTIFIED BY 'CHANGE_ME';
GRANT ALL PRIVILEGES ON topup_bot.* TO 'topup_user'@'localhost';
GRANT ALL PRIVILEGES ON topup_bot.* TO 'topup_user'@'127.0.0.1';
FLUSH PRIVILEGES;
-- Tables are created automatically by SQLAlchemy on first startup.
