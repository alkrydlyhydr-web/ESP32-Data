import os
import sys
import queue
import socket
import threading
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import filedialog, messagebox
def reverse_words(text):
    # يقوم بعكس ترتيب الكلمات (تحويل: محمد حيدر علي -> علي حيدر محمد)
    words = text.split()
    return " ".join(reversed(words))


# استيراد مكتبة CustomTkinter لتصميم الواجهات الحديثة
try:
    import customtkinter as ctk
except ImportError:
    import subprocess
    print("Installing customtkinter...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "customtkinter"])
    import customtkinter as ctk

# استيراد الوحدات الخاصة بالنظام
from db_manager import DatabaseManager
import flask_server
from serial_reader import SerialReader
from report_generator import ReportGenerator

# إعداد المظهر الأساسي للبرنامج (Dark theme with Blue accents)
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class StudentAttendanceApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("نظام تسجيل الحضور بالبصمة الذكي")
        self.geometry("1150x700")
        self.resizable(True, True)

        # تهيئة قاعدة البيانات
        self.db = DatabaseManager()
        try:
            self.db.initialize_database()
        except Exception as e:
            messagebox.showerror(
                "خطأ في الاتصال", 
                f"فشل الاتصال بقاعدة بيانات MySQL الملحية.\nيرجى التأكد من تشغيل خادم MySQL (مثل XAMPP) ثم إعادة المحاولة.\nالخطأ: {e}"
            )
            sys.exit(1)

        # تحميل الإعدادات من قاعدة البيانات
        self.settings = self.db.get_settings()
        
        # إنشاء صف أحداث لتحديث الواجهة من الخيوط الأخرى (Threads) بشكل آمن
        self.ui_queue = queue.Queue()

        # إعداد قارئ السيريال
        self.serial_reader = SerialReader()

        # تشغيل الخدمات الخلفية (Flask و Serial)
        self.start_background_services()

        # بناء هيكل الواجهة
        self.setup_layout()

        # بدء مؤقت فحص الأحداث من صف الانتظار (Queue)
        self.after(100, self.process_queue)

        # تحديث لوحة التحكم دورياً
        self.update_dashboard_stats()

    def make_entry_rtl_compatible(self, entry_widget):
        """تهيئة حقل الإدخال ليدعم الكتابة باللغة العربية من اليمين لليسار مع الحفاظ على ترتيب الكلمات"""
        # الحصول على عنصر tk.Entry الداخلي لمكتبة CustomTkinter لضمان استجابة الأحداث مباشرة
        tk_entry = entry_widget._entry if hasattr(entry_widget, '_entry') else entry_widget
        
        # ضبط المحاذاة لليمين
        entry_widget.configure(justify="right")
        
        # متغير لتتبع ما إذا كان المستخدم يقوم بتعديل النص في المنتصف يدوياً
        entry_widget._manual_cursor = False
        
        def on_click(event):
            def check_click():
                try:
                    current_pos = tk_entry.index(tk.INSERT)
                    text_len = len(tk_entry.get())
                    # إذا نقر المستخدم في منتصف النص، نُفعل الوضع اليدوي لتجنب سحب المؤشر للنهاية
                    if current_pos < text_len:
                        entry_widget._manual_cursor = True
                    else:
                        entry_widget._manual_cursor = False
                except Exception:
                    pass
            tk_entry.after(10, check_click)
            
        def on_navigation(event):
            # عند استخدام الأسهم أو أزرار الانتقال، نُفعل الوضع اليدوي
            entry_widget._manual_cursor = True
            
        def on_key_press(event):
            try:
                # إذا كان الحقل فارغاً، نعيد تعيين الوضع التلقائي
                if len(tk_entry.get()) == 0:
                    entry_widget._manual_cursor = False
            except Exception:
                pass
            
                
            # def apply_correction():
            #     try:
            #         # إذا لم نكن في الوضع اليدوي، نجبر المؤشر على البقاء في النهاية لمنع قفزات RTL
            #         if not entry_widget._manual_cursor:
            #             tk_entry.icursor(tk.END)
            #     except Exception:
            #         pass
            # tk_entry.after(10, apply_correction)
            
            
        tk_entry.bind("<Button-1>", on_click, add="+")
        tk_entry.bind("<KeyPress-Left>", on_navigation, add="+")
        tk_entry.bind("<KeyPress-Right>", on_navigation, add="+")
        tk_entry.bind("<KeyPress-Home>", on_navigation, add="+")
        tk_entry.bind("<KeyPress-End>", on_click, add="+")
        tk_entry.bind("<KeyPress>", on_key_press, add="+")

    def get_local_ip(self):
        """جلب عنوان الـ IP المحلي للحاسوب لتسهيل ربط الـ ESP32 عبر الواي فاي"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def start_background_services(self):
        """تشغيل خادم الـ Flask وقارئ السيريال"""
        # 1. تشغيل خادم Flask المصغر لاستقبال اتصالات الـ Wi-Fi
        flask_port = int(self.settings.get('flask_port', 5000))
        self.flask_thread = threading.Thread(
            target=flask_server.run_server,
            args=(self.db, self.ui_queue, flask_port)
        )
        self.flask_thread.daemon = True
        self.flask_thread.start()

        # 2. تشغيل قارئ السيريال للاتصال السلكي
        serial_port = self.settings.get('serial_port', '')
        baudrate = self.settings.get('serial_baudrate', '115200')
        self.serial_reader.start(serial_port, baudrate, self.db, self.ui_queue)

    def setup_layout(self):
        """إعداد التخطيط الهيكلي للواجهة (شريط جانبي يمين، محتوى يسار)"""
        # استخدام نظام التخطيط الشبكي (Grid)
        self.grid_columnconfigure(0, weight=1)  # المحتوى الرئيسي
        self.grid_columnconfigure(1, weight=0)  # الشريط الجانبي (RTL)
        self.grid_rowconfigure(0, weight=1)

        # --- شريط التنقل الجانبي الأيمن ---
        self.sidebar_frame = ctk.CTkFrame(self, width=220, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=1, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(5, weight=1)

        # عنوان البرنامج في الشريط الجانبي
        self.logo_label = ctk.CTkLabel(
            self.sidebar_frame, 
            text="نظام البصمة الذكي", 
            font=ctk.CTkFont(size=20, weight="bold")
        )
        self.logo_label.grid(row=0, column=0, padx=20, pady=20)

        # أزرار التنقل
        self.btn_dashboard = ctk.CTkButton(
            self.sidebar_frame, text="لوحة التحكم", 
            fg_color="transparent", text_color=("gray10", "gray90"), 
            hover_color=("gray70", "gray30"), anchor="e",
            command=lambda: self.select_frame("dashboard")
        )
        self.btn_dashboard.grid(row=1, column=0, sticky="ew", padx=10, pady=5)

        self.btn_register = ctk.CTkButton(
            self.sidebar_frame, text="تسجيل الطلاب", 
            fg_color="transparent", text_color=("gray10", "gray90"), 
            hover_color=("gray70", "gray30"), anchor="e",
            command=lambda: self.select_frame("register")
        )
        self.btn_register.grid(row=2, column=0, sticky="ew", padx=10, pady=5)

        self.btn_reports = ctk.CTkButton(
            self.sidebar_frame, text="تقارير الحضور", 
            fg_color="transparent", text_color=("gray10", "gray90"), 
            hover_color=("gray70", "gray30"), anchor="e",
            command=lambda: self.select_frame("reports")
        )
        self.btn_reports.grid(row=3, column=0, sticky="ew", padx=10, pady=5)

        self.btn_settings = ctk.CTkButton(
            self.sidebar_frame, text="إعدادات النظام", 
            fg_color="transparent", text_color=("gray10", "gray90"), 
            hover_color=("gray70", "gray30"), anchor="e",
            command=lambda: self.select_frame("settings")
        )
        self.btn_settings.grid(row=4, column=0, sticky="ew", padx=10, pady=5)

        # معلومات الاتصال السريعة أسفل الشريط الجانبي
        self.info_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        self.info_frame.grid(row=6, column=0, sticky="ew", padx=10, pady=20)
        
        self.lbl_ip_info = ctk.CTkLabel(
            self.info_frame, 
            text=f"IP خادم الواي فاي:\n{self.get_local_ip()}:{self.settings.get('flask_port', '5000')}", 
            font=ctk.CTkFont(size=11), text_color="gray60"
        )
        self.lbl_ip_info.pack(pady=5)
        
        self.lbl_com_info = ctk.CTkLabel(
            self.info_frame, 
            text=f"منفذ USB السلكي:\n{self.settings.get('serial_port', 'com8')}", 
            font=ctk.CTkFont(size=11), text_color="gray60"
        )
        self.lbl_com_info.pack(pady=5)

        # --- إطارات الصفحات المختلفة ---
        self.create_dashboard_frame()
        self.create_register_frame()
        self.create_reports_frame()
        self.create_settings_frame()

        # فتح لوحة التحكم افتراضياً
        self.select_frame("dashboard")

    def select_frame(self, name):
        """التبديل بين الصفحات وتغيير لون الزر النشط في الشريط الجانبي"""
        # إعادة تصفير ألوان الأزرار
        self.btn_dashboard.configure(fg_color="transparent")
        self.btn_register.configure(fg_color="transparent")
        self.btn_reports.configure(fg_color="transparent")
        self.btn_settings.configure(fg_color="transparent")

        # إخفاء كافة الإطارات
        self.frame_dashboard.grid_forget()
        self.frame_register.grid_forget()
        self.frame_reports.grid_forget()
        self.frame_settings.grid_forget()

        # إظهار الإطار المحدد وتلوين زره
        if name == "dashboard":
            self.btn_dashboard.configure(fg_color=("gray75", "gray25"))
            self.frame_dashboard.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
            self.update_dashboard_stats()
        elif name == "register":
            self.btn_register.configure(fg_color=("gray75", "gray25"))
            self.frame_register.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
            self.refresh_students_table()
        elif name == "reports":
            self.btn_reports.configure(fg_color=("gray75", "gray25"))
            self.frame_reports.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
            self.load_attendance_report()
        elif name == "settings":
            self.btn_settings.configure(fg_color=("gray75", "gray25"))
            self.frame_settings.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)

    # ==========================================
    # 1. صفحة لوحة التحكم (Dashboard Screen)
    # ==========================================
    def create_dashboard_frame(self):
        self.frame_dashboard = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_dashboard.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self.frame_dashboard.grid_rowconfigure(2, weight=1)

        # عنوان الصفحة
        lbl_title = ctk.CTkLabel(self.frame_dashboard, text="لوحة التحكم العامة", font=ctk.CTkFont(size=22, weight="bold"))
        lbl_title.grid(row=0, column=0, columnspan=4, sticky="e", pady=10)

        # كروت الإحصائيات (Stat Cards)
        # كارت إجمالي الطلاب
        self.card_total = ctk.CTkFrame(self.frame_dashboard, height=100)
        self.card_total.grid(row=1, column=3, padx=10, pady=10, sticky="nsew")
        self.lbl_stat_total_val = ctk.CTkLabel(self.card_total, text="0", font=ctk.CTkFont(size=30, weight="bold"), text_color="#1a73e8")
        self.lbl_stat_total_val.pack(pady=(15, 2))
        lbl_stat_total_lbl = ctk.CTkLabel(self.card_total, text="إجمالي الطلاب المسجلين", font=ctk.CTkFont(size=12))
        lbl_stat_total_lbl.pack(pady=(0, 15))

        # كارت الحاضرين اليوم
        self.card_present = ctk.CTkFrame(self.frame_dashboard, height=100)
        self.card_present.grid(row=1, column=2, padx=10, pady=10, sticky="nsew")
        self.lbl_stat_present_val = ctk.CTkLabel(self.card_present, text="0", font=ctk.CTkFont(size=30, weight="bold"), text_color="#2ec4b6")
        self.lbl_stat_present_val.pack(pady=(15, 2))
        lbl_stat_present_lbl = ctk.CTkLabel(self.card_present, text="حضور اليوم", font=ctk.CTkFont(size=12))
        lbl_stat_present_lbl.pack(pady=(0, 15))

        # كارت المتأخرين اليوم
        self.card_late = ctk.CTkFrame(self.frame_dashboard, height=100)
        self.card_late.grid(row=1, column=1, padx=10, pady=10, sticky="nsew")
        self.lbl_stat_late_val = ctk.CTkLabel(self.card_late, text="0", font=ctk.CTkFont(size=30, weight="bold"), text_color="#ff9f1c")
        self.lbl_stat_late_val.pack(pady=(15, 2))
        lbl_stat_late_lbl = ctk.CTkLabel(self.card_late, text="متأخر اليوم", font=ctk.CTkFont(size=12))
        lbl_stat_late_lbl.pack(pady=(0, 15))

        # كارت الغياب اليوم
        self.card_absent = ctk.CTkFrame(self.frame_dashboard, height=100)
        self.card_absent.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        self.lbl_stat_absent_val = ctk.CTkLabel(self.card_absent, text="0", font=ctk.CTkFont(size=30, weight="bold"), text_color="#e71d36")
        self.lbl_stat_absent_val.pack(pady=(15, 2))
        lbl_stat_absent_lbl = ctk.CTkLabel(self.card_absent, text="غياب اليوم (تقديري)", font=ctk.CTkFont(size=12))
        lbl_stat_absent_lbl.pack(pady=(0, 15))

        # قائمة آخر القراءات / الحضور اليومي الفوري
        self.recent_scans_frame = ctk.CTkFrame(self.frame_dashboard)
        self.recent_scans_frame.grid(row=2, column=0, columnspan=4, sticky="nsew", pady=15)
        
        lbl_scans_title = ctk.CTkLabel(self.recent_scans_frame, text="سجل الحضور الفوري المباشر (اليوم)", font=ctk.CTkFont(size=15, weight="bold"))
        lbl_scans_title.pack(anchor="e", padx=15, pady=10)

        # صندوق قابل للتمرير لعرض السجلات
        self.scans_scrollable = ctk.CTkScrollableFrame(self.recent_scans_frame, height=320)
        self.scans_scrollable.pack(fill="both", expand=True, padx=10, pady=5)

    def update_dashboard_stats(self):
        """تحديث بيانات الإحصائيات وجلب الحضور لليوم الحالي"""
        stats = self.db.get_attendance_stats()
        self.lbl_stat_total_val.configure(text=str(stats['total_students']))
        self.lbl_stat_present_val.configure(text=str(stats['present_today']))
        self.lbl_stat_late_val.configure(text=str(stats['late_today']))
        self.lbl_stat_absent_val.configure(text=str(stats['absent_today']))

        # إفراغ وعرض آخر قراءات اليوم
        for widget in self.scans_scrollable.winfo_children():
            widget.destroy()

        today_attendance = self.db.get_attendance_report(
            start_date=datetime.now().strftime('%Y-%m-%d'),
            end_date=datetime.now().strftime('%Y-%m-%d')
        )

        if not today_attendance:
            lbl_no_scans = ctk.CTkLabel(self.scans_scrollable, text="لا يوجد حضور مسجل اليوم حتى الآن. بانتظار مسح البصمات...", text_color="gray50")
            lbl_no_scans.pack(pady=40)
        else:
            # رؤوس أعمدة السجل السريع
            header_row = ctk.CTkFrame(self.scans_scrollable, fg_color="gray20", height=35)
            header_row.pack(fill="x", pady=2)
            
            ctk.CTkLabel(header_row, text="الحالة", font=ctk.CTkFont(weight="bold"), width=100).pack(side="left", padx=15)
            ctk.CTkLabel(header_row, text="وقت الدخول", font=ctk.CTkFont(weight="bold"), width=120).pack(side="left", padx=15)
            ctk.CTkLabel(header_row, text="الرقم الأكاديمي", font=ctk.CTkFont(weight="bold"), width=150).pack(side="right", padx=15)
            ctk.CTkLabel(header_row, text="اسم الطالب", font=ctk.CTkFont(weight="bold"), width=200).pack(side="right", padx=15)

            for rec in today_attendance:
                row_item = ctk.CTkFrame(self.scans_scrollable, fg_color="transparent")
                row_item.pack(fill="x", pady=2)
                
                # لون وتسمية الحالة بالعربية
                status_val = rec.get('status')
                status_ar = 'حاضر' if status_val == 'Present' else 'متأخر' if status_val == 'Late' else 'غائب'
                status_color = "#2ec4b6" if status_val == 'Present' else "#ff9f1c" if status_val == 'Late' else "#e71d36"

                lbl_status = ctk.CTkLabel(row_item, text=status_ar, text_color=status_color, font=ctk.CTkFont(weight="bold"), width=100)
                lbl_status.pack(side="left", padx=15)
                
                lbl_time = ctk.CTkLabel(row_item, text=str(rec.get('check_in_time')), width=120)
                lbl_time.pack(side="left", padx=15)
                
                lbl_acid = ctk.CTkLabel(row_item, text=rec.get('academic_id'), width=150)
                lbl_acid.pack(side="right", padx=15)
                
                lbl_name = ctk.CTkLabel(row_item, text=rec.get('name'), anchor="w", width=200)
                lbl_name.pack(side="right", padx=15)

    # ==========================================
    # 2. صفحة تسجيل الطلاب (Register Screen)
    # ==========================================
    def create_register_frame(self):
        self.frame_register = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_register.grid_columnconfigure(0, weight=3) # جدول الطلاب
        self.frame_register.grid_columnconfigure(1, weight=2) # نموذج الإدخال
        self.frame_register.grid_rowconfigure(1, weight=1)

        # عنوان الصفحة
        lbl_title = ctk.CTkLabel(self.frame_register, text="تسجيل الطلاب والتبصيم", font=ctk.CTkFont(size=22, weight="bold"))
        lbl_title.grid(row=0, column=0, columnspan=2, sticky="e", pady=10)

        # --- الجزء الأيمن: نموذج الإدخال والتسجيل ---
        self.form_frame = ctk.CTkFrame(self.frame_register)
        self.form_frame.grid(row=1, column=1, sticky="nsew", padx=(10, 0), pady=10)

        lbl_form_title = ctk.CTkLabel(self.form_frame, text="بيانات الطالب الجديد", font=ctk.CTkFont(size=15, weight="bold"))
        lbl_form_title.pack(anchor="e", padx=15, pady=15)

        # حقل الاسم
        self.entry_name = ctk.CTkEntry(self.form_frame, placeholder_text="الاسم الكامل للطالب", placeholder_text_color="gray50")
        self.make_entry_rtl_compatible(self.entry_name)
        self.entry_name.pack(fill="x", padx=20, pady=10)

        # حقل الرقم الجامعي
        self.entry_academic_id = ctk.CTkEntry(self.form_frame, placeholder_text="الرقم الأكاديمي / الجامعي", placeholder_text_color="gray50")
        self.make_entry_rtl_compatible(self.entry_academic_id)
        self.entry_academic_id.pack(fill="x", padx=20, pady=10)

        # حقل البريد
        self.entry_email = ctk.CTkEntry(self.form_frame, placeholder_text="البريد الإلكتروني للإشعارات", placeholder_text_color="gray50")
        self.make_entry_rtl_compatible(self.entry_email)
        self.entry_email.pack(fill="x", padx=20, pady=10)

        # حقل رقم البصمة
        lbl_fp_hint = ctk.CTkLabel(self.form_frame, text="رقم البصمة في الذاكرة (1 - 127)", font=ctk.CTkFont(size=11), text_color="gray60")
        lbl_fp_hint.pack(anchor="e", padx=20, pady=(10, 0))
        
        self.entry_fp_id = ctk.CTkEntry(self.form_frame, placeholder_text="رقم البصمة")
        self.make_entry_rtl_compatible(self.entry_fp_id)
        self.entry_fp_id.insert(0, "1") # قيمة افتراضية
        self.entry_fp_id.pack(fill="x", padx=20, pady=(0, 10))

        # زر بدء عملية التبصيم وتسجيل الهاردوير
        self.btn_enroll_hardware = ctk.CTkButton(
            self.form_frame, text="بدء تسجيل البصمة على الجهاز 👆",
            fg_color="#ff9f1c", hover_color="#e58f19", text_color="black",
            command=self.start_fingerprint_enrollment
        )
        self.btn_enroll_hardware.pack(fill="x", padx=20, pady=15)

        self.lbl_enroll_status = ctk.CTkLabel(self.form_frame, text="", font=ctk.CTkFont(size=12, weight="bold"))
        self.lbl_enroll_status.pack(pady=5)

        # زر حفظ وحفظ الطالب بقاعدة البيانات
        self.btn_save_student = ctk.CTkButton(
            self.form_frame, text="حفظ بيانات الطالب بقاعدة البيانات 💾",
            fg_color="#1a73e8", hover_color="#155cb4",
            command=self.save_student_to_db,
            state="disabled" # يتم تفعيله فقط بعد نجاح التبصيم الفعلي
        )
        self.btn_save_student.pack(fill="x", padx=20, pady=10)

        # --- الجزء الأيسر: عرض الطلاب المسجلين ---
        self.list_frame = ctk.CTkFrame(self.frame_register)
        self.list_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 10), pady=10)

        lbl_list_title = ctk.CTkLabel(self.list_frame, text="الطلاب المسجلين بالنظام", font=ctk.CTkFont(size=15, weight="bold"))
        lbl_list_title.pack(anchor="e", padx=15, pady=10)

        # مربع بحث سريع
        self.entry_search_student = ctk.CTkEntry(self.list_frame, placeholder_text="ابحث باسم الطالب أو الرقم الأكاديمي...")
        self.make_entry_rtl_compatible(self.entry_search_student)
        self.entry_search_student.pack(fill="x", padx=15, pady=5)
        self.entry_search_student.bind("<KeyRelease>", lambda e: self.refresh_students_table())

        # جدول الطلاب القابل للتمرير
        self.students_scrollable = ctk.CTkScrollableFrame(self.list_frame, height=350)
        self.students_scrollable.pack(fill="both", expand=True, padx=10, pady=10)

    def start_fingerprint_enrollment(self):
        """بدء عملية تبصيم الطالب على جهاز الـ ESP32"""
        # التحقق من المدخلات الأساسية
        name = self.entry_name.get().strip()
        academic_id = self.entry_academic_id.get().strip()
        email = self.entry_email.get().strip()
        fp_id_str = self.entry_fp_id.get().strip()

        if not name or not academic_id or not email or not fp_id_str:
            messagebox.showwarning("تنبيه", "يرجى ملء جميع الحقول أولاً قبل بدء عملية تسجيل البصمة.")
            return

        try:
            fp_id = int(fp_id_str)
            if fp_id < 1 or fp_id > 127:
                raise ValueError()
        except ValueError:
            messagebox.showwarning("تنبيه", "يجب أن يكون رقم البصمة عدداً صحيحاً بين 1 و 127.")
            return

        # التحقق من أن رقم البصمة أو الرقم الأكاديمي غير مكرر في قاعدة البيانات
        if self.db.get_student_by_academic_id(academic_id):
            messagebox.showwarning("تنبيه", "الرقم الأكاديمي مسجل بالفعل لطالب آخر.")
            return
        if self.db.get_student_by_fingerprint(fp_id):
            messagebox.showwarning("تنبيه", "رقم البصمة محجوز بالفعل لطالب آخر.")
            return

        # تعيين رقم التسجيل المعلق (لخادم Flask) أو إرساله سلكياً
        flask_server.set_pending_enroll(fp_id)
        
        # إرسال الأمر سلكياً أيضاً (في حال كان الاتصال سلكياً)
        sent_serial = self.serial_reader.send_command(f"ENROLL:{fp_id}")
        
        # تحديث الواجهة لبدء الانتظار
        self.lbl_enroll_status.configure(
            text="⏳ يرجى وضع الإصبع على جهاز البصمة الآن...", 
            text_color="#ff9f1c"
        )
        self.btn_enroll_hardware.configure(state="disabled")
        self.entry_name.configure(state="disabled")
        self.entry_academic_id.configure(state="disabled")
        self.entry_email.configure(state="disabled")
        self.entry_fp_id.configure(state="disabled")

    def save_student_to_db(self):
        """حفظ بيانات الطالب في قاعدة البيانات بعد تبصيمه بنجاح"""
        name = self.entry_name.get().strip()
        academic_id = self.entry_academic_id.get().strip()
        email = self.entry_email.get().strip()
        fp_id = int(self.entry_fp_id.get().strip())

        try:
            # إدخال في قاعدة البيانات
            self.db.add_student(academic_id, name, email, fp_id)
            messagebox.showinfo("نجاح", f"تم تسجيل الطالب '{name}' بنجاح في النظام.")
            
            # إعادة تهيئة النموذج
            self.entry_name.configure(state="normal")
            self.entry_academic_id.configure(state="normal")
            self.entry_email.configure(state="normal")
            self.entry_fp_id.configure(state="normal")
            
            self.entry_name.delete(0, tk.END)
            self.entry_academic_id.delete(0, tk.END)
            self.entry_email.delete(0, tk.END)
            self.entry_fp_id.delete(0, tk.END)
            
            self.lbl_enroll_status.configure(text="")
            self.btn_enroll_hardware.configure(state="normal")
            self.btn_save_student.configure(state="disabled")
            
            # تحديث الجداول والإحصائيات
            self.refresh_students_table()
            self.update_dashboard_stats()
        except Exception as e:
            messagebox.showerror("خطأ", f"فشل حفظ البيانات: {e}")

    def refresh_students_table(self):
        """تحديث جدول الطلاب المسجلين باليسار"""
        for widget in self.students_scrollable.winfo_children():
            widget.destroy()

        search_q = self.entry_search_student.get().strip()
        all_students = self.db.get_all_students()
        
        # تصفية الطلاب بناء على مربع البحث
        if search_q:
            filtered = []
            for s in all_students:
                if search_q in s['name'] or search_q in s['academic_id']:
                    filtered.append(s)
            all_students = filtered

        if not all_students:
            lbl_empty = ctk.CTkLabel(self.students_scrollable, text="لا يوجد طلاب مسجلين مطابقة للبحث.", text_color="gray50")
            lbl_empty.pack(pady=30)
            return

        # رؤوس الأعمدة
        header_row = ctk.CTkFrame(self.students_scrollable, fg_color="gray20", height=30)
        header_row.pack(fill="x", pady=2)
        
        ctk.CTkLabel(header_row, text="حذف", font=ctk.CTkFont(weight="bold"), width=60).pack(side="left", padx=10)
        ctk.CTkLabel(header_row, text="البصمة", font=ctk.CTkFont(weight="bold"), width=60).pack(side="left", padx=10)
        ctk.CTkLabel(header_row, text="الرقم الأكاديمي", font=ctk.CTkFont(weight="bold"), width=120).pack(side="right", padx=10)
        ctk.CTkLabel(header_row, text="اسم الطالب", font=ctk.CTkFont(weight="bold"), width=180).pack(side="right", padx=10)

        for s in all_students:
            row_item = ctk.CTkFrame(self.students_scrollable, fg_color="transparent")
            row_item.pack(fill="x", pady=2)

            btn_del = ctk.CTkButton(
                row_item, text="🗑️", width=35, height=25, 
                fg_color="#e71d36", hover_color="#c1121f",
                command=lambda student_id=s['id'], student_name=s['name']: self.delete_student_clicked(student_id, student_name)
            )
            btn_del.pack(side="left", padx=10)
            
            lbl_fp = ctk.CTkLabel(row_item, text=str(s['fingerprint_id']), width=60)
            lbl_fp.pack(side="left", padx=10)

            lbl_acid = ctk.CTkLabel(row_item, text=s['academic_id'], width=120)
            lbl_acid.pack(side="right", padx=10)

            lbl_name = ctk.CTkLabel(row_item, text=s['name'], anchor="w", width=180)
            lbl_name.pack(side="right", padx=10)

    def delete_student_clicked(self, student_id, student_name):
        """حذف طالب"""
        if messagebox.askyesno("تأكيد الحذف", f"هل أنت متأكد من حذف الطالب '{student_name}'؟ سيؤدي ذلك لحذف سجل حضوره بالكامل!"):
            try:
                self.db.delete_student(student_id)
                self.refresh_students_table()
                self.update_dashboard_stats()
            except Exception as e:
                messagebox.showerror("خطأ", f"فشل حذف الطالب: {e}")

    # ==========================================
    # 3. صفحة تقارير الحضور (Reports Screen)
    # ==========================================
    def create_reports_frame(self):
        self.frame_reports = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_reports.grid_columnconfigure(0, weight=1)
        self.frame_reports.grid_rowconfigure(2, weight=1)

        # عنوان الصفحة
        lbl_title = ctk.CTkLabel(self.frame_reports, text="تقارير الحضور والغياب الشاملة", font=ctk.CTkFont(size=22, weight="bold"))
        lbl_title.grid(row=0, column=0, sticky="e", pady=10)

        # شريط الفلترة والأزرار
        self.filter_frame = ctk.CTkFrame(self.frame_reports)
        self.filter_frame.grid(row=1, column=0, sticky="ew", pady=10)

        # زر تصدير PDF
        self.btn_export_pdf = ctk.CTkButton(
            self.filter_frame, text="تصدير PDF 📄", 
            fg_color="#e71d36", hover_color="#c1121f", width=110,
            command=self.export_report_pdf
        )
        self.btn_export_pdf.pack(side="left", padx=10, pady=10)

        # زر تصدير Excel
        self.btn_export_excel = ctk.CTkButton(
            self.filter_frame, text="تصدير Excel 📊", 
            fg_color="#2ec4b6", hover_color="#209a8f", text_color="black", width=110,
            command=self.export_report_excel
        )
        self.btn_export_excel.pack(side="left", padx=10, pady=10)

        # حقل البحث باسم الطالب
        self.entry_search_report = ctk.CTkEntry(self.filter_frame, placeholder_text="البحث بالاسم أو الرقم الأكاديمي...", width=200)
        self.make_entry_rtl_compatible(self.entry_search_report)
        self.entry_search_report.pack(side="right", padx=10, pady=10)
        self.entry_search_report.bind("<KeyRelease>", lambda e: self.load_attendance_report())

        # فلتر التاريخ
        self.entry_end_date = ctk.CTkEntry(self.filter_frame, placeholder_text="تاريخ النهاية YYYY-MM-DD", width=150, justify="center")
        self.entry_end_date.insert(0, datetime.now().strftime('%Y-%m-%d'))
        self.entry_end_date.pack(side="right", padx=10, pady=10)
        self.entry_end_date.bind("<KeyRelease>", lambda e: self.load_attendance_report())

        lbl_to = ctk.CTkLabel(self.filter_frame, text="إلى")
        lbl_to.pack(side="right", padx=2)

        self.entry_start_date = ctk.CTkEntry(self.filter_frame, placeholder_text="تاريخ البدء YYYY-MM-DD", width=150, justify="center")
        self.entry_start_date.insert(0, (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'))
        self.entry_start_date.pack(side="right", padx=10, pady=10)
        self.entry_start_date.bind("<KeyRelease>", lambda e: self.load_attendance_report())

        lbl_from = ctk.CTkLabel(self.filter_frame, text="من")
        lbl_from.pack(side="right", padx=2)

        # جدول عرض التقارير القابل للتمرير
        self.reports_scrollable = ctk.CTkScrollableFrame(self.frame_reports)
        self.reports_scrollable.grid(row=2, column=0, sticky="nsew", pady=10)

        self.current_report_data = []

    def load_attendance_report(self):
        """تحميل وتصفية تقرير الحضور بناء على محددات البحث والتاريخ"""
        for widget in self.reports_scrollable.winfo_children():
            widget.destroy()

        start = self.entry_start_date.get().strip()
        end = self.entry_end_date.get().strip()
        query = self.entry_search_report.get().strip()

        # تأكيد تنسيق التواريخ المدخلة لتجنب الأخطاء
        start_date = None
        end_date = None
        
        try:
            if start:
                datetime.strptime(start, '%Y-%m-%d')
                start_date = start
        except ValueError:
            pass

        try:
            if end:
                datetime.strptime(end, '%Y-%m-%d')
                end_date = end
        except ValueError:
            pass

        # جلب البيانات
        self.current_report_data = self.db.get_attendance_report(
            start_date=start_date,
            end_date=end_date,
            search_query=query if query else None
        )

        if not self.current_report_data:
            lbl_empty = ctk.CTkLabel(self.reports_scrollable, text="لا توجد سجلات حضور مطابقة للمواصفات المحددة.", text_color="gray50")
            lbl_empty.pack(pady=40)
            return

        # رؤوس أعمدة الجدول
        header_row = ctk.CTkFrame(self.reports_scrollable, fg_color="gray20", height=30)
        header_row.pack(fill="x", pady=2)
        
        ctk.CTkLabel(header_row, text="الحالة", font=ctk.CTkFont(weight="bold"), width=80).pack(side="left", padx=10)
        ctk.CTkLabel(header_row, text="وقت الحضور", font=ctk.CTkFont(weight="bold"), width=100).pack(side="left", padx=10)
        ctk.CTkLabel(header_row, text="التاريخ", font=ctk.CTkFont(weight="bold"), width=110).pack(side="left", padx=10)
        ctk.CTkLabel(header_row, text="البصمة", font=ctk.CTkFont(weight="bold"), width=60).pack(side="left", padx=10)
        ctk.CTkLabel(header_row, text="الرقم الأكاديمي", font=ctk.CTkFont(weight="bold"), width=120).pack(side="right", padx=10)
        ctk.CTkLabel(header_row, text="اسم الطالب", font=ctk.CTkFont(weight="bold"), width=180).pack(side="right", padx=10)

        for rec in self.current_report_data:
            row_item = ctk.CTkFrame(self.reports_scrollable, fg_color="transparent")
            row_item.pack(fill="x", pady=2)

            status_val = rec.get('status')
            status_ar = 'حاضر' if status_val == 'Present' else 'متأخر' if status_val == 'Late' else 'غائب'
            status_color = "#2ec4b6" if status_val == 'Present' else "#ff9f1c" if status_val == 'Late' else "#e71d36"

            lbl_status = ctk.CTkLabel(row_item, text=status_ar, text_color=status_color, font=ctk.CTkFont(weight="bold"), width=80)
            lbl_status.pack(side="left", padx=10)

            lbl_time = ctk.CTkLabel(row_item, text=str(rec.get('check_in_time')), width=100)
            lbl_time.pack(side="left", padx=10)

            lbl_date = ctk.CTkLabel(row_item, text=str(rec.get('date')), width=110)
            lbl_date.pack(side="left", padx=10)

            lbl_fp = ctk.CTkLabel(row_item, text=str(rec.get('fingerprint_id')), width=60)
            lbl_fp.pack(side="left", padx=10)

            lbl_acid = ctk.CTkLabel(row_item, text=rec.get('academic_id'), width=120)
            lbl_acid.pack(side="right", padx=10)

            lbl_name = ctk.CTkLabel(row_item, text=rec.get('name'), anchor="w", width=180)
            lbl_name.pack(side="right", padx=10)

    def export_report_excel(self):
        if not self.current_report_data:
            messagebox.showwarning("تنبيه", "لا توجد بيانات لتصديرها.")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel Files", "*.xlsx")],
            title="حفظ تقرير Excel"
        )
        if file_path:
            try:
                ReportGenerator.export_to_excel(self.current_report_data, file_path)
                messagebox.showinfo("نجاح", "تم تصدير ملف Excel بنجاح.")
            except Exception as e:
                messagebox.showerror("خطأ", f"فشل التصدير إلى Excel: {e}")

    def export_report_pdf(self):
        if not self.current_report_data:
            messagebox.showwarning("تنبيه", "لا توجد بيانات لتصديرها.")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF Files", "*.pdf")],
            title="حفظ تقرير PDF"
        )
        if file_path:
            try:
                ReportGenerator.export_to_pdf(self.current_report_data, file_path)
                messagebox.showinfo("نجاح", "تم تصدير ملف PDF بنجاح.")
            except Exception as e:
                messagebox.showerror("خطأ", f"فشل التصدير إلى PDF: {e}")

    # ==========================================
    # 4. صفحة إعدادات النظام (Settings Screen)
    # ==========================================
    def create_settings_frame(self):
        self.frame_settings = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_settings.grid_columnconfigure(0, weight=1)
        self.frame_settings.grid_rowconfigure(1, weight=1)

        # عنوان الصفحة
        lbl_title = ctk.CTkLabel(self.frame_settings, text="إعدادات النظام والاتصالات", font=ctk.CTkFont(size=22, weight="bold"))
        lbl_title.grid(row=0, column=0, sticky="e", pady=10)

        # إطار قابل للتمرير لاحتواء كافة خيارات الإعدادات
        self.settings_scrollable = ctk.CTkScrollableFrame(self.frame_settings)
        self.settings_scrollable.grid(row=1, column=0, sticky="nsew", pady=10)

        # --- قسم 1: إعدادات الاتصال السلكي (Serial) ---
        group_serial = ctk.CTkFrame(self.settings_scrollable)
        group_serial.pack(fill="x", pady=10, padx=5)
        
        lbl_s_title = ctk.CTkLabel(group_serial, text="اتصال USB السلكي (Serial Port)", font=ctk.CTkFont(size=14, weight="bold"))
        lbl_s_title.pack(anchor="e", padx=15, pady=10)
        
        row_s = ctk.CTkFrame(group_serial, fg_color="transparent")
        row_s.pack(fill="x", padx=15, pady=5)

        self.val_baudrate = ctk.CTkComboBox(row_s, values=["9600", "19200", "38400", "57600", "115200"], width=150)
        self.val_baudrate.set(self.settings.get('serial_baudrate', '115200'))
        self.val_baudrate.pack(side="left", padx=10)
        
        lbl_baud = ctk.CTkLabel(row_s, text="معدل البود (Baudrate):")
        lbl_baud.pack(side="left", padx=5)

        self.val_serial_port = ctk.CTkEntry(row_s, placeholder_text="com8", width=150, justify="center")
        self.val_serial_port.insert(0, self.settings.get('serial_port', 'com8'))
        self.val_serial_port.pack(side="right", padx=10)
        
        lbl_port = ctk.CTkLabel(row_s, text="منفذ الكوم (Serial Port):")
        lbl_port.pack(side="right", padx=5)

        # --- قسم 2: إعدادات اتصال الواي فاي والإنترنت (Wi-Fi & API) ---
        group_wifi = ctk.CTkFrame(self.settings_scrollable)
        group_wifi.pack(fill="x", pady=10, padx=5)
        
        lbl_w_title = ctk.CTkLabel(group_wifi, text="إعدادات خادم الشبكة (Wi-Fi)", font=ctk.CTkFont(size=14, weight="bold"))
        lbl_w_title.pack(anchor="e", padx=15, pady=10)

        # منفذ Flask
        row_w1 = ctk.CTkFrame(group_wifi, fg_color="transparent")
        row_w1.pack(fill="x", padx=15, pady=5)
        
        self.val_flask_port = ctk.CTkEntry(row_w1, placeholder_text="5000", width=150, justify="center")
        self.val_flask_port.insert(0, self.settings.get('flask_port', '5000'))
        self.val_flask_port.pack(side="right", padx=10)
        lbl_wport = ctk.CTkLabel(row_w1, text="منفذ خادم الويب (Web Server Port):")
        lbl_wport.pack(side="right", padx=5)

        # اسم وكلمة مرور الواي فاي (ليتم استخدامها في توليد كود الـ ESP32)
        row_w2 = ctk.CTkFrame(group_wifi, fg_color="transparent")
        row_w2.pack(fill="x", padx=15, pady=5)
        
        self.val_wifi_pass = ctk.CTkEntry(row_w2, placeholder_text="WiFi Password", width=200)
        self.make_entry_rtl_compatible(self.val_wifi_pass)
        self.val_wifi_pass.insert(0, self.settings.get('wifi_password', ''))
        self.val_wifi_pass.pack(side="left", padx=10)
        lbl_wpass = ctk.CTkLabel(row_w2, text="كلمة مرور الواي فاي:")
        lbl_wpass.pack(side="left", padx=5)

        self.val_wifi_ssid = ctk.CTkEntry(row_w2, placeholder_text="WiFi SSID Name", width=200)
        self.make_entry_rtl_compatible(self.val_wifi_ssid)
        self.val_wifi_ssid.insert(0, self.settings.get('wifi_ssid', ''))
        self.val_wifi_ssid.pack(side="right", padx=10)
        lbl_wssid = ctk.CTkLabel(row_w2, text="اسم شبكة الواي فاي:")
        lbl_wssid.pack(side="right", padx=5)

        # --- قسم 3: أوقات تسجيل الحضور والتأخير ---
        group_time = ctk.CTkFrame(self.settings_scrollable)
        group_time.pack(fill="x", pady=10, padx=5)

        lbl_t_title = ctk.CTkLabel(group_time, text="مواعيد المحاضرات والحضور", font=ctk.CTkFont(size=14, weight="bold"))
        lbl_t_title.pack(anchor="e", padx=15, pady=10)

        row_t = ctk.CTkFrame(group_time, fg_color="transparent")
        row_t.pack(fill="x", padx=15, pady=5)

        self.val_time_late = ctk.CTkEntry(row_t, placeholder_text="08:30:00", width=150, justify="center")
        self.val_time_late.insert(0, self.settings.get('attendance_time_late', '08:30:00'))
        self.val_time_late.pack(side="left", padx=10)
        lbl_tlate = ctk.CTkLabel(row_t, text="وقت التأخر (Late بعد):")
        lbl_tlate.pack(side="left", padx=5)

        self.val_time_start = ctk.CTkEntry(row_t, placeholder_text="08:00:00", width=150, justify="center")
        self.val_time_start.insert(0, self.settings.get('attendance_time_start', '08:00:00'))
        self.val_time_start.pack(side="right", padx=10)
        lbl_tstart = ctk.CTkLabel(row_t, text="وقت بدء المحاضرة (Start):")
        lbl_tstart.pack(side="right", padx=5)

        # --- قسم 4: إشعارات البريد الإلكتروني (SMTP) ---
        group_email = ctk.CTkFrame(self.settings_scrollable)
        group_email.pack(fill="x", pady=10, padx=5)
        
        lbl_e_title = ctk.CTkLabel(group_email, text="إشعارات البريد الإلكتروني (SMTP)", font=ctk.CTkFont(size=14, weight="bold"))
        lbl_e_title.pack(anchor="e", padx=15, pady=10)

        row_e1 = ctk.CTkFrame(group_email, fg_color="transparent")
        row_e1.pack(fill="x", padx=15, pady=5)
        
        self.val_smtp_port = ctk.CTkEntry(row_e1, placeholder_text="587", width=100, justify="center")
        self.val_smtp_port.insert(0, self.settings.get('smtp_port', '587'))
        self.val_smtp_port.pack(side="left", padx=10)
        lbl_eport = ctk.CTkLabel(row_e1, text="المنفذ (Port):")
        lbl_eport.pack(side="left", padx=5)

        self.val_smtp_server = ctk.CTkEntry(row_e1, placeholder_text="smtp.gmail.com", width=220, justify="left")
        self.val_smtp_server.insert(0, self.settings.get('smtp_server', 'smtp.gmail.com'))
        self.val_smtp_server.pack(side="right", padx=10)
        lbl_eserver = ctk.CTkLabel(row_e1, text="خادم البريد (SMTP Server):")
        lbl_eserver.pack(side="right", padx=5)

        row_e2 = ctk.CTkFrame(group_email, fg_color="transparent")
        row_e2.pack(fill="x", padx=15, pady=5)

        self.val_smtp_pass = ctk.CTkEntry(row_e2, placeholder_text="SMTP App Password", show="*", width=220, justify="left")
        self.val_smtp_pass.insert(0, self.settings.get('smtp_password', ''))
        self.val_smtp_pass.pack(side="left", padx=10)
        lbl_epass = ctk.CTkLabel(row_e2, text="كلمة مرور التطبيقات:")
        lbl_epass.pack(side="left", padx=5)

        self.val_smtp_email = ctk.CTkEntry(row_e2, placeholder_text="your_email@gmail.com", width=220, justify="left")
        self.val_smtp_email.insert(0, self.settings.get('smtp_email', ''))
        self.val_smtp_email.pack(side="right", padx=10)
        lbl_eaddr = ctk.CTkLabel(row_e2, text="البريد المرسل:")
        lbl_eaddr.pack(side="right", padx=5)

        # --- قسم 5: إشعارات تلجرام الفورية (Telegram Notification) ---
        group_tg = ctk.CTkFrame(self.settings_scrollable)
        group_tg.pack(fill="x", pady=10, padx=5)
        
        lbl_g_title = ctk.CTkLabel(group_tg, text="إشعارات تلجرام الفورية للمسؤولين (إضافي)", font=ctk.CTkFont(size=14, weight="bold"))
        lbl_g_title.pack(anchor="e", padx=15, pady=10)

        row_g1 = ctk.CTkFrame(group_tg, fg_color="transparent")
        row_g1.pack(fill="x", padx=15, pady=5)
        
        self.val_tg_chat_id = ctk.CTkEntry(row_g1, placeholder_text="-100123456789", width=220, justify="center")
        self.val_tg_chat_id.insert(0, self.settings.get('telegram_chat_id', ''))
        self.val_tg_chat_id.pack(side="right", padx=10)
        lbl_tchat = ctk.CTkLabel(row_g1, text="معرف الشات (Chat ID):")
        lbl_tchat.pack(side="right", padx=5)

        row_g2 = ctk.CTkFrame(group_tg, fg_color="transparent")
        row_g2.pack(fill="x", padx=15, pady=5)

        self.val_tg_token = ctk.CTkEntry(group_tg, placeholder_text="Bot API Token (e.g. 123456:ABC-DEF...)", justify="center")
        self.val_tg_token.insert(0, self.settings.get('telegram_bot_token', ''))
        self.val_tg_token.pack(fill="x", padx=15, pady=5)
        lbl_ttoken = ctk.CTkLabel(group_tg, text="توكن البوت (Bot Token):")
        lbl_ttoken.pack(anchor="e", padx=15, pady=2)

        # --- زر الحفظ العام ---
        self.btn_save_all_settings = ctk.CTkButton(
            self.settings_scrollable, text="حفظ جميع الإعدادات 💾",
            fg_color="#1a73e8", hover_color="#155cb4", height=40,
            command=self.save_all_settings
        )
        self.btn_save_all_settings.pack(fill="x", pady=20, padx=10)

    def save_all_settings(self):
        """حفظ كافة التغييرات في قاعدة البيانات وتحديث الخدمات الفعالة"""
        try:
            # تحديث في قاعدة البيانات
            self.db.update_setting('serial_port', self.val_serial_port.get().strip())
            self.db.update_setting('serial_baudrate', self.val_baudrate.get())
            self.db.update_setting('flask_port', self.val_flask_port.get().strip())
            self.db.update_setting('wifi_ssid', self.val_wifi_ssid.get().strip())
            self.db.update_setting('wifi_password', self.val_wifi_pass.get().strip())
            self.db.update_setting('attendance_time_start', self.val_time_start.get().strip())
            self.db.update_setting('attendance_time_late', self.val_time_late.get().strip())
            self.db.update_setting('smtp_server', self.val_smtp_server.get().strip())
            self.db.update_setting('smtp_port', self.val_smtp_port.get().strip())
            self.db.update_setting('smtp_email', self.val_smtp_email.get().strip())
            self.db.update_setting('smtp_password', self.val_smtp_pass.get().strip())
            self.db.update_setting('telegram_bot_token', self.val_tg_token.get().strip())
            self.db.update_setting('telegram_chat_id', self.val_tg_chat_id.get().strip())

            # تحديث المتغير المحلي للإعدادات
            self.settings = self.db.get_settings()
            
            # إعادة تهيئة شريط البيانات السريع
            self.lbl_ip_info.configure(text=f"IP خادم الواي فاي:\n{self.get_local_ip()}:{self.settings.get('flask_port', '5000')}")
            self.lbl_com_info.configure(text=f"منفذ USB السلكي:\n{self.settings.get('serial_port', 'com8')}")

            # إعادة تشغيل قارئ السيريال بناء على القيم الجديدة
            self.serial_reader.stop()
            self.serial_reader.start(
                self.settings.get('serial_port', 'com8'),
                self.settings.get('serial_baudrate', '115200'),
                self.db,
                self.ui_queue
            )

            messagebox.showinfo("نجاح", "تم حفظ الإعدادات بنجاح وإعادة تشغيل الخدمات السلكية بالمنفذ الجديد.")
        except Exception as e:
            messagebox.showerror("خطأ", f"فشل حفظ الإعدادات: {e}")

    # ==========================================
    # إدارة الأحداث والخيوط (Thread Event Loop)
    # ==========================================
    def process_queue(self):
        """فحص صف الأحداث لتحديث الواجهة من الخيوط الأخرى بأمان"""
        try:
            while True:
                event = self.ui_queue.get_nowait()
                event_type = event.get('type')
                
                # 1. حدث تسجيل حضور بنجاح
                if event_type == 'attendance':
                    record = event.get('record')
                    name = event.get('student_name')
                    already = event.get('already_logged')
                    
                    self.update_dashboard_stats()
                    
                    if already:
                        messagebox.showinfo("تنبيه حضور", f"الطالب '{name}' قام بتسجيل الحضور مسبقاً اليوم.")
                    else:
                        # إشعار منبثق مؤقت أو رسالة في الأسفل
                        print(f"UI NOTIFIED: Student {name} logged successfully.")
                        
                # 2. بصمة غير مسجلة في قاعدة البيانات
                elif event_type == 'unregistered_scan':
                    fp_id = event.get('fingerprint_id')
                    messagebox.showwarning(
                        "بصمة غير معروفة", 
                        f"تم مسح البصمة رقم ({fp_id}) على الجهاز، ولكنها غير مسجلة لطالب في قاعدة البيانات."
                    )
                    
                # 3. محاولة مطابقة فاشلة تماماً في المستشعر
                elif event_type == 'no_match':
                    messagebox.showwarning("خطأ مطابقة", "البصمة الموضوعة لا تطابق أي بصمة مخزنة على المستشعر.")
                    
                # 4. نتيجة تسجيل بصمة جديدة
                elif event_type == 'enroll_result':
                    status = event.get('status')
                    fp_id = event.get('fingerprint_id')
                    
                    # إعادة تفعيل الأزرار والمدخلات
                    self.entry_name.configure(state="normal")
                    self.entry_academic_id.configure(state="normal")
                    self.entry_email.configure(state="normal")
                    self.entry_fp_id.configure(state="normal")
                    self.btn_enroll_hardware.configure(state="normal")
                    
                    # إلغاء التعليق في الخادم
                    flask_server.cancel_pending_enroll()
                    
                    if status == 'success':
                        self.lbl_enroll_status.configure(
                            text=f"✅ تم تبصيم البصمة رقم ({fp_id}) بنجاح على الجهاز!",
                            text_color="#2ec4b6"
                        )
                        # تفعيل زر الحفظ في قاعدة البيانات
                        self.btn_save_student.configure(state="normal")
                    else:
                        err = event.get('message', 'خطأ غير معروف')
                        translations = {
                            'Timeout waiting for finger (Image 1)': 'انتهت مهلة وضع البصمة الأولى',
                            'Failed to convert image 1': 'فشل قراءة صورة البصمة الأولى',
                            'Timeout waiting for finger (Image 2)': 'انتهت مهلة وضع البصمة الثانية',
                            'Failed to convert image 2': 'فشل قراءة صورة البصمة الثانية',
                            'Failed to store model in sensor memory': 'فشل حفظ البصمة في ذاكرة الجهاز',
                            'Fingerprints did not match. Try again': 'البصمتان غير متطابقتين، يرجى المحاولة مجدداً'
                        }
                        err_ar = translations.get(err, err)
                        self.lbl_enroll_status.configure(
                            text=f"❌ فشل التبصيم: {err_ar}",
                            text_color="#e71d36"
                        )
                        self.btn_save_student.configure(state="disabled")

                # 5. تحديث حالة التبصيم خطوة بخطوة
                elif event_type == 'enroll_status_update':
                    msg = event.get('message', '')
                    translations = {
                        'Place finger on sensor': '⏳ يرجى وضع الإصبع على جهاز البصمة الآن...',
                        'Remove finger': '☝️ يرجى رفع الإصبع عن المستشعر...',
                        'Place same finger again': '🔄 يرجى وضع نفس الإصبع مرة أخرى لتأكيد المطابقة...',
                        'Timeout waiting for finger (Image 1)': '❌ انتهت مهلة وضع البصمة الأولى.',
                        'Failed to convert image 1': '❌ فشل قراءة صورة البصمة الأولى.',
                        'Timeout waiting for finger (Image 2)': '❌ انتهت مهلة وضع البصمة الثانية.',
                        'Failed to convert image 2': '❌ فشل قراءة صورة البصمة الثانية.',
                        'Failed to store model in sensor memory': '❌ فشل حفظ البصمة في ذاكرة المستشعر.',
                        'Fingerprints did not match. Try again': '❌ لم تتطابق البصمتان. يرجى المحاولة مرة أخرى.'
                    }
                    translated_msg = translations.get(msg, msg)
                    self.lbl_enroll_status.configure(
                        text=translated_msg,
                        text_color="#ff9f1c"
                    )
                    
                        
                self.ui_queue.task_done()
        except queue.Empty:
            pass
        finally:
            # تكرار الفحص كل 100 مللي ثانية
            self.after(100, self.process_queue)

    def on_closing(self):
        """تنظيف الموارد عند إغلاق التطبيق"""
        self.serial_reader.stop()
        self.destroy()
        

if __name__ == "__main__":
    app = StudentAttendanceApp()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
