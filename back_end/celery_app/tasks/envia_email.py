import os
from dotenv import load_dotenv
from email.message import EmailMessage
import smtplib
from celery_app.celery_app import celery_app

load_dotenv()

@celery_app.task(bind=True)
def enviar_email(self,dict_info: dict):
    SMTP_SERVER = os.getenv('SMTP_SERVER')
    SMTP_PORT = int(os.getenv('SMTP_PORT'))
    EMAIL_USER = os.getenv('EMAIL_USER')
    EMAIL_PASS = os.getenv('EMAIL_PASS')
    token = dict_info.get('token')
    email = dict_info.get('email')

    msg = EmailMessage()
    msg['Subject'] = "Recuperação de Senha"
    msg['From'] = EMAIL_USER
    msg['To'] = email

    link = f"https://seuecommerce.com.br/site/alterar-senha?token={token}"

    conteudo_html = f"""
    <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: auto; border: 1px solid #ddd; padding: 20px; border-radius: 10px;">
                <h2 style="color: #2563eb;">Recuperação de Senha</h2>
                <p>Olá,</p>
                <p>Recebemos uma solicitação para redefinir a senha da sua conta no <strong>Minha Loja API</strong>.</p>
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{link}" style="background-color: #2563eb; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold;">Redefinir Minha Senha</a>
                </div>
                <p style="font-size: 0.9em; color: #666;">O link acima expira em 15 minutos.</p>
                <hr style="border: 0; border-top: 1px solid #eee;">
                <p style="font-size: 0.8em; color: #999;">Caso não tenha sido você, por favor ignore este e-mail por segurança.</p>
            </div>
        </body>
    </html>
    """
    msg.add_alternative(conteudo_html, subtype='html')

    # Dispara o e-mail diretamente aqui!
    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as smtp:
        smtp.login(EMAIL_USER, EMAIL_PASS)
        smtp.send_message(msg)
        