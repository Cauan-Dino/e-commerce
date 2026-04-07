import os
from datetime import datetime,timedelta,timezone
from dotenv import load_dotenv
from banco_dados import Session,sessao_db,UsuarioDB
from pydantic import EmailStr
from fastapi import Depends,APIRouter,HTTPException
from jose import JWTError,jwt
from fastapi.security import OAuth2PasswordBearer

oauth_scheme = OAuth2PasswordBearer(tokenUrl='/site/login-usuario')

auth_router = APIRouter(
    prefix='/auth',
    tags=['Autenticação']
)

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
TEMPO_ACCESS = int(os.getenv("TEMPO_ACCESS"))
TEMPO_REFRESH = int(os.getenv("TEMPO_REFRESH"))

# Cria token de acesso
def criar_token_acesso(email: EmailStr,time=timedelta(minutes=TEMPO_ACCESS),db: Session = Depends(sessao_db)):
    tempo = datetime.now(timezone.utc) + time
    
    # Verifica se o email existe
    usuario = db.query(UsuarioDB).filter(UsuarioDB.email == email).first()
    if not usuario:
        raise HTTPException(
            status_code=404,
            detail='Esse email não existe'
        )
    
    # Cria o token
    dict_info = {
        'sub': str(usuario.usuario_id),
        'exp':tempo,
        'type':'access'
    }
    token = jwt.encode(dict_info,SECRET_KEY,ALGORITHM)
    return token

# Cria um token de acesso para usuarios logados pelo google
def criar_token_acesso_google(usuario_id: int, time: timedelta = None):
    if time is None:
        time = timedelta(minutes=TEMPO_ACCESS)
        
    tempo_expiracao = datetime.now(timezone.utc) + time
    
    dict_info = {
        'sub': str(usuario_id),
        'exp': tempo_expiracao,
        'type': 'access'
    }
    
    token = jwt.encode(dict_info, SECRET_KEY, algorithm=ALGORITHM)
    return token

# Cria um refresh token para um usuario do google
def criar_token_refresh_google(usuario_id: int, time: timedelta = None):
    # Se não passar tempo, usa o padrão (ex: 7 dias)
    if time is None:
        time = timedelta(days=TEMPO_REFRESH)
        
    tempo_expiracao = datetime.now(timezone.utc) + time
    
    dict_info = {
        'sub': str(usuario_id),
        'exp': tempo_expiracao,
        'type': 'refresh'
    }
    
    token = jwt.encode(dict_info, SECRET_KEY, algorithm=ALGORITHM)
    return token

# Cria um token do tipo refresh
def criar_token_refresh(email: EmailStr,time=timedelta(days=TEMPO_REFRESH),db: Session = Depends(sessao_db)):
    tempo = datetime.now(timezone.utc) + time
    
    # Verifica se o email existe
    usuario = db.query(UsuarioDB).filter(UsuarioDB.email == email).first()
    if not usuario:
        raise HTTPException(
            status_code=404,
            detail='Esse email não existe'
        )
    
    # Cria o token
    dict_info = {
        'sub':str(usuario.usuario_id),
        'exp':tempo,
        'type':'refresh'
    }
    token = jwt.encode(dict_info,SECRET_KEY,ALGORITHM)
    return token

# Verifica se o token do tipo refresh ainda ta valido
def verificar_token_refresh(token: str = Depends(oauth_scheme),db: Session = Depends(sessao_db)):
    # Trata o erro caso o token nao exista
    try:
        dict_info = jwt.decode(token,SECRET_KEY,algorithms=[ALGORITHM])
        usuario_id = dict_info.get('sub')
        token_type = dict_info.get('type')
    except JWTError:
        raise HTTPException(
            status_code=401,
            detail=f'Token inválido'
        )
    # Verifica se o token eh do tipo refresh
    if token_type != 'refresh':
        raise HTTPException(
            status_code=400,
            detail='O token precisa do tipo refresh'
        )
    usuario = db.query(UsuarioDB).filter(UsuarioDB.usuario_id == usuario_id).first()
    if not usuario:
        raise HTTPException(
            status_code=404,
            detail='Esse usuário não existe'
        )
    return usuario

# Verifica o token do tipo access
def verificar_token_access(token: str = Depends(oauth_scheme),db: Session = Depends(sessao_db)):
    # Tratamento de erro caso o token nao existe
    try:
        dict_info = jwt.decode(token,SECRET_KEY,algorithms=[ALGORITHM])
        usuario_id = dict_info.get('sub')
        token_type = dict_info.get('type')
    except JWTError:
        raise HTTPException(
            status_code=401,
            detail=f'Token inválido'
        )
    # Verifica se o token eh do tipo access
    if token_type != 'access':
        raise HTTPException(
            status_code=400,
            detail='O token precisa ser do tipo access'
        )
    # Verifica se o usuario existe
    usuario = db.query(UsuarioDB).filter(UsuarioDB.usuario_id == usuario_id).first()
    if not usuario:
        raise HTTPException(
            status_code=404,
            detail='Esse usúario não existe'
        )
    return usuario

@auth_router.post('/refresh')
async def refresh(usuario: UsuarioDB = Depends(verificar_token_refresh),db: Session = Depends(sessao_db)):
    token = criar_token_acesso(usuario.email,db=db)
    return {
        'access_token':token,
        'type':'Bearer'
    }
