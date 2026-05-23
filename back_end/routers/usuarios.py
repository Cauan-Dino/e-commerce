import os
import secrets
import smtplib
import jwt
from datetime import datetime, timedelta
from email.message import EmailMessage
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from passlib.context import CryptContext

from banco_dados import sessao_db, UsuarioDB
from auth_token import verificar_token_access, criar_token_acesso, criar_token_refresh
from body_models import BODYUsuario, BODYCadastrarUsuario, BODYResetSenhaRequest, BODYExcluirConta
from routers.dependencias import autorizacao
from kafka_configs.producer import enviar_tarefa
from fastapi.security import OAuth2PasswordRequestForm

router = APIRouter()

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# Carrega as configurações do .env
SECRET_KEY = os.getenv("SECRET_KEY")
EMAIL_USER = os.getenv("EMAIL_USER")  # Seu e-mail 
EMAIL_PASS = os.getenv("EMAIL_PASS")  # Sua senha
SMTP_SERVER = os.getenv("SMTP_SERVER")        # Exemplo para Gmail
SMTP_PORT = int(os.getenv("SMTP_PORT", 465))

# Carrega o front end de resetpassword
@router.get("/reset-password")
async def pagina_reset():
    # Isso faz o navegador abrir o seu arquivo HTML
    return FileResponse("reset-password.html")

# Mostra todos os usuarios cadastrados
@router.get('/site/usuario')
async def mostrar_usuarios(db: Session = Depends(sessao_db), page: int = 1, limit: int = 20, usuario_id: int = None, nome_usuario: str = None, _: None = Depends(autorizacao)):
    # Tratamento de erro por pagina e limite
    if page < 1 or limit < 1:
        raise HTTPException(
            status_code=400,
            detail='Pagina ou limite invalidos'
        )

    query = db.query(UsuarioDB)

    # Filtro nome
    if nome_usuario is not None:
        query = query.filter(UsuarioDB.nome_usuario == nome_usuario)

    # Filtro id
    if usuario_id is not None:
        query = query.filter(UsuarioDB.usuario_id == usuario_id)

    # Mostra a quantidade de usuarios cadastrados
    quantidade_usuarios = query.count()

    query = query.offset((page-1)*limit).limit(limit).all()

    paginacao = [
        {
            'nome': valor.nome_usuario,
            'id': valor.usuario_id,
            'email': valor.email
        }
        for valor in query
    ]

    return {    
        'pagina': page,
        'limite': limit,
        'quantidade': quantidade_usuarios,
        'paginacao': paginacao
    }

# Login no site pelo site
@router.post('/site/login-usuario')
async def login_site_usuario(body: BODYUsuario, db: Session = Depends(sessao_db)):
    # Verifica se o usuario existe
    usuario = db.query(UsuarioDB).filter(UsuarioDB.email == body.email).first()
    if usuario is None:
        raise HTTPException(
            status_code=401,
            detail='Senha ou email incorretos'
        )
    
    if usuario.senha_usuario is None:
        raise HTTPException(
            status_code=401,
            detail='Esta conta foi criada via Google. Por favor, use o login social.'
        )

    senha_valida = pwd_context.verify(body.senha_usuario, usuario.senha_usuario)
    if not senha_valida:
        raise HTTPException(
            status_code=401,
            detail='Senha ou email incorretos'
        )
    
    access_token = criar_token_acesso(body.email, db=db)
    refresh_token = criar_token_refresh(body.email, db=db)

    return {
        'access_token': access_token,
        'refresh_token': refresh_token,
        'type': 'Bearer'
    }

# Cadastra no site pelo site
@router.post('/site/cadastro-usuario')
async def cadastrar_site_usuario(body: BODYCadastrarUsuario, db: Session = Depends(sessao_db)):
    # Verifica se o usuario ja possui cadastro no site
    usuario = db.query(UsuarioDB).filter(
        UsuarioDB.email == body.email
    ).first()
    
    if usuario:
        raise HTTPException(
            status_code=400,
            detail='Você já possui esse email cadastrado.'
        )

    # Verifica se a senha eh menor de 6 caracteres
    if len(body.senha_usuario) < 6 or len(body.confirmar_senha) < 6:
        raise HTTPException(
            status_code=400,
            detail='A senha precisa possuir mais de 6 caracteres'
        )

    # Verifica se senha e confirmar senha sao iguais
    senha = secrets.compare_digest(body.senha_usuario, body.confirmar_senha)
    if not senha:
        raise HTTPException(
            status_code=400,
            detail='As senhas devem ser iguais'
        )
    
    hash_senha = pwd_context.hash(body.senha_usuario)
    
    # Adiciona no banco de dados
    adicionar = UsuarioDB(
        nome_usuario=body.nome_usuario,
        senha_usuario=hash_senha,
        email=body.email,
    )
    
    db.add(adicionar)
    db.commit()
    db.refresh(adicionar)

    return {'message': 'Cadastro realizado com sucesso'}

