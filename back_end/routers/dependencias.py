import os
import secrets
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")

security = HTTPBasic()
chave = os.getenv('CPF_CRYPTO_KEY')
fernet = Fernet(chave)

def criptografar(cpf: str):
    return fernet.encrypt(cpf.encode()).decode()

def descriptografar(cpf_criptografado: str):
    return fernet.decrypt(cpf_criptografado.encode()).decode()

def autorizacao(credenciais: HTTPBasicCredentials = Depends(security)):
    password = os.getenv('SENHA')
    username = os.getenv('USUARIO')

    comparacao_password = secrets.compare_digest(password, credenciais.password)
    comparacao_username = secrets.compare_digest(username, credenciais.username)

    if not (comparacao_password and comparacao_username):
        raise HTTPException(
            status_code=401,
            detail='Senha ou usuario incorretos',
            headers={'WWW-Authenticate':'Basic'}
        )
