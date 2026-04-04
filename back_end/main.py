from fastapi import HTTPException,FastAPI,Depends,UploadFile,File,Form, Request, BackgroundTasks
from sqlalchemy.orm import Session
from fastapi.security import HTTPBasic,HTTPBasicCredentials
import os
import json
from dotenv import load_dotenv
load_dotenv(dotenv_path=".env")
import secrets
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from cryptography.fernet import Fernet
import hashlib
import jwt
from datetime import datetime, timedelta
from authlib.integrations.starlette_client import OAuth
from passlib.context import CryptContext
from email_validator import validate_email, EmailNotValidError
from fastapi.responses import FileResponse
import smtplib
from email.message import EmailMessage
from datetime import datetime, timedelta
from jose import JWTError,jwt
from auth_token import auth_router,criar_token_acesso,criar_token_refresh,verificar_token_access,verificar_token_refresh

TEMPO_ACESSO_GOOGLE = int(os.getenv("TEMPO_ACESSO_GOOGLE"))

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

oauth = OAuth()

oauth.register(
    name='google',
    client_id=os.getenv("CLIENT_ID"),
    client_secret=os.getenv("CLIENT_SECRECT"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={
        "scope": "openid email profile"
    }
)

app = FastAPI()

app.include_router(auth_router)

security = HTTPBasic()

# Chave criptografada
chave = os.getenv('CPF_CRYPTO_KEY')
fernet = Fernet(chave)

# criptografar
def criptografar(cpf: str):
    return fernet.encrypt(cpf.encode()).decode()

# Funcao para descriptografar
def descriptografar(cpf_criptografado: str):
    return fernet.decrypt(cpf_criptografado.encode()).decode()

# Adicione este bloco:
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permite qualquer origem (em produção, coloque o IP do front)
    allow_methods=["*"],
    allow_headers=["*"],    
)

app.mount("/uploads", StaticFiles(directory="fotos_produtos"), name="fotos_produtos")
app.mount("/front", StaticFiles(directory="../front_end"), name="front")

from banco_dados import (
    engine, SessionLocal, Base, redis_client, redis_client2, sessao_db,
    UsuarioDB, ProdutosLojaDB, CarrinhoUsuarioDB, CriarCarrinhoDB,
    EnderecoUsuarioDB, CartoesDB, ConfirmarPagamentoDB
)
from body_models import (
    BODYUsuario, BODYCadastrarUsuario, BODYProdutosLoja, BODYCarrinhoUsuario,
    BODYCriarCarrinho, BODYEnderecoUsuario, BODYCartao, BODYConfirmarPagamento,
    BODYCartaoPUT, BODYEnderecoUsuarioPUT, BODYProdutosLojaPUT,BODYRecuperarSenha,
    BODYResetSenhaRequest,BODYNomeEndereco
)

@app.get("/login/google")
async def login_google(request: Request):
    redirect_uri = request.url_for("auth_google")
    return await oauth.google.authorize_redirect(request, redirect_uri)

@app.get("/auth/google")
async def auth_google(request: Request, db: Session = Depends(sessao_db)):

    token = await oauth.google.authorize_access_token(request)
    user = token.get("userinfo")

    google_id = user["sub"]

    usuario = db.query(UsuarioDB).filter(
        UsuarioDB.google_id == google_id
    ).first()

    if not usuario:
        usuario = UsuarioDB(
            google_id=google_id,
            email=user["email"],
            nome_usuario=user["name"]
        )
        db.add(usuario)
        db.commit()
        db.refresh(usuario)

    token_jwt = criar_token_acesso(usuario.email,timedelta(hours=TEMPO_ACESSO_GOOGLE),db)

    return {
        "message": "Login realizado com sucesso",
        "token": token_jwt,
        "usuario": BODYUsuario.model_validate(usuario)
    }

    
# Autorizacao para adicionar um produto
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

# ------ End Points ------

# =========
# |  GET  |
# =========

# Carrega o front end de resetpassword
@app.get("/reset-password")
async def pagina_reset():
    # Isso faz o navegador abrir o seu arquivo HTML
    return FileResponse("reset-password.html")

# Mostra todoso os usuarios cadastrados
@app.get('/site/usuario')
async def mostrar_usuarios(db: Session = Depends(sessao_db),page: int = 1,limit: int = 20,usuario_id:int = None,nome_usuario: str = None,_:None = Depends(autorizacao)):
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
    
