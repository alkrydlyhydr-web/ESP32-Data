import serial
import threading
import time
from notifier import Notifier

class SerialReader:
    def __init__(self):
        self.ser = None
        self.running = False
        self.thread = None
        self.db = None
        self.ui_queue = None
        self.port = None
        self.baudrate = 115200

    def start(self, port, baudrate, db_manager, queue_obj):
        """بدء الاستماع للمنفذ التسلسلي في خيط منفصل"""
        if self.running:
            self.stop()
            
        self.port = port
        self.baudrate = int(baudrate)
        self.db = db_manager
        self.ui_queue = queue_obj
        self.running = True
        
        self.thread = threading.Thread(target=self._read_loop)
        self.thread.daemon = True
        self.thread.start()
        print(f"[Serial] Started listening on {port} at {baudrate} baud...")

    def stop(self):
        """إيقاف الاستماع وإغلاق المنفذ"""
        self.running = False
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except Exception as e:
                print(f"[Serial] Error closing port: {e}")
        if self.thread:
            self.thread.join(timeout=1.0)
        self.ser = None
        print("[Serial] Stopped listening.")

    def send_command(self, command):
        """إرسال أمر إلى ESP32 عبر السيريال (مثال: ENROLL:5)"""
        if self.ser and self.ser.is_open:
            try:
                full_command = f"{command}\n"
                self.ser.write(full_command.encode('utf-8'))
                self.ser.flush()
                print(f"[Serial] Sent command: {command}")
                return True
            except Exception as e:
                print(f"[Serial] Failed to send command '{command}': {e}")
                return False
        else:
            print("[Serial] Port is closed. Cannot send command.")
            return False

    def _read_loop(self):
        """حلقة القراءة المستمرة من السيريال"""
        while self.running:
            try:
                if not self.ser or not self.ser.is_open:
                    self.ser = serial.Serial(self.port, self.baudrate, timeout=1.0)
                    time.sleep(1.0) # انتظار استقرار الاتصال
                
                if self.ser.in_waiting > 0:
                    line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                    if line:
                        print(f"[Serial Read] Raw data: {line}")
                        self._process_message(line)
            except serial.SerialException as se:
                print(f"[Serial] Connection error on {self.port}: {se}. Retrying in 3 seconds...")
                if self.ser:
                    try:
                        self.ser.close()
                    except:
                        pass
                    self.ser = None
                time.sleep(3.0)
            except Exception as e:
                print(f"[Serial] Error in loop: {e}")
                time.sleep(1.0)
        
        # عند الخروج من الحلقة تأكد من إغلاق المنفذ
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except:
                pass

    def _process_message(self, message):
        """معالجة وتفسير الرسائل القادمة من ESP32"""
        try:
            # 1. حالة فحص البصمة وتسجيل الحضور
            if message.startswith("SCAN:"):
                fingerprint_id = int(message.split(":")[1])
                print(f"[Serial] Received scan event for fingerprint ID: {fingerprint_id}")
                
                # معالجة تسجيل الحضور
                student = self.db.get_student_by_fingerprint(fingerprint_id)
                if not student:
                    print(f"[Serial] Fingerprint ID {fingerprint_id} not registered in DB.")
                    if self.ui_queue:
                        self.ui_queue.put({
                            'type': 'unregistered_scan',
                            'fingerprint_id': fingerprint_id
                        })
                    return

                # تدوين الحضور
                result = self.db.log_attendance(student['id'])
                record = result['record']
                already_logged = result['already_logged']

                # إرسال إشعارات
                if not already_logged:
                    settings = self.db.get_settings()
                    record['email'] = student['email']
                    record['name'] = student['name']
                    record['academic_id'] = student['academic_id']
                    Notifier.send_notifications(record, settings)

                # إشعار الواجهة
                if self.ui_queue:
                    self.ui_queue.put({
                        'type': 'attendance',
                        'record': record,
                        'student_name': student['name'],
                        'already_logged': already_logged
                    })

            # 2. حالة فشل التحقق من البصمة في المستشعر
            elif message == "NO_MATCH":
                print("[Serial] Fingerprint placed but no match found on sensor.")
                if self.ui_queue:
                    self.ui_queue.put({
                        'type': 'no_match'
                    })

            # 3. حالة نجاح عملية تسجيل بصمة جديدة
            elif message.startswith("ENROLL_OK:"):
                fingerprint_id = int(message.split(":")[1])
                print(f"[Serial] Fingerprint ID {fingerprint_id} successfully enrolled.")
                if self.ui_queue:
                    self.ui_queue.put({
                        'type': 'enroll_result',
                        'status': 'success',
                        'fingerprint_id': fingerprint_id
                    })

            # 4. حالة فشل تسجيل بصمة جديدة
            elif message.startswith("ENROLL_FAIL:"):
                parts = message.split(":")
                fingerprint_id = int(parts[1])
                error_msg = parts[2] if len(parts) > 2 else "Unknown error"
                print(f"[Serial] Fingerprint ID {fingerprint_id} enrollment failed: {error_msg}")
                if self.ui_queue:
                    self.ui_queue.put({
                        'type': 'enroll_result',
                        'status': 'failed',
                        'fingerprint_id': fingerprint_id,
                        'message': error_msg
                    })

            # 5. حالة تحديثات عملية تسجيل البصمة (الخطوات البينية)
            elif message.startswith("ENROLL_STATUS:"):
                status_text = message.split(":", 1)[1]
                print(f"[Serial] Enrollment status update: {status_text}")
                if self.ui_queue:
                    self.ui_queue.put({
                        'type': 'enroll_status_update',
                        'message': status_text
                    })
                    
        except Exception as e:
            print(f"[Serial] Error processing message '{message}': {e}")
