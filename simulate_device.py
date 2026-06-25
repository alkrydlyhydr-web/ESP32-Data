import time
import requests
import sys

# إعدادات الاتصال بالخادم المحلي
PORT = 5000
BASE_URL = f"http://localhost:{PORT}"

def print_menu():
    print("\n" + "="*50)
    print("      محاكي جهاز البصمة الذكي (Virtual ESP32)")
    print("="*50)
    print("1. إرسال عملية مسح بصمة حضور (Attendance Scan)")
    print("2. بدء فحص عمليات التسجيل المعلقة (Poll for Enrollment)")
    print("3. خروج")
    print("="*50)

def simulate_scan():
    try:
        fp_id_str = input("أدخل رقم البصمة المراد مسحها (مثال: 1): ").strip()
        if not fp_id_str:
            return
        fp_id = int(fp_id_str)
        
        print(f"جاري إرسال طلب حضور للبصمة رقم: {fp_id}...")
        url = f"{BASE_URL}/api/attendance"
        payload = {"fingerprint_id": fp_id}
        
        response = requests.post(url, json=payload, timeout=5)
        
        if response.status_code == 200:
            res_data = response.json()
            if res_data.get("already_logged"):
                print(f"ℹ️ [خادم] الطالب '{res_data.get('student_name')}' مسجل حضوره مسبقاً اليوم.")
            else:
                print(f"✅ [خادم] تم تسجيل حضور الطالب '{res_data.get('student_name')}' بنجاح!")
        elif response.status_code == 404:
            print("⚠️ [خادم] البصمة المقروءة غير مسجلة لأي طالب في النظام.")
        else:
            print(f"❌ [خطأ خادم] رمز الاستجابة: {response.status_code}, التفاصيل: {response.text}")
            
    except ValueError:
        print("❌ خطأ: يرجى إدخال رقم بصمة صحيح.")
    except requests.exceptions.ConnectionError:
        print(f"❌ خطأ اتصال: يرجى التأكد من تشغيل تطبيق البايثون الرئيسي (main_app.py) أولاً على منفذ {PORT}.")
    except Exception as e:
        print(f"❌ خطأ غير متوقع: {e}")

def simulate_enrollment_polling():
    print("\n⏳ جاري مراقبة خادم البايثون بحثاً عن عمليات تسجيل معلقة...")
    print("لتسجيل بصمة: اذهب لصفحة 'تسجيل الطلاب' في التطبيق واضغط 'بدء تسجيل البصمة'")
    print("اضغط Ctrl+C للعودة للقائمة الرئيسية في أي وقت.")
    
    url_check = f"{BASE_URL}/api/check_enroll"
    url_result = f"{BASE_URL}/api/enroll_result"
    
    try:
        while True:
            response = requests.get(url_check, timeout=3)
            if response.status_code == 200:
                data = response.json()
                enroll_id = data.get("enroll_id", 0)
                
                if enroll_id > 0:
                    print(f"\n⚡ تم اكتشاف طلب تسجيل بصمة جديد للمعرف: {enroll_id}!")
                    print("من فضلك اختر نتيجة المحاكاة:")
                    print("S) محاكاة نجاح البصمة (Success)")
                    print("F) محاكاة فشل البصمة (Failure)")
                    
                    choice = ""
                    while choice not in ['s', 'f']:
                        choice = input("خيارك (S/F): ").strip().lower()
                    
                    if choice == 's':
                        # إرسال نتيجة نجاح
                        payload = {"status": "success", "fingerprint_id": enroll_id}
                        requests.post(url_result, json=payload, timeout=5)
                        print(f"✅ تم إرسال نتيجة النجاح للبصمة رقم {enroll_id} بنجاح إلى التطبيق.")
                    else:
                        # إرسال نتيجة فشل
                        reason = input("أدخل سبب الفشل (افتراضي: لم تتطابق البصمتان): ").strip()
                        if not reason:
                            reason = "Fingerprints did not match. Try again"
                        payload = {"status": "failed", "fingerprint_id": enroll_id, "message": reason}
                        requests.post(url_result, json=payload, timeout=5)
                        print(f"❌ تم إرسال نتيجة الفشل للبصمة رقم {enroll_id} بنجاح.")
                    
                    print("\n⏳ العودة لمراقبة الطلبات...")
            
            time.sleep(2) # فحص كل ثانيتين
    except KeyboardInterrupt:
        print("\nتم إيقاف المراقبة والعودة للقائمة.")
    except requests.exceptions.ConnectionError:
        print(f"❌ خطأ اتصال: يرجى التأكد من تشغيل تطبيق البايثون الرئيسي (main_app.py) أولاً على منفذ {PORT}.")
    except Exception as e:
        print(f"❌ خطأ غير متوقع: {e}")

def main():
    while True:
        print_menu()
        choice = input("أدخل رقم خيارك: ").strip()
        
        if choice == "1":
            simulate_scan()
        elif choice == "2":
            simulate_enrollment_polling()
        elif choice == "3":
            print("شكراً لاستخدام محاكي البصمة. مع السلامة!")
            sys.exit(0)
        else:
            print("❌ خيار غير صحيح، يرجى إدخال 1 أو 2 أو 3.")
        
        input("\nاضغط Enter للمتابعة...")

if __name__ == "__main__":
    main()