# Mostra todos os produtos cadastrados
@app.get('/site/produtos')
async def produtos_cadastrados(db: Session = Depends(sessao_db),produto_id:int = None,categoria_produto: str = None,page: int = 1,nome_produto:str = None):
    limit = 30
    if page < 1:
        raise HTTPException(
            status_code=400,
            detail='A pagina nao pode ser menos que 1'
        )
    
    key = f'produtos:page:{page}:limit:{limit}:categoria:{categoria_produto}:id:{produto_id}:nome_produto:{nome_produto}'

    cache = redis_client.get(key)
    if cache:
        
        return {'produtos':json.loads(cache),'ttl': redis_client.ttl(key)}

    produto = db.query(ProdutosLojaDB)
    # Filtra por nome
    if nome_produto is not None:
        produto = produto.filter(ProdutosLojaDB.nome_produto == nome_produto)

    # Filtra por categoria
    if categoria_produto is not None:
        produto = produto.filter(ProdutosLojaDB.categoria_produto == categoria_produto)

    # Filtro por id
    if produto_id is not None:
        produto = produto.filter(ProdutosLojaDB.produto_id == produto_id)
        
    produto_all = produto.offset((page-1)*limit).limit(limit).all()

    if not produto_all:
        raise HTTPException(
            status_code=404,
            detail='Ocorreu um erro na filtragem'
        )
    
    paginacao = [
        {
            'produto': valor.nome_produto,
            'preco': valor.preco_produto,
            'categoria': valor.categoria_produto,
            'produto_id': valor.produto_id
        }
        for valor in produto_all
    ]

    redis_client.setex(key,300,json.dumps(paginacao))

    return paginacao

# Mostra o carrinho do usuario
@app.get('/site/carrinho/{carrinho_id}')
async def mostrar_carrinho(carrinho_id: int = None,db: Session = Depends(sessao_db),usuario_token: UsuarioDB = Depends(verificar_token_access)):
    # Verifica se o usuario_id existe
    usuario = db.query(UsuarioDB).filter(UsuarioDB.usuario_id== usuario_token.usuario_id).first()
    if usuario is None:
        raise HTTPException(
            status_code=404,
            detail='Esse usuario nao existe'
        )
    
    # Filtra por carrinho_id
    carrinho = db.query(CarrinhoUsuarioDB)
    if carrinho_id is not None:
        carrinho = carrinho.filter(CarrinhoUsuarioDB.carrinho_id == carrinho_id)

    # Verifica se ha algo adicionado no carrinho do usuario
    carrinho_usuario = carrinho.filter(CarrinhoUsuarioDB.carrinho_usuario_id == usuario_token.usuario_id).all()
    if not carrinho_usuario:  
        raise HTTPException(
            status_code=400,
            detail='Nao existe nada adicionado no carrinho'
        )

    carrinho = [
        {
            'nome_produto':valor.produto_no_carrinho.nome_produto,
            'preco_produto': valor.produto_no_carrinho.preco_produto,
            'carrinho_id': valor.carrinho_id
        }
        for valor in carrinho_usuario
    ]

    # Lista com todos os carrinhos_id
    carrinhos_id = []
    for valor in carrinho:
        carrinhos_id.append(valor['carrinho_id'])

    carrinhos_id_formatado = list(set(carrinhos_id)) 
    
    # Criacao do dicionario que vai retornar corretamente cada carrinho
    lista = []
    for valor in carrinhos_id_formatado:
        lista.append({'carrinho_id':valor,'produtos':[],'soma_total': 0,})
   
    # for para adiiconar os items em cada carrinho
    for valor in carrinho:
        # Pega o index dos id do carrinho
        index = carrinhos_id_formatado.index(valor['carrinho_id'])
        # Adiciona no dicionario lista
        lista[index]['produtos'].append(valor)
        # Adiciona a soma total de produtos de cada carrinho
        lista[index]['soma_total'] += valor['preco_produto']
    
    return lista

# Mostra todo o redis
@app.get('/site/mostrar/redis-inteiro')
async def mostrar_todo_redis(_:None = Depends(autorizacao)):
    # Pega todas as chaves do redis
    keys = redis_client.keys('produtos:*')
    
    # Verifica se o redis esta vazio
    if not keys:
        raise HTTPException(
            status_code=404,
            detail='Nao ha nada cadastrado no redis'
        )
    
    lista = []
    for key in keys:
        valor = redis_client.get(key)
        ttl = redis_client.ttl(key)
        lista.append({'chave':key,'valor':json.loads(valor),'ttl':ttl})
    
    return lista

