import os
from pydantic import EmailStr
import secrets
from jose import jwt,JWTError
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from passlib.context import CryptContext

from banco_dados import sessao_db, UsuarioDB
from auth_token import verificar_token_access, criar_token_acesso, criar_token_refresh
from body_models import BODYUsuario, BODYCadastrarUsuario, BODYEnviarEmailParaExcluirConta,BODYResetSenhaRequest,BODYRecuperarSenha,BODYExcluirConta
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
SECRET_KEY_TOKEN = os.getenv("SECRET_KEY_TOKEN")

# Carrega o front end de resetpassword
@router.get("/reset-password")
async def pagina_reset():
    # Isso faz o navegador abrir o seu arquivo HTML
    return FileResponse("reset-password.html")



# Mostra todos os usuarios cadastrados
@router.get('/site/usuario')
async def mostrar_usuarios(
    db: Session = Depends(sessao_db), 
    page: int = 1, 
    usuario_id: int = None, 
    nome_usuario: str = None,
    _: None = Depends(autorizacao)
    ):
    limit = 20
    
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
    # Verifica se o usuario existe e se estar ativo
    usuario = db.query(UsuarioDB).filter(UsuarioDB.email == body.email, UsuarioDB.usuario_ativo == True).first()
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
    
    if usuario and usuario.usuario_ativo:
        raise HTTPException(
            status_code=400,
            detail='Esse email já existe.'
        )

    # Verifica se a senha eh menor de 6 caracteres
    if len(body.senha_usuario) < 6 or len(body.confirmar_senha) < 6:
        raise HTTPException(
            status_code=400,
            detail='A senha precisa possuir mais de 6 caracteres'
        )

    # Verifica se senha e confirmar senha sao iguais
    if body.senha_usuario != body.confirmar_senha:
        raise HTTPException(
            status_code=400,
            detail='As senhas devem ser iguais'
        )
    
    hash_senha = pwd_context.hash(body.senha_usuario)
    
    # Adiciona no banco de dados
    if usuario is None:
        usuario = UsuarioDB(
            nome_usuario=body.nome_usuario,
            senha_usuario=hash_senha,
            email=body.email,
        )
    
        db.add(usuario)
    else:
        usuario.nome_usuario = body.nome_usuario
        usuario.senha_usuario = hash_senha
        usuario.usuario_ativo = True
    
    db.commit()
    db.refresh(usuario)

    return {'message': 'Cadastro realizado com sucesso'}



# Envia o email para alterar a senha
@router.post('/site/alterar-senha/enviar-email')
async def enviar_processo_recuperacao(body: BODYRecuperarSenha, db: Session = Depends(sessao_db)):
    # Verifica se o email existe
    email = db.query(UsuarioDB).filter(UsuarioDB.email == body.email, UsuarioDB.usuario_ativo == True).first()
    if email is None:
        raise HTTPException(
            status_code=404,
            detail='Esse email não existe!'
        )
    
    # 1. Gerar o Token
    expiracao = datetime.now(timezone.utc) + timedelta(minutes=15)
    payload = {"sub": body.email, "exp": expiracao}
    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
    
    # Informacoes enviadas para o broker
    dict_info = {
        'token':token,
        'email':body.email
    }
    
    # Envia a tarefa para o producer
    enviar_tarefa('enviar_email', dict_info)

    return {"message": "Processo iniciado! Verifique seu e-mail em instantes."}



# Altera a senha do usuario no banco de dados
@router.patch('/site/alterar-senha')
async def alterar_senha(body: BODYResetSenhaRequest, db: Session = Depends(sessao_db)):
    try:
        payload = jwt.decode(body.token,SECRET_KEY,algorithms=["HS256"])
        email = payload.get('sub')
    except JWTError:
        raise HTTPException(
            status_code=401,
            detail='Token inválido!'
        )
    
    # Pega as informacoes do usuario
    usuario = db.query(UsuarioDB).filter(UsuarioDB.email == email, UsuarioDB.usuario_ativo == True).first()
    if usuario is None:
        raise HTTPException(
            status_code=404,
            detail='Esse email não existe!'
        )

    # Verifica se a senhas sao iguais
    if not secrets.compare_digest(body.nova_senha, body.confirmar_senha):
        raise HTTPException(
            status_code=400,
            detail='As senhas devem ser iguais.'
        )
    # Vefifica se as senhas possem menos de 6 caracteres
    if len(body.nova_senha) < 6:
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


# Envia um email para que o usuari confime se quer excluir a conta
@router.post('/site/deletar/conta')
async def enviar_email_para_excluir_usuario(
    body: BODYEnviarEmailParaExcluirConta,
    usuario_token: UsuarioDB = Depends(verificar_token_access)
    ):
    # VALIDAÇÃO DO E-MAIL: Garante que o e-mail digitado pertence ao token logado
    if body.email != usuario_token.email:
        raise HTTPException(
            status_code=400,
            detail='O e-mail informado não confere com o e-mail da conta logada.'
        )

    # VALIDAÇÃO DA SENHA (Apenas se o usuário tiver senha definida no banco)
    if usuario_token.senha_usuario:
        # Se ele tem senha no banco, ele obrigatoriamente precisa mandar a senha no body
        if not body.senha:
            raise HTTPException(
                status_code=400,
                detail='A senha é obrigatória para usuários com cadastro tradicional.'
            )
            
        # Valida se a senha é a que esta cadastrada
        senha_valida = pwd_context.verify(body.senha, usuario_token.senha_usuario)
        if not senha_valida:
            raise HTTPException(
                status_code=401,
                detail='Senha incorreta!'
            )

    # Gerar o Token
    expiracao = datetime.now(timezone.utc) + timedelta(minutes=30)
    payload = {"sub": body.email, "exp": expiracao}
    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")

    # Informacoes enviadas para o broker
    dict_info = {
        'token':token,
        'email': body.email
    }

    enviar_tarefa('enviar_email_para_excluir_conta',dict_info)

    return {'message': 'Confirme a exclusão da sua conta no email.'}



# Envia um email pro usuario confirmar a exclusao da conta dele
@router.patch('/site/conta/desativar')
async def enviar_email_para_excluir_usuario(
    body: BODYExcluirConta,
    db: Session = Depends(sessao_db),
    ):
    try:
        payload = jwt.decode(body.token,SECRET_KEY,algorithms=['HS256'])
        email = payload.get('sub')
    except JWTError:
        raise HTTPException(
            status_code=401,
            detail='Token inválido!'
        )
    
    usuario = db.query(UsuarioDB).filter(UsuarioDB.email == email).first()
    # Verifica se o email existe
    if not usuario:
        raise HTTPException(
            status_code=404,
            detail='Esse email não existe!'
        )
    
    # Exclusao logica
    usuario.usuario_ativo = False
    
    db.commit()
    db.refresh(usuario)

    return {'message':'Sua conta foi delatada com sucesso!'}



# Login pelo fastapi forms
@router.post('/login-form')
async def login_form(
    formulario: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(sessao_db)
    ):
    # Verifica se o email existe e se o usuario estar ativo
    usuario = db.query(UsuarioDB).filter(UsuarioDB.email == formulario.username,UsuarioDB.usuario_ativo == True).first()
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
