from flask import Flask, request, jsonify
import logging
from db_manager import DatabaseManager
from notifier import Notifier

# إعداد خادم Flask
app = Flask(__name__)

# إيقاف رسائل الديباجينج المزعجة لخادم Flask في الطرفية
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# متغيرات مشتركة (تتم تهيئتها عند تشغيل الخادم)
db = None
ui_queue = None
pending_enroll_id = 0

@app.route('/api/attendance', methods=['POST'])
def api_attendance():
    """استقبال البصمة المقروءة لتسجيل الحضور"""
    global db, ui_queue
    try:
        data = request.get_json()
        if not data or 'fingerprint_id' not in data:
            return jsonify({"status": "error", "message": "Missing fingerprint_id"}), 400
            
        fingerprint_id = int(data['fingerprint_id'])
        print(f"[Flask Server] Received attendance scan for fingerprint ID: {fingerprint_id}")

        if not db:
            return jsonify({"status": "error", "message": "Database not initialized"}), 500

        # البحث عن الطالب وتدوين الحضور
        student = db.get_student_by_fingerprint(fingerprint_id)
        if not student:
            print(f"[Flask Server] Fingerprint ID {fingerprint_id} not registered in database.")
            # إشعار الواجهة ببصمة غير مسجلة
            if ui_queue:
                ui_queue.put({
                    'type': 'unregistered_scan',
                    'fingerprint_id': fingerprint_id
                })
            return jsonify({"status": "unregistered", "message": "Fingerprint not registered"}), 404

        # تدوين الحضور
        result = db.log_attendance(student['id'])
        record = result['record']
        already_logged = result['already_logged']

        # إرسال إشعار فوري (بريد إلكتروني وتلجرام) إذا لم يكن مسجلاً مسبقاً
        if not already_logged:
            settings = db.get_settings()
            # إرفاق البريد والإسم للسجل
            record['email'] = student['email']
            record['name'] = student['name']
            record['academic_id'] = student['academic_id']
            Notifier.send_notifications(record, settings)

        # إشعار الواجهة الرسومية لتحديث الشاشة فوراً
        if ui_queue:
            ui_queue.put({
                'type': 'attendance',
                'record': record,
                'student_name': student['name'],
                'already_logged': already_logged
            })

        return jsonify({
            "status": "success",
            "student_name": student['name'],
            "already_logged": already_logged
        }), 200

    except Exception as e:
        print(f"[Flask Server] Error in /api/attendance: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/check_enroll', methods=['GET'])
def api_check_enroll():
    """استعلام الـ ESP32 عما إذا كان هناك عملية تسجيل بصمة معلقة"""
    global pending_enroll_id
    # يعيد الـ ID المطلوب تسجيله، أو 0 إذا لم يكن هناك تسجيل معلق
    return jsonify({"enroll_id": pending_enroll_id}), 200


@app.route('/api/enroll_result', methods=['POST'])
def api_enroll_result():
    """استقبال نتيجة تسجيل البصمة من ESP32"""
    global pending_enroll_id, ui_queue
    try:
        data = request.get_json()
        if not data or 'status' not in data or 'fingerprint_id' not in data:
            return jsonify({"status": "error", "message": "Missing status or fingerprint_id"}), 400

        status = data['status']  # 'success' or 'failed'
        fingerprint_id = int(data['fingerprint_id'])
        error_msg = data.get('message', '')

        print(f"[Flask Server] Enrollment result for ID {fingerprint_id}: {status} ({error_msg})")

        # تصفير معرف التسجيل المعلق
        pending_enroll_id = 0

        # إرسال النتيجة إلى الواجهة الرسومية
        if ui_queue:
            ui_queue.put({
                'type': 'enroll_result',
                'status': status,
                'fingerprint_id': fingerprint_id,
                'message': error_msg
            })

        return jsonify({"status": "success"}), 200
    except Exception as e:
        print(f"[Flask Server] Error in /api/enroll_result: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


def run_server(db_manager, queue_obj, port=5000):
    """تشغيل خادم Flask (يتم استدعاء هذه الدالة في خيط منفصل Thread)"""
    global db, ui_queue
    db = db_manager
    ui_queue = queue_obj
    
    print(f"[Flask Server] Starting Flask server on port {port}...")
    try:
        app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
    except Exception as e:
        print(f"[Flask Server] Failed to start server: {e}")


def set_pending_enroll(fingerprint_id):
    """تعيين معرف البصمة المطلوب تسجيلها ليقوم الـ ESP32 بقراءتها عند الاستعلام"""
    global pending_enroll_id
    pending_enroll_id = fingerprint_id
    print(f"[Flask Server] Pending enrollment set for fingerprint ID: {pending_enroll_id}")


def cancel_pending_enroll():
    """إلغاء عملية التسجيل المعلقة"""
    global pending_enroll_id
    pending_enroll_id = 0
    print("[Flask Server] Pending enrollment cancelled")