# Mostra os enderecos cadastrado do usuario
@app.get('/site/endereco')
async def mostrar_endereco(db: Session = Depends(sessao_db),usuario_token: UsuarioDB = Depends(verificar_token_access)):
    # Chave do redis que mostra o endereco
    key = f'endereco:{usuario_token.usuario_id}'
    # Verifica se o redis existe
    redis = redis_client2.get(key)
    # Retorna o redis caso exista
    if redis:
        return {'enderecos':json.loads(redis),'ttl':redis_client2.ttl(key)}
    
    # Verifica se o usuario tem algum endereco cadastrado existe
    endereco = db.query(EnderecoUsuarioDB).filter(EnderecoUsuarioDB.usuario_id == usuario_token.usuario_id).all()
    if not endereco:
        raise HTTPException(
            status_code=404,
            detail='Ainda nao ha nenhum endereco cadastrado'
        )
    
    dicionario_redis = []

    for valor in endereco:  
        dicionario_redis.append({
            'usuario_id': valor.usuario_id,
            'endereco_nomeado': valor.endereco_nomeado,
            'bairro': valor.bairro,
            'numero': valor.numero,
            'cidade': valor.cidade,
            'estado': valor.estado,
            'complementeo': valor.complemento,
            'cep': valor.cep
        })

    redis_client2.setex(f'endereco:{usuario_token.usuario_id}',300,json.dumps(dicionario_redis))

    return {'enderecos':dicionario_redis}

# ==============
# |    POST    |
# ==============

