import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
import threading

class Notifier:
    @staticmethod
    def _send_email_async(to_email, subject, body, smtp_server, smtp_port, from_email, password):
        """إرسال البريد الإلكتروني في خيط منفصل لتفادي تجميد النظام"""
        if not smtp_server or not from_email or not password:
            print("Email settings are incomplete. Skipping email notification.")
            return

        try:
            # إنشاء الرسالة
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = from_email
            message["To"] = to_email

            # تمثيل HTML للبريد الإلكتروني بشكل احترافي وجذاب
            html = f"""
            <html>
                <body style="font-family: Arial, sans-serif; direction: rtl; text-align: right; background-color: #f4f6f9; padding: 20px;">
                    <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; padding: 30px; box-shadow: 0 4px 10px rgba(0,0,0,0.1); border-top: 5px solid #1a73e8;">
                        <h2 style="color: #1a73e8; margin-bottom: 20px; text-align: center;">إشعار تسجيل الحضور</h2>
                        <p style="font-size: 16px; color: #333;">عزيزي ولي الأمر / الطالب،</p>
                        <p style="font-size: 15px; color: #555; line-height: 1.6;">
                            نود إعلامكم بأنه تم تسجيل حضور الطالب بنجاح في النظام وفقاً للبيانات التالية:
                        </p>
                        <table style="width: 100%; border-collapse: collapse; margin-top: 20px; margin-bottom: 20px; font-size: 15px;">
                            <tr style="background-color: #f8f9fa;">
                                <td style="padding: 10px; border: 1px solid #dee2e6; font-weight: bold; width: 30%;">اسم الطالب</td>
                                <td style="padding: 10px; border: 1px solid #dee2e6;">{body['name']}</td>
                            </tr>
                            <tr>
                                <td style="padding: 10px; border: 1px solid #dee2e6; font-weight: bold;">الرقم الأكاديمي</td>
                                <td style="padding: 10px; border: 1px solid #dee2e6;">{body['academic_id']}</td>
                            </tr>
                            <tr style="background-color: #f8f9fa;">
                                <td style="padding: 10px; border: 1px solid #dee2e6; font-weight: bold;">التاريخ</td>
                                <td style="padding: 10px; border: 1px solid #dee2e6;">{body['date']}</td>
                            </tr>
                            <tr>
                                <td style="padding: 10px; border: 1px solid #dee2e6; font-weight: bold;">وقت الدخول</td>
                                <td style="padding: 10px; border: 1px solid #dee2e6;">{body['time']}</td>
                            </tr>
                            <tr style="background-color: #f8f9fa;">
                                <td style="padding: 10px; border: 1px solid #dee2e6; font-weight: bold;">حالة الحضور</td>
                                <td style="padding: 10px; border: 1px solid #dee2e6; color: {'#2ec4b6' if body['status'] == 'Present' else '#e71d36'}; font-weight: bold;">
                                    {body['status_ar']}
                                </td>
                            </tr>
                        </table>
                        <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
                        <p style="font-size: 12px; color: #888; text-align: center;">
                            هذا البريد تم إرساله تلقائياً من نظام إدارة حضور الطلاب بالبصمة. يرجى عدم الرد.
                        </p>
                    </div>
                </body>
            </html>
            """
            
            part = MIMEText(html, "html", "utf-8")
            message.attach(part)

            # إرسال البريد
            context = ssl.create_default_context()
            port = int(smtp_port)
            if port == 465:
                # SSL
                with smtplib.SMTP_SSL(smtp_server, port, context=context) as server:
                    server.login(from_email, password)
                    server.sendmail(from_email, to_email, message.as_string())
            else:
                # STARTTLS (Port 587 or 25)
                with smtplib.SMTP(smtp_server, port) as server:
                    server.ehlo()
                    server.starttls(context=context)
                    server.ehlo()
                    server.login(from_email, password)
                    server.sendmail(from_email, to_email, message.as_string())
                    
            print(f"Notification email sent successfully to {to_email}")
        except Exception as e:
            print(f"Failed to send email notification to {to_email}: {e}")

    @staticmethod
    def _send_telegram_async(token, chat_id, message_text):
        """إرسال إشعار تلجرام في خيط منفصل"""
        if not token or not chat_id:
            return
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": message_text,
                "parse_mode": "HTML"
            }
            response = requests.post(url, json=payload, timeout=5)
            if response.status_code == 200:
                print("Telegram notification sent successfully.")
            else:
                print(f"Telegram API error: {response.text}")
        except Exception as e:
            print(f"Failed to send Telegram notification: {e}")

    @classmethod
    def send_notifications(cls, record, settings):
        """
        إرسال إشعارات الحضور عبر الإيميل وتلجرام.
        الحقول المتوقعة في السجل (record): 
        'name', 'academic_id', 'email', 'date', 'check_in_time', 'status'
        """
        # ترجمة حالة الحضور للعربية
        status_map = {
            'Present': 'حاضر',
            'Late': 'متأخر',
            'Absent': 'غائب'
        }
        status_ar = status_map.get(record.get('status', 'Present'), 'حاضر')

        # تجهيز البيانات للإيميل
        email_body = {
            'name': record.get('name', ''),
            'academic_id': record.get('academic_id', ''),
            'date': str(record.get('date', '')),
            'time': str(record.get('check_in_time', '')),
            'status': record.get('status', 'Present'),
            'status_ar': status_ar
        }

        # إرسال الإيميل إذا تم توفيره وتفعيل الإعدادات
        student_email = record.get('email')
        if student_email and settings.get('smtp_email'):
            subject = f"إشعار حضور: {record.get('name')}"
            email_thread = threading.Thread(
                target=cls._send_email_async,
                args=(
                    student_email,
                    subject,
                    email_body,
                    settings.get('smtp_server'),
                    settings.get('smtp_port', '587'),
                    settings.get('smtp_email'),
                    settings.get('smtp_password')
                )
            )
            email_thread.daemon = True
            email_thread.start()

        # إرسال إشعار تلجرام للمسؤولين
        bot_token = settings.get('telegram_bot_token')
        chat_id = settings.get('telegram_chat_id')
        if bot_token and chat_id:
            # صياغة نص الإشعار لتلجرام
            emoji = "✅" if record.get('status') == 'Present' else "⚠️"
            telegram_msg = (
                f"<b>📢 إشعار تسجيل حضور طالب</b>\n\n"
                f"👤 <b>الاسم:</b> {record.get('name')}\n"
                f"🆔 <b>الرقم الجامعي:</b> {record.get('academic_id')}\n"
                f"📅 <b>التاريخ:</b> {record.get('date')}\n"
                f"⏰ <b>الوقت:</b> {record.get('check_in_time')}\n"
                f"{emoji} <b>الحالة:</b> {status_ar}"
            )
            
            telegram_thread = threading.Thread(
                target=cls._send_telegram_async,
                args=(bot_token, chat_id, telegram_msg)
            )
            telegram_thread.daemon = True
            telegram_thread.start()
