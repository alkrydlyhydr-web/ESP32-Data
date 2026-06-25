-- إنشاء قاعدة البيانات إذا لم تكن موجودة
CREATE DATABASE IF NOT EXISTS student_attendance
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE student_attendance;

-- 1. جدول الطلاب
CREATE TABLE IF NOT EXISTS students (
    id INT AUTO_INCREMENT PRIMARY KEY,
    academic_id VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) NOT NULL,
    fingerprint_id INT NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. جدول الحضور اليومي
CREATE TABLE IF NOT EXISTS attendance (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    date DATE NOT NULL,
    check_in_time TIME NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'Present',
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    UNIQUE KEY unique_daily_attendance (student_id, date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. جدول إعدادات النظام
CREATE TABLE IF NOT EXISTS system_settings (
    settings_key VARCHAR(50) PRIMARY KEY,
    settings_value TEXT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- إدخال الإعدادات الافتراضية للنظام
INSERT IGNORE INTO system_settings (settings_key, settings_value) VALUES 
('serial_port', 'COM8'),
('serial_baudrate', '115200'),
('flask_port', '5000'),
('wifi_ssid', 'MyWiFiNetwork'),
('wifi_password', 'MyWiFiPassword'),
('smtp_server', 'smtp.gmail.com'),
('smtp_port', '587'),
('smtp_email', ''),
('smtp_password', ''),
('telegram_bot_token', ''),
('telegram_chat_id', ''),
('attendance_time_start', '08:00:00'),
('attendance_time_late', '08:30:00');
