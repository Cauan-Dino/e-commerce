from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse
import httpx
from banco_dados import sessao_db, UsuarioDB
from sqlalchemy.orm import Session
from sqlalchemy import or_
import os
from datetime import timedelta
from dotenv import load_dotenv
from auth_token import criar_token_acesso,criar_token_refresh

load_dotenv()

router = APIRouter(
    prefix='/auth',
    tags=['Google autenticação']
)

# Credenciais e Configurações
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")
# Transformamos em timedelta aqui para facilitar o uso na função
TEMPO_ACESSO_GOOGLE = timedelta(minutes=int(os.getenv("TEMPO_ACESSO_GOOGLE", 15)))

@router.get("/login/google")
async def login_google():
    return RedirectResponse(
        url=f"https://accounts.google.com/o/oauth2/v2/auth?response_type=code&client_id={GOOGLE_CLIENT_ID}&redirect_uri={GOOGLE_REDIRECT_URI}&scope=openid%20email%20profile"
    )

@router.get("/google/callback")
async def auth_google(code: str, db: Session = Depends(sessao_db)):
    async with httpx.AsyncClient() as client:
        # 1. Troca do código pelo Token de Acesso do Google
        token_url = "https://oauth2.googleapis.com/token"
        data = {
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        }
        
        res_token = await client.post(token_url, data=data)
        if res_token.status_code != 200:
            raise HTTPException(status_code=400, detail="Erro ao obter token do Google")
        
        google_access_token = res_token.json().get("access_token")

        # 2. Busca de informações do perfil do usuário
        user_info_res = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {google_access_token}"}
        )
        if user_info_res.status_code != 200:
            raise HTTPException(status_code=400, detail="Erro ao obter dados do usuário")
            
        user_info = user_info_res.json()

    # 3. Lógica de Banco de Dados
    google_id = user_info.get("sub")
    email_google = user_info.get("email")
    nome_usuario = user_info.get('name')

    usuario = db.query(UsuarioDB).filter(
        or_(UsuarioDB.google_id == google_id, UsuarioDB.email == email_google)
    ).first()

    try:
        # Validação: Se o usuário já existe
        if usuario:
            # Ele existe, mas estava inativo (Reativa a conta se essa for a sua regra)
            if not usuario.usuario_ativo:
                usuario.usuario_ativo = True
            # Se entrou por e-mail/senha antes, vincula o google_id agora
            if usuario.google_id is None:
                usuario.google_id = google_id
            
        # Se não existe, cria um novo (garanta que o padrão de 'usuario_ativo' seja True no seu Model ou defina aqui)
        else:
            usuario = UsuarioDB(
                nome_usuario=nome_usuario,
                email=email_google,
                google_id=google_id,
                senha_usuario=None,
                usuario_ativo=True
            )
            db.add(usuario)
        db.commit()
        db.refresh(usuario)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Erro ao processar usuário no banco de dados")

    # 4. Geração dos seus Tokens internos
    # Passamos o tempo específico do Google se desejar
    meu_access_token = criar_token_acesso(email=usuario.email, time=TEMPO_ACESSO_GOOGLE, db=db)
    meu_refresh_token = criar_token_refresh(email=usuario.email, db=db)
    
    return {
        "access_token": meu_access_token, 
        "refresh_token": meu_refresh_token, 
        "token_type": "bearer"
    }