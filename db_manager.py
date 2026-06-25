import mysql.connector
from mysql.connector import Error
import os
from datetime import datetime

class DatabaseManager:
    def __init__(self, host="localhost", user="root", password="", database="student_attendance"):
        self.config = {
            'host': host,
            'user': user,
            'password': password,
            'database': database,
            'charset': 'utf8mb4',
            'use_unicode': True
        }
        self.raw_config = {
            'host': host,
            'user': user,
            'password': password
        }

    def get_connection(self, include_db=True):
        """توفير اتصال بقاعدة البيانات"""
        try:
            if include_db:
                return mysql.connector.connect(**self.config)
            else:
                return mysql.connector.connect(**self.raw_config)
        except Error as e:
            print(f"Error connecting to MySQL: {e}")
            raise e

    def initialize_database(self, sql_file_path="database.sql"):
        """تهيئة قاعدة البيانات وتوليد الجداول من ملف sql"""
        conn = None
        cursor = None
        try:
            # الاتصال بـ MySQL بدون تحديد قاعدة البيانات أولاً لإنشائها
            conn = self.get_connection(include_db=False)
            cursor = conn.cursor()
            
            # قراءة ملف SQL
            if os.path.exists(sql_file_path):
                with open(sql_file_path, 'r', encoding='utf-8') as f:
                    sql_commands = f.read()
                
                # تقسيم الأوامر وتنفيذها
                commands = sql_commands.split(';')
                for command in commands:
                    command = command.strip()
                    if command:
                        cursor.execute(command)
                conn.commit()
                print("Database initialized successfully.")
            else:
                # إذا لم يكن الملف موجوداً، نقوم بإنشاء قاعدة البيانات والجداول برمجياً
                cursor.execute("CREATE DATABASE IF NOT EXISTS student_attendance CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
                cursor.execute("USE student_attendance;")
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS students (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        academic_id VARCHAR(50) NOT NULL UNIQUE,
                        name VARCHAR(100) NOT NULL,
                        email VARCHAR(100) NOT NULL,
                        fingerprint_id INT NOT NULL UNIQUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """)
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS attendance (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        student_id INT NOT NULL,
                        date DATE NOT NULL,
                        check_in_time TIME NOT NULL,
                        status VARCHAR(20) NOT NULL DEFAULT 'Present',
                        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
                        UNIQUE KEY unique_daily_attendance (student_id, date)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """)
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS system_settings (
                        settings_key VARCHAR(50) PRIMARY KEY,
                        settings_value TEXT NOT NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """)
                conn.commit()
                print("Database created from fallback python code.")
        except Error as e:
            print(f"Failed to initialize database: {e}")
            raise e
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    # --- عمليات إدارة الطلاب ---
    
    def add_student(self, academic_id, name, email, fingerprint_id):
        """إضافة طالب جديد لقاعدة البيانات"""
        conn = None
        cursor = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            query = """
                INSERT INTO students (academic_id, name, email, fingerprint_id) 
                VALUES (%s, %s, %s, %s)
            """
            cursor.execute(query, (academic_id, name, email, fingerprint_id))
            conn.commit()
            return cursor.lastrowid
        except Error as e:
            print(f"Error adding student: {e}")
            raise e
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def get_all_students(self):
        """جلب جميع الطلاب المسجلين"""
        conn = None
        cursor = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM students ORDER BY id DESC")
            return cursor.fetchall()
        except Error as e:
            print(f"Error getting students: {e}")
            return []
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def get_student_by_fingerprint(self, fingerprint_id):
        """البحث عن طالب بواسطة رقم البصمة"""
        conn = None
        cursor = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM students WHERE fingerprint_id = %s", (fingerprint_id,))
            return cursor.fetchone()
        except Error as e:
            print(f"Error getting student by fingerprint: {e}")
            return None
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def get_student_by_academic_id(self, academic_id):
        """البحث عن طالب بواسطة الرقم الجامعي"""
        conn = None
        cursor = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM students WHERE academic_id = %s", (academic_id,))
            return cursor.fetchone()
        except Error as e:
            print(f"Error getting student by academic_id: {e}")
            return None
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def delete_student(self, student_id):
        """حذف طالب وسجل حضوره تلقائياً"""
        conn = None
        cursor = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM students WHERE id = %s", (student_id,))
            conn.commit()
            return True
        except Error as e:
            print(f"Error deleting student: {e}")
            raise e
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    # --- عمليات الحضور والغياب ---
    
    def log_attendance(self, student_id, status=None):
        """تسجيل حضور طالب لليوم الحالي"""
        conn = None
        cursor = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor(dictionary=True)
            
            now = datetime.now()
            today_date = now.strftime('%Y-%m-%d')
            current_time = now.strftime('%H:%M:%S')
            
            # التحقق إذا كان الطالب قد سجل حضوراً اليوم بالفعل
            cursor.execute("SELECT * FROM attendance WHERE student_id = %s AND date = %s", (student_id, today_date))
            existing = cursor.fetchone()
            if existing:
                return {
                    'already_logged': True,
                    'record': existing
                }

            # تحديد حالة الحضور تلقائياً إذا لم يتم تحديدها
            if status is None:
                status = 'Present'
                # جلب وقت بدء المحاضرة ووقت التأخر من الإعدادات
                start_time_str = self.get_setting('attendance_time_start', '08:00:00')
                late_time_str = self.get_setting('attendance_time_late', '08:30:00')
                
                try:
                    start_time = datetime.strptime(start_time_str, '%H:%M:%S').time()
                    late_time = datetime.strptime(late_time_str, '%H:%M:%S').time()
                    now_time = now.time()
                    
                    if now_time > late_time:
                        status = 'Late'
                    elif now_time > start_time:
                        # اختياري: يمكن اعتباره Present أو Late حسب رغبة المستخدم
                        # سنعتبره Present طالما قبل وقت التأخر
                        status = 'Present'
                except Exception as ex:
                    print(f"Error comparing attendance times: {ex}")

            query = """
                INSERT INTO attendance (student_id, date, check_in_time, status) 
                VALUES (%s, %s, %s, %s)
            """
            cursor.execute(query, (student_id, today_date, current_time, status))
            conn.commit()
            
            attendance_id = cursor.lastrowid
            
            # جلب سجل الحضور كاملاً مع بيانات الطالب
            cursor.execute("""
                SELECT a.*, s.name, s.academic_id, s.email 
                FROM attendance a 
                JOIN students s ON a.student_id = s.id 
                WHERE a.id = %s
            """, (attendance_id,))
            
            return {
                'already_logged': False,
                'record': cursor.fetchone()
            }
        except Error as e:
            print(f"Error logging attendance: {e}")
            raise e
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def get_attendance_report(self, start_date=None, end_date=None, search_query=None):
        """جلب تقارير الحضور مع الفلترة والبحث"""
        conn = None
        cursor = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor(dictionary=True)
            
            query = """
                SELECT a.id as attendance_id, a.date, a.check_in_time, a.status,
                       s.id as student_id, s.name, s.academic_id, s.email, s.fingerprint_id
                FROM attendance a 
                JOIN students s ON a.student_id = s.id
                WHERE 1=1
            """
            params = []
            
            if start_date:
                query += " AND a.date >= %s"
                params.append(start_date)
            if end_date:
                query += " AND a.date <= %s"
                params.append(end_date)
            if search_query:
                query += " AND (s.name LIKE %s OR s.academic_id LIKE %s)"
                like_str = f"%{search_query}%"
                params.append(like_str)
                params.append(like_str)
                
            query += " ORDER BY a.date DESC, a.check_in_time DESC"
            cursor.execute(query, params)
            return cursor.fetchall()
        except Error as e:
            print(f"Error getting attendance report: {e}")
            return []
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def get_attendance_stats(self):
        """إحصائيات سريعة للوحة التحكم"""
        conn = None
        cursor = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor(dictionary=True)
            
            today = datetime.now().strftime('%Y-%m-%d')
            
            stats = {
                'total_students': 0,
                'present_today': 0,
                'late_today': 0,
                'absent_today': 0
            }
            
            # إجمالي الطلاب
            cursor.execute("SELECT COUNT(*) as count FROM students")
            stats['total_students'] = cursor.fetchone()['count']
            
            # الحضور والتأخر اليوم
            cursor.execute("SELECT status, COUNT(*) as count FROM attendance WHERE date = %s GROUP BY status", (today,))
            rows = cursor.fetchall()
            for row in rows:
                if row['status'] == 'Present':
                    stats['present_today'] = row['count']
                elif row['status'] == 'Late':
                    stats['late_today'] = row['count']
            
            # الغياب (الفرق بين إجمالي الطلاب والذين سجلوا حضور اليوم)
            logged_today = stats['present_today'] + stats['late_today']
            stats['absent_today'] = max(0, stats['total_students'] - logged_today)
            
            return stats
        except Error as e:
            print(f"Error getting stats: {e}")
            return {
                'total_students': 0,
                'present_today': 0,
                'late_today': 0,
                'absent_today': 0
            }
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    # --- إدارة الإعدادات ---
    
    def get_settings(self):
        """جلب جميع الإعدادات"""
        conn = None
        cursor = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT settings_key, settings_value FROM system_settings")
            rows = cursor.fetchall()
            return {row[0]: row[1] for row in rows}
        except Error as e:
            print(f"Error getting settings: {e}")
            return {}
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def get_setting(self, key, default=None):
        """جلب إعداد محدد"""
        conn = None
        cursor = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT settings_value FROM system_settings WHERE settings_key = %s", (key,))
            row = cursor.fetchone()
            if row:
                return row[0]
            return default
        except Error as e:
            print(f"Error getting setting {key}: {e}")
            return default
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def update_setting(self, key, value):
        """تحديث أو إدراج إعداد"""
        conn = None
        cursor = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            query = """
                INSERT INTO system_settings (settings_key, settings_value) 
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE settings_value = %s
            """
            cursor.execute(query, (key, str(value), str(value)))
            conn.commit()
            return True
        except Error as e:
            print(f"Error updating setting {key}: {e}")
            raise e
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