# Envia o email para alterar a senha
@router.post('/site/enviar-email')
async def enviar_processo_recuperacao(usuario_token: UsuarioDB = Depends(verificar_token_access), db: Session = Depends(sessao_db)):
    # Verifica se o email existe
    email = db.query(UsuarioDB).filter(UsuarioDB.email == usuario_token.email).first()
    if email is None:
        raise HTTPException(
            status_code=404,
            detail='Esse email não existe!'
        )
    
    # 1. Gerar o Token
    expiracao = datetime.utcnow() + timedelta(minutes=15)
    payload = {"sub": usuario_token.email, "exp": expiracao}
    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
    
    # Informacoes enviadas para o broker
    dict_info = {
        'token':token,
        'email':usuario_token.email
    }
    
    # Envia a tarefa para o producer
    enviar_tarefa('enviar_email', dict_info)

    return {"message": "Processo iniciado! Verifique seu e-mail em instantes."}

# Altera a senha do usuario no banco de dados
@router.put('/site/alterar-senha')
async def alterar_senha(body: BODYResetSenhaRequest, db: Session = Depends(sessao_db), usuario: UsuarioDB = Depends(verificar_token_access)):
    # Verifica se a senhas sao iguais
    if not secrets.compare_digest(body.nova_senha, body.confirmar_senha):
        raise HTTPException(
            status_code=400,
            detail='As senhas devem ser iguais.'
        )
    # Vefifica se as senhas possem menos de 6 caracteres
    if len(body.nova_senha) < 6 or len(body.confirmar_senha) < 6:
        raise HTTPException(
            status_code=400,
            detail='A senha deve conter mais de 6 caracteres.'
        )
    
    # Verifica se a senha eh igual a que esta salva atualmente
    senha = pwd_context.verify(body.nova_senha, usuario.senha_usuario)
    if senha:
        raise HTTPException(
            status_code=400,
            detail='A senha não pode ser igual a senha atual.'
        )
    try:  
        # Atualiza para o novo hash
        usuario.senha_usuario = pwd_context.hash(body.nova_senha)
        
        db.add(usuario) # Garante que o objeto está na sessão
        db.commit()
        db.refresh(usuario)
        
        return {"message": "Senha alterada com sucesso!"}
        
    except Exception as e:
        db.rollback() # Desfaz alterações em caso de erro no banco
        raise HTTPException(status_code=500, detail=f"Erro interno ao salvar nova senha.")

# Exclui a conta do usuario
@router.delete('/site/deletar/conta')
async def excluir_usuario(body: BODYExcluirConta, db: Session = Depends(sessao_db), usuario_token: UsuarioDB = Depends(verificar_token_access)):
    # Verifica se a senha do usuario 
    senha = pwd_context.verify(body.senha, usuario_token.senha_usuario)
    if not senha:
        raise HTTPException(
            status_code=401,
            detail='Senha incorreta!'
        )

    db.query(UsuarioDB).filter(UsuarioDB.usuario_id == usuario_token.usuario_id).delete()
    db.commit()

    return {'message': 'Usuário deletado com sucesso!'}

@router.post('/login-form')
async def login_form(
    formulario: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(sessao_db)
    ):
    # Verifica se o email existe
    usuario = db.query(UsuarioDB).filter(UsuarioDB.email == formulario.username).first()
    senha_verificada = pwd_context.verify(formulario.password, usuario.senha_usuario)
    if not usuario or not senha_verificada:
        raise HTTPException(
            status_code=401,
            detail='Senha ou email incorretos!'
        )
    
    access_token = criar_token_acesso(email=usuario.email,db=db)
    refresh_token = criar_token_refresh(email=usuario.email,db=db)

    return {
        "access_token": access_token,
        "refresh_token":refresh_token,
        "token_type": "Bearer"
    }
