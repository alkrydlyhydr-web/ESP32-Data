import os
import sys
import subprocess
from datetime import datetime

# التثبيت التلقائي للمكتبات الخاصة باللغة العربية في PDF إذا لم تكن موجودة
try:
    import arabic_reshaper
    from bidi.algorithm import get_display
except ImportError:
    print("Installing arabic-reshaper and python-bidi for Arabic PDF support...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "arabic-reshaper", "python-bidi"])
    import arabic_reshaper
    from bidi.algorithm import get_display

import pandas as pd

# التحقق من تثبيت مكتبة openpyxl لتصدير Excel
try:
    import openpyxl
except ImportError:
    print("Installing openpyxl for Excel export support...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "openpyxl"])
        import openpyxl
    except Exception as e:
        print(f"Failed to install openpyxl: {e}")

# استيراد مكتبات ReportLab لتصميم الـ PDF
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

class ReportGenerator:
    @staticmethod
    def _reshape_text(text):
        """إعادة تشكيل النص العربي ليظهر بشكل صحيح في الـ PDF (من اليمين لليوم وبأحرف متصلة)"""
        if not text:
            return ""
        reshaped = arabic_reshaper.reshape(str(text))
        bidi_text = get_display(reshaped)
        return bidi_text

    @classmethod
    def export_to_excel(cls, report_data, file_path):
        """تصدير التقارير إلى ملف Excel"""
        try:
            # تجهيز البيانات للتصدير
            data = []
            for row in report_data:
                # تحويل حالة الحضور للعربية
                status_map = {'Present': 'حاضر', 'Late': 'متأخر', 'Absent': 'غائب'}
                status_ar = status_map.get(row.get('status'), row.get('status'))
                
                data.append({
                    'الرقم الأكاديمي': row.get('academic_id'),
                    'اسم الطالب': row.get('name'),
                    'البريد الإلكتروني': row.get('email'),
                    'رقم البصمة': row.get('fingerprint_id'),
                    'التاريخ': str(row.get('date')),
                    'وقت الحضور': str(row.get('check_in_time')),
                    'الحالة': status_ar
                })

            df = pd.DataFrame(data)
            
            # حفظ الملف
            df.to_excel(file_path, index=False, sheet_name='تقرير الحضور والغياب')
            return True
        except Exception as e:
            print(f"Failed to export to Excel: {e}")
            raise e

    @classmethod
    def export_to_pdf(cls, report_data, file_path):
        """تصدير التقارير إلى ملف PDF منسق واحترافي يدعم اللغة العربية"""
        try:
            # البحث الديناميكي عن الخطوط المتوافقة مع العربية على مختلف أنظمة التشغيل
            font_paths = [
                # Windows
                os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), 'Fonts', 'tahoma.ttf'),
                os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), 'Fonts', 'arial.ttf'),
                os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), 'Fonts', 'times.ttf'),
                os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), 'Fonts', 'calibri.ttf'),
                os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), 'Fonts', 'segoeui.ttf'),
                # macOS
                '/System/Library/Fonts/Supplemental/Arial.ttf',
                '/Library/Fonts/Arial.ttf',
                '/System/Library/Fonts/Supplemental/Times New Roman.ttf',
                '/Library/Fonts/Tahoma.ttf',
                # Linux
                '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
                '/usr/share/fonts/truetype/freefont/FreeSans.ttf',
                '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
                # خط محلي احتياطي في مجلد البرنامج
                os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Amiri-Regular.ttf')
            ]
            
            font_name = 'Helvetica'
            registered = False
            for path in font_paths:
                if os.path.exists(path):
                    try:
                        pdfmetrics.registerFont(TTFont('ArabicFont', path))
                        font_name = 'ArabicFont'
                        registered = True
                        break
                    except Exception as e:
                        print(f"Failed to register font {path}: {e}")
            
            # إذا لم يتم العثور على أي خط يدعم العربية، نقوم بتحميل خط Amiri مفتوح المصدر تلقائياً
            if not registered:
                local_amiri = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Amiri-Regular.ttf')
                if not os.path.exists(local_amiri):
                    print("No local Arabic fonts found. Attempting to download Amiri font from Google Fonts...")
                    try:
                        import urllib.request
                        url = "https://github.com/google/fonts/raw/main/ofl/amiri/Amiri-Regular.ttf"
                        urllib.request.urlretrieve(url, local_amiri)
                    except Exception as ex:
                        print(f"Failed to download Amiri font: {ex}")
                
                if os.path.exists(local_amiri):
                    try:
                        pdfmetrics.registerFont(TTFont('ArabicFont', local_amiri))
                        font_name = 'ArabicFont'
                        registered = True
                    except Exception as e:
                        print(f"Failed to register downloaded Amiri font: {e}")

            # إنشاء مستند الـ PDF
            doc = SimpleDocTemplate(
                file_path,
                pagesize=A4,
                rightMargin=30,
                leftMargin=30,
                topMargin=30,
                bottomMargin=30
            )

            story = []
            styles = getSampleStyleSheet()

            # إعداد التنسيقات
            title_style = ParagraphStyle(
                'TitleStyle',
                parent=styles['Heading1'],
                fontName=font_name,
                fontSize=20,
                leading=24,
                textColor=colors.HexColor("#1a73e8"),
                alignment=1, # Center
                spaceAfter=15
            )

            meta_style = ParagraphStyle(
                'MetaStyle',
                parent=styles['Normal'],
                fontName=font_name,
                fontSize=10,
                leading=14,
                textColor=colors.HexColor("#555555"),
                alignment=2, # Right
                spaceAfter=20
            )

            cell_style = ParagraphStyle(
                'CellStyle',
                parent=styles['Normal'],
                fontName=font_name,
                fontSize=9,
                leading=12,
                alignment=1 # Center
            )

            header_style = ParagraphStyle(
                'HeaderStyle',
                parent=styles['Normal'],
                fontName=font_name,
                fontSize=10,
                leading=13,
                textColor=colors.white,
                alignment=1 # Center
            )

            # عنوان التقرير
            title_text = cls._reshape_text("تقرير حضور وغياب الطلاب")
            story.append(Paragraph(title_text, title_style))

            # معلومات التقرير التاريخ والوقت
            generation_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            meta_text = cls._reshape_text(f"تاريخ استخراج التقرير: {generation_time} | إجمالي السجلات: {len(report_data)}")
            story.append(Paragraph(meta_text, meta_style))

            # جدول البيانات
            # رؤوس الأعمدة (بالترتيب من اليمين إلى اليسار ليناسب القراءة العربية)
            headers = [
                cls._reshape_text("الحالة"),
                cls._reshape_text("وقت الحضور"),
                cls._reshape_text("التاريخ"),
                cls._reshape_text("رقم البصمة"),
                cls._reshape_text("اسم الطالب"),
                cls._reshape_text("الرقم الأكاديمي")
            ]

            table_data = [[Paragraph(h, header_style) for h in headers]]

            # ملء بيانات الجدول
            for row in report_data:
                # تحويل حالة الحضور للعربية
                status_map = {'Present': 'حاضر', 'Late': 'متأخر', 'Absent': 'غائب'}
                status_ar = status_map.get(row.get('status'), row.get('status'))
                
                # إعداد نصوص الخلايا وإعادة تشكيلها للعربية
                row_cells = [
                    Paragraph(cls._reshape_text(status_ar), cell_style),
                    Paragraph(cls._reshape_text(str(row.get('check_in_time'))), cell_style),
                    Paragraph(cls._reshape_text(str(row.get('date'))), cell_style),
                    Paragraph(cls._reshape_text(str(row.get('fingerprint_id'))), cell_style),
                    Paragraph(cls._reshape_text(row.get('name')), cell_style),
                    Paragraph(cls._reshape_text(row.get('academic_id')), cell_style)
                ]
                table_data.append(row_cells)

            # إنشاء جدول ReportLab
            # عرض الأعمدة (مجموعها يناسب عرض صفحة A4 بـ margins 30 من الجهتين = 535)
            col_widths = [70, 80, 80, 70, 155, 80]
            t = Table(table_data, colWidths=col_widths, repeatRows=1)
            
            # تصميم الجدول
            t_style = TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1a73e8")),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('TOPPADDING', (0, 0), (-1, 0), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e0e0e0")),
            ])
            
            # تلوين الصفوف بالتناوب (Zebra Stripe Effect) وتلوين الحالات
            for i in range(1, len(table_data)):
                # خلفية بالتناوب
                bg_color = colors.HexColor("#f8f9fa") if i % 2 == 0 else colors.white
                t_style.add('BACKGROUND', (0, i), (-1, i), bg_color)
                
                # تلوين خلية الحالة
                status_val = report_data[i-1].get('status')
                if status_val == 'Present':
                    t_style.add('TEXTCOLOR', (0, i), (0, i), colors.HexColor("#2ec4b6")) # أخضر
                elif status_val == 'Late':
                    t_style.add('TEXTCOLOR', (0, i), (0, i), colors.HexColor("#ff9f1c")) # برتقالي
                elif status_val == 'Absent':
                    t_style.add('TEXTCOLOR', (0, i), (0, i), colors.HexColor("#e71d36")) # أحمر
                
                t_style.add('BOTTOMPADDING', (0, i), (-1, i), 6)
                t_style.add('TOPPADDING', (0, i), (-1, i), 6)

            t.setStyle(t_style)
            story.append(t)

            # بناء المستند
            doc.build(story)
            return True
        except Exception as e:
            print(f"Failed to export to PDF: {e}")
            raise e