# Adiciona um produto no site
@app.post('/site/produto/adicionar')
async def adicionar_produto(
    nome_produto: str = Form(...),
    preco_produto: float = Form(...),
    categoria_produto: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(sessao_db),
    __: None = Depends(autorizacao)
    ):
    import uuid
    import shutil

    # 1. Validação básica (sem ler o conteúdo ainda)
    if not file.content_type.startswith("image/"):
        return {"erro": "O arquivo enviado não é uma imagem válida."}
    
    extensao = file.filename.split(".")[-1]
    nome_unico = f"{uuid.uuid4()}.{extensao}"
    caminho_no_disco = f"fotos_produtos/{nome_unico}"

     # 3. Salvar o arquivro
    try:
        with open(caminho_no_disco, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        return {"erro": f"Falha ao salvar arquivo: {str(e)}"}


    produto = ProdutosLojaDB(
        nome_produto=nome_produto,
        preco_produto=preco_produto,
        categoria_produto=categoria_produto,
        url_foto_produto=caminho_no_disco
    )
    
    db.add(produto)
    db.commit()
    
    # Exclui tudo que esta no redis
    key = 'produtos:*'
    keys = redis_client.keys(key)
    # For para excluir todas as chaves
    for key in keys:
        redis_client.delete(key)

    return {
        'message':f'produto {nome_produto} cadastrado com sucesso',
        'nome_arquvio':nome_unico
    }

# Adicionar produto no carrinho
@app.post('/site/carrinho')
async def adicionar_produto_carrinho(body: BODYCarrinhoUsuario, db: Session = Depends(sessao_db),usuario_token: UsuarioDB = Depends(verificar_token_access)):
    # Verifica se o carrinho existe
    existe_carrinho = db.query(CriarCarrinhoDB).filter(CriarCarrinhoDB.usuario_id == usuario_token.usuario_id, CriarCarrinhoDB.carrinho_id == body.carrinho_id).first()
    if existe_carrinho is None:
        raise HTTPException(
            status_code=400,
            detail='Esse carrinho nao existe'
        )
    
    # Verifica se o produto existe
    produto = db.query(ProdutosLojaDB).filter(ProdutosLojaDB.produto_id == body.produto_id).first()
    if produto is None:
        raise HTTPException(
            status_code=404,
            detail='Esse produto nao existe'
        )
    
    # Adiciona o produto no carrinho
    carrinho = CarrinhoUsuarioDB(**body.model_dump(),carrinho_usuario_id=usuario_token.usuario_id)
    db.add(carrinho)
    db.commit()
    db.refresh(carrinho)

    return carrinho


# Cria um carrinho
@app.post('/site/criar/carrinho')
async def criar_carrinho(body: BODYCriarCarrinho,db: Session = Depends(sessao_db),usuario_token: UsuarioDB = Depends(verificar_token_access)):
    # Verifica se o carrinho ja existe
    carrinho = db.query(CriarCarrinhoDB).filter(CriarCarrinhoDB.usuario_id == usuario_token.usuario_id, CriarCarrinhoDB.carrinho_id == body.carrinho_id).first()
    if carrinho:
        raise HTTPException(
            status_code=400,
            detail='Esse carrinho ja existe'
        )

    # Cria um carrinho
    criar_carrinho = CriarCarrinhoDB(**body.model_dump(),usuario_id=usuario_token.usuario_id)
    db.add(criar_carrinho)
    db.commit()
    db.refresh(criar_carrinho)

    return criar_carrinho   

# Adiciona um endereco da casa do usuario
@app.post('/site/endereco')
async def criar_endereco(body:BODYEnderecoUsuario ,db: Session = Depends(sessao_db),usuario_token: UsuarioDB = Depends(verificar_token_access)):
    # Verifica se a quantidade de enderecos ultrapassou 3
    quantidade_enderecos = db.query(EnderecoUsuarioDB).filter(EnderecoUsuarioDB.usuario_id == usuario_token.usuario_id).count()
    if quantidade_enderecos >= 10:
        raise HTTPException(
            status_code=400,
            detail='Voce ja atingiu o limite de enderecos cadastrados'
        )
    
    # Verifica se o endereco ja existe
    endereco = db.query(EnderecoUsuarioDB).filter(EnderecoUsuarioDB.usuario_id == usuario_token.usuario_id, EnderecoUsuarioDB.endereco_nomeado == body.endereco_nomeado).first()
    if endereco:
        raise HTTPException(
            status_code=400,
            detail='Esse endereco ja existe'
        )
    
    # Adiciona o endereco no banco de dados
    adicionar_endereco = EnderecoUsuarioDB(**body.model_dump(),usuario_id=usuario_token.usuario_id)
    db.add(adicionar_endereco)
    db.commit()
    db.refresh(adicionar_endereco)

    # -------- Exclui todas as informacoes do redis no endereco --------
    
    # Verifica se tem algo adicionado no redis
    valor = redis_client2.get(f'endereco:{usuario_token.usuario_id}')
    if valor:
        redis_client2.delete(f'endereco:{usuario_token.usuario_id}')


    return adicionar_endereco

# Adiciona a forma de pagamento
@app.post('/site/pagamento', response_model=BODYCartao)
async def adicionar_forma_pagamento(body: BODYCartao, db: Session = Depends(sessao_db),usuario_token: UsuarioDB = Depends(verificar_token_access)):
    # Verifica nome duplicado
    if db.query(CartoesDB).filter(
        CartoesDB.nome_cartao == body.nome_cartao,
        CartoesDB.usuario_id == usuario_token.usuario_id
    ).first():
        raise HTTPException(400, 'Você já possui um cartão com esse nome')

    # Deve ter pelo menos um tipo de cartão
    if not (body.cartao_credito or body.cartao_debito):
        raise HTTPException(400, 'Você deve informar um cartão')

    # Número do cartão (crédito ou débito)
    numero = body.cartao_credito or body.cartao_debito
    numero_limpo = numero.replace(" ", "")

    # Validação simples: apenas dígitos e tamanho 13-19
    if not numero_limpo.isdigit() or not 13 <= len(numero_limpo) <= 19:
        raise HTTPException(400, 'Número do cartão inválido')

    # Gera hash
    hash_cartao = hashlib.sha256(numero_limpo.encode()).hexdigest()

    # Verifica duplicidade por usuário
    if db.query(CartoesDB).filter(
        CartoesDB.hash_cartao == hash_cartao,
        CartoesDB.usuario_id == usuario_token.usuario_id
    ).first():
        raise HTTPException(400, 'Não foi possível processar o cadastro do cartão')

    # Criptografa números
    cartao_credito = criptografar(numero_limpo) if body.cartao_credito else None
    cartao_debito = criptografar(numero_limpo) if body.cartao_debito else None

    # Salva apenas hash e últimos 4
    novo_cartao = CartoesDB(
        usuario_id=usuario_token.usuario_id,
        nome_cartao=body.nome_cartao,
        hash_cartao=hash_cartao,
        cartao_credito=cartao_credito,
        cartao_debito=cartao_debito,
        nome_do_usuario_do_cartao=body.nome_do_usuario_do_cartao,
        data_validade_cartao=body.data_validade_cartao,
        ultimos_4=numero_limpo[-4:]
    )

    db.add(novo_cartao)
    db.commit()
    db.refresh(novo_cartao)

    return novo_cartao

# Finaliza o pagamento
@app.post('/site/finalizar-compra')
async def finalizar_compra(body: BODYConfirmarPagamento, db: Session = Depends(sessao_db),usuario_token: UsuarioDB = Depends(verificar_token_access)):
    # Verifica se o usuario ja possui um endereco
    endereco = db.query(EnderecoUsuarioDB).filter(EnderecoUsuarioDB.usuario_id == usuario_token.usuario_id,  EnderecoUsuarioDB.endereco_nomeado == body.endereco_nomeado).first()
    # Tratamento de erro caso nao exista o endereco
    if endereco is None:
        raise HTTPException(
            status_code=404,
            detail='Voce nao possui esse endereco'
        )
    
    # Verifica se a forma de pagamento existe
    pagamento = db.query(CartoesDB).filter(CartoesDB.usuario_id == usuario_token.usuario_id,CartoesDB.nome_cartao == body.nome_cartao).first()
    if pagamento is None:
        raise HTTPException(
            status_code=404,
            detail='Adicione alguma forma de pagamento'
        )

    # Verifica se o carrinho existe
    carrinho = db.query(CarrinhoUsuarioDB).filter(CarrinhoUsuarioDB.carrinho_id == body.carrinho_id, CarrinhoUsuarioDB.carrinho_usuario_id == usuario_token.usuario_id).all()
    if not carrinho:
        raise HTTPException(
            status_code=404,
            detail='Adicione um carriho que exista'
        )
    
    # Salva para ser usado como formtacao no return para atribuir preco,nome e categoria do produto
    produtos = [
            {
                'preco': valor.produto_no_carrinho.preco_produto,
                'nome_produto': valor.produto_no_carrinho.nome_produto,
                'categoria': valor.produto_no_carrinho.categoria_produto
            }
            for valor in carrinho
        ]

    # Envia o produto para o endereco
    envio = ConfirmarPagamentoDB(**body.model_dump(),usuario_id=usuario_token.usuario_id)
    
    db.add(envio)
    
    # Deleta o carrinho que o usuario escolheu
    db.query(CarrinhoUsuarioDB).filter(CarrinhoUsuarioDB.carrinho_usuario_id == usuario_token.usuario_id, CarrinhoUsuarioDB.carrinho_id == body.carrinho_id).delete()
   
    # Deleta o carrinho em criar carrinho 
    db.query(CriarCarrinhoDB).filter(CriarCarrinhoDB.usuario_id == usuario_token.usuario_id, CriarCarrinhoDB.carrinho_id == body.carrinho_id).delete()
    db.commit()
    db.refresh(envio)


    return {
        'message':'Envio realizado com sucesso.',
        'endereco': f'Endereço de envio: bairro:{envio.endereco.bairro},número: {envio.endereco.numero},estado: {envio.endereco.estado},cidade: {envio.endereco.cidade},cep: {envio.endereco.cep}',
        'usuario': f'carrinho escolhido: {body.carrinho_id}',
        'Produtos enviados': produtos
        }
    
# Login no site pelo site
@app.post('/site/login-usuario')
async def login_site_usuario(body: BODYUsuario, db: Session = Depends(sessao_db)):
    # Verifica se o usuario existe
    usuario = db.query(UsuarioDB).filter(UsuarioDB.email == body.email).first()
    if usuario is None:
        raise HTTPException(
            status_code=404,
            detail='Senha ou email incorretos'
        )
    
    senha_valida = pwd_context.verify(body.senha_usuario, usuario.senha_usuario)
    if not senha_valida:
        raise HTTPException(
            status_code=401,
            detail='Senha ou email incorretos'
        )
    
    access_token = criar_token_acesso(body.email,db=db)
    refresh_token = criar_token_refresh(body.email,db=db)

    return {
        'access_token':access_token,
        'refresh_token':refresh_token,
        'type':'Bearer'
    }


# Cadastra no site pelo site
@app.post('/site/cadastro-usuario')
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
    if len(body.senha_usuario) < 6:
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

    return {'message':'Cadastro realizado com sucesso'}

# Carrega as configurações do seu .env
SECRET_KEY = os.getenv("SECRET_KEY")
EMAIL_USER = os.getenv("EMAIL_USER")  # Seu e-mail 
EMAIL_PASS = os.getenv("EMAIL_PASS")  # Sua senha
SMTP_SERVER = os.getenv("SMTP_SERVER")        # Exemplo para Gmail
SMTP_PORT = int(os.getenv("SMTP_PORT",465))

# Envia o email para alterar a senha
@app.post('/site/enviar-email')
async def enviar_processo_recuperacao(body: BODYRecuperarSenha,background_tasks: BackgroundTasks,db: Session = Depends(sessao_db)):
    # Verifica se o email existe
    email = db.query(UsuarioDB).filter(UsuarioDB.email == body.email).first()
    if email is None:
        raise HTTPException(
            status_code=404,
            detail='Esse email não existe!'
        )
    
    # 1. Gerar o Token
    expiracao = datetime.utcnow() + timedelta(minutes=15)
    payload = {"sub": body.email, "exp": expiracao}
    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")

    # 2. Criar a Mensagem
    msg = EmailMessage()
    msg['Subject'] = "Recuperação de Senha"
    msg['From'] = EMAIL_USER
    msg['To'] = body.email
    
    link = f"https://seuecommerce.com.br/reset-password?token={token}"
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
    def disparar_email(mensagem, server, port, user, password):
        with smtplib.SMTP_SSL(server, port) as smtp:
            smtp.login(user, password)
            smtp.send_message(mensagem)

    # Adicionamos a tarefa para rodar depois da resposta
    background_tasks.add_task(disparar_email, msg, SMTP_SERVER, SMTP_PORT, EMAIL_USER, EMAIL_PASS)

    return {"message": "Processo iniciado! Verifique seu e-mail em instantes."}

# ===============
# |    DELETE   |
# ===============

# Deleta todo o redis
@app.delete('/site/redis')
async def deletar_redis():
    # Pega todas as chaves do redis
    keys = redis_client.keys('produtos:*')
    # Verifica se o redis existe
    if not keys:
        raise HTTPException(
            status_code=400,
            detail='Nao existe nada no redis'
        )
    # Deleta todo o redis
    for key in keys:
        redis_client.delete(key)
    
    return {'message':'todo o redis foi deletado'}

# Deleta um endereco do usuario
@app.delete('/site/endereco/{nome_endereco}')
async def deletar_endereco(nome_endereco: str, db: Session = Depends(sessao_db),usuario_token: UsuarioDB = Depends(verificar_token_access)):
    # Verifica se o usuario existe e o endereco existem
    verificacao = db.query(EnderecoUsuarioDB).filter(EnderecoUsuarioDB.usuario_id == usuario_token.usuario_id, EnderecoUsuarioDB.endereco_nomeado == nome_endereco).first()
    if verificacao is None:
        raise HTTPException(
            status_code=404,
            detail='Esse endereço não existe!'
        )
    # Deleta o endereco
    db.delete(verificacao)
    db.commit()

    # Deleta o endereco no redis
    key = redis_client2.get(f'endereco:{usuario_token.usuario_id}')
    # Verifica se existe
    if key:
        # Trasforma em dicionario
        lista = json.loads(key)
        for i,v in enumerate(lista):
            if v['endereco_nomeado'] == nome_endereco:
                del lista[i]
        
        redis_client2.setex(f'endereco:{usuario_token.usuario_id}',300,json.dumps(lista))
    
    return {'message':'Endereço deletado com sucesso!'}

# Deletar carrinho
@app.delete('/site/carrinho/{carrinho_id}')
async def deletar_carrinho(carrinho_id: int, db: Session = Depends(sessao_db),usuario_token: UsuarioDB = Depends(verificar_token_access)):
    # Verifica se o usuario possui esse carrinho
    carrinho = db.query(CriarCarrinhoDB).filter(CriarCarrinhoDB.usuario_id == usuario_token.usuario_id, CriarCarrinhoDB.carrinho_id).first()
    if carrinho is None:
        raise HTTPException(
            status_code=404,
            detail='Esse usuário não possui esse carrinho!'
        )
    # Deleta o carrinho que esta no Banco de Dados CriarCarrinhoDB
    db.delete(carrinho)
    # Deleta o carrinho que esta em CarrinhoUsuarioDB
    carrinho_usuario = db.query(CarrinhoUsuarioDB).filter(CarrinhoUsuarioDB.carrinho_usuario_id == usuario_token.usuario_id, CarrinhoUsuarioDB.carrinho_id == carrinho_id).delete()
    db.commit()

    return {'message':f'Carrinho {carrinho_id} deletado com sucesso'}

# Deleta um cartao cadastrado
@app.delete('/site/cartoes/{nome_cartao}')
async def deletar_cartao(nome_cartao:str, db: Session = Depends(sessao_db),usuario_token: UsuarioDB = Depends(verificar_token_access)):
    # Verifica se o cartao existe
    cartao = db.query(CartoesDB).filter(CartoesDB.usuario_id == usuario_token.usuario_id, CartoesDB.nome_cartao == nome_cartao).first()
    if cartao is None:
        raise HTTPException(
            status_code=404,
            detail='Esse cartao nao existe'
        )
    db.delete(cartao)
    db.commit()

    return {'message':'Cartao excluido com sucesso'}

# Deleta um item de um carrinho
@app.delete('/site/carrinho-item/{carrinho_id}/{produto_id}')
async def deletar_produto_carrinho(carrinho_id: int,produto_id: int, db: Session = Depends(sessao_db),usuario_token: UsuarioDB = Depends(verificar_token_access)):
    # Verifica se o item existe no carrinho do usuario
    item_carrinho = db.query(CarrinhoUsuarioDB).filter(CarrinhoUsuarioDB.produto_id == produto_id, CarrinhoUsuarioDB.carrinho_usuario_id == usuario_token.usuario_id, CarrinhoUsuarioDB.carrinho_id == carrinho_id).first()
    if item_carrinho is None:
        raise HTTPException(
            status_code=404,
            detail='Item não encontrado.'
        )
    db.delete(item_carrinho)
    db.commit()

    return {'message':f'Item deletado com sucesso'}

# Exclui a conta do usuario
@app.delete('/site/deletar/conta/{usuario_id}')
    

# ===========
# |   PUT   |
# ===========

# Altera o cartao ja cadastrado
@app.put('/site/cartao/{nome_cartao}')
async def alterar_cartao(nome_cartao: str, body: BODYCartaoPUT, db: Session = Depends(sessao_db),usuario_token: UsuarioDB = Depends(verificar_token_access)):
    
    cartao_db = db.query(CartoesDB).filter(
        CartoesDB.usuario_id == usuario_token.usuario_id,
        CartoesDB.nome_cartao == nome_cartao
    ).first()

    if cartao_db is None:
        raise HTTPException(
            status_code=404,
            detail='Cartão não encontrado'
        )

    # ❗ Deve enviar pelo menos um número
    if body.cartao_credito is None and body.cartao_debito is None:
        raise HTTPException(
            status_code=400,
            detail='Dados inválidos'
        )

    # ❗ Não pode enviar os dois
    if body.cartao_credito and body.cartao_debito:
        raise HTTPException(
            status_code=400,
            detail='Dados inválidos'
        )

    # 🔐 Atualiza número do cartão
    numero = body.cartao_credito or body.cartao_debito
    numero_limpo = numero.replace(" ", "")

    # ✅ Validação correta (ANTES de criptografar)
    if not numero_limpo.isdigit() or not 13 <= len(numero_limpo) <= 19:
        raise HTTPException(400, 'Número do cartão inválido')

    # 🔑 Novo hash
    hash_cartao = hashlib.sha256(numero_limpo.encode()).hexdigest()

    # 🔍 Verifica duplicidade
    cartao_existente = db.query(CartoesDB).filter(
        CartoesDB.hash_cartao == hash_cartao,
        CartoesDB.usuario_id == usuario_token.usuario_id,
        CartoesDB.id != cartao_db.id  # evita conflito com ele mesmo
    ).first()

    if cartao_existente:
        raise HTTPException(400, 'Não foi possível atualizar o cartão')

    # 🔐 Criptografa
    numero_criptografado = criptografar(numero_limpo)

    if body.cartao_credito:
        cartao_db.cartao_credito = numero_criptografado
        cartao_db.cartao_debito = None
    else:
        cartao_db.cartao_debito = numero_criptografado
        cartao_db.cartao_credito = None

    # 💾 Atualiza dados auxiliares
    cartao_db.hash_cartao = hash_cartao
    cartao_db.ultimos_4 = numero_limpo[-4:]

    # 📝 Outros campos opcionais
    if body.data_validade_cartao:
        cartao_db.data_validade_cartao = body.data_validade_cartao

    if body.nome_do_usuario_do_cartao:
        cartao_db.nome_do_usuario_do_cartao = body.nome_do_usuario_do_cartao

    if body.nome_cartao:
        cartao_db.nome_cartao = body.nome_cartao

    db.commit()
    db.refresh(cartao_db)

    return {"message": "Cartão atualizado com sucesso"}

# Altera o endereco do usuario
@app.put('/site/alterar-endereco/{endereco_nomeado}')
async def alterar_endereco(
    endereco_nomeado: str, 
    body: BODYEnderecoUsuarioPUT, 
    db: Session = Depends(sessao_db),
    usuario_token: UsuarioDB = Depends(verificar_token_access)
    ):
    # Verifica se o usuario possui esse endereco
    endereco = db.query(EnderecoUsuarioDB).filter(
        EnderecoUsuarioDB.usuario_id == usuario_token.usuario_id,
        EnderecoUsuarioDB.endereco_nomeado == endereco_nomeado
    ).first()
    if endereco is None:
        raise HTTPException(
            status_code=404,
            detail='Esse endereço não existe'
        )
    
    # Verifica se o campo endereco_nomeado esta preenchido
    if body.endereco_nomeado is not None:
        endereco.endereco_nomeado = body.endereco_nomeado
    # Verifica se o campo bairro esta preenchido
    if body.bairro is not None:
        endereco.bairro = body.bairro
    # Verifica se o campo numero esta preenchido
    if body.numero is not None:
        endereco.numero = body.numero
    # Verifica se o campo cidade esta preenchido
    if body.cidade is not None:
        endereco.cidade = body.cidade
    # Verifica se o campo estado esta preenchido
    if body.estado is not None:
        endereco.estado = body.estado
    # Verifica se o campo cep esta preenchido
    if body.cep is not None:
        endereco.cep = body.cep
    # Verifica se o campo complemento esta vazio
    if body.complemento is not None:
        endereco.complemento = body.complemento
    
    db.commit()
    db.refresh(endereco)

    return endereco

# Altera informacoes de um produto
@app.put('/site/alterar-produto/{produto_id}')
async def alterar_produto(
    produto_id: int,
    body: BODYProdutosLojaPUT,
    db: Session = Depends(sessao_db),
    _: None = Depends(autorizacao)
    ):
    
    # Verifica se o produto existe
    produto = db.query(ProdutosLojaDB).filter(
        ProdutosLojaDB.produto_id == produto_id
    ).first()

    if produto is None:
        raise HTTPException(
            status_code=404,
            detail='Esse produto não existe'
        )
    
    # Verifica se o campo nome esta preenchido
    if body.nome_produto is not None:
        produto.nome_produto = body.nome_produto
    # Verifica se o campo preco esta preenchido
    if body.preco_produto is not None:
        produto.preco_produto = body.preco_produto
    # Verifica se o campo categoria esta preenchido
    if body.categoria_produto is not None:
        produto.categoria_produto = body.categoria_produto

    db.commit()
    db.refresh(produto)

    # Deleta todo o redis que armazena os produtos
    keys = redis_client.keys('produtos:*')
    for key in keys:
        redis_client.delete(key)

    return {'message':'Produto alterado com sucesso'}


# Altera a senha do usuario no banco de dados
@app.put('/site/alterar-senha')
async def alterar_senha(body: BODYResetSenhaRequest, db: Session = Depends(sessao_db),usuario: UsuarioDB = Depends(verificar_token_access)):
    # Verifica se a senhas sao iguais
    if not secrets.compare_digest(body.nova_senha,body.confirmar_senha):
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
    senha = pwd_context.verify(body.nova_senha,usuario.senha_usuario)
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

# COLOCAR O JWT OU USUARIO ID NO REDIS

# PASSAR O NOME ENDERECO COMO UM NOVO BODY