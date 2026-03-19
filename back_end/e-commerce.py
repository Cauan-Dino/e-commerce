import redis
from fastapi import HTTPException,FastAPI,Depends,UploadFile,File,Form
from sqlalchemy.orm import sessionmaker,declarative_base,Mapped,mapped_column,relationship,Session
from sqlalchemy import create_engine,ForeignKey     
from fastapi.security import HTTPBasic,HTTPBasicCredentials
import os
from pydantic import BaseModel
import json
from dotenv import load_dotenv
load_dotenv(dotenv_path=".env")
from typing import Optional
import secrets
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from cryptography.fernet import Fernet
import hashlib


app = FastAPI()
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

# Criacao do banco de dados
engine = create_engine(os.getenv('DATABASE_URL'),connect_args={'check_same_thread': False})
SessionLocal = sessionmaker(autoflush=False,autocommit=False,bind=engine)
Base = declarative_base()
redis_client = redis.Redis(host='localhost',db=0,decode_responses=True,port=6379)
redis_client2 = redis.Redis(host='localhost',db=1,decode_responses=True,port=6379)

# Criacao das tabelas do banco de dados

# Tabela Usuario
class UsuarioDB(Base):
    __tablename__ = 'usuario'
    usuario_id: Mapped[int] = mapped_column(primary_key=True,index=True)
    nome_usuario: Mapped[str] = mapped_column(index=True)
    cpf: Mapped[str] = mapped_column(index=True,unique=True)
    hash_cpf: Mapped[str] = mapped_column(unique=True)

    carrinho = relationship('CarrinhoUsuarioDB', back_populates='usuario')

# Tabela produtos cadastrados na loja
class ProdutosLojaDB(Base):
    __tablename__ = 'produtos_loja'
    produto_id: Mapped[int] = mapped_column(primary_key=True,index=True)
    nome_produto: Mapped[str] = mapped_column(index=True)
    preco_produto: Mapped[float] = mapped_column(index=True)
    categoria_produto: Mapped[str] = mapped_column(index=True)
    url_foto_produto: Mapped[str] = mapped_column()

    carrinho = relationship('CarrinhoUsuarioDB',back_populates='produto_no_carrinho')

# Tabela que permite adicionar itens no carrinho do usuario
class CarrinhoUsuarioDB(Base):
    __tablename__ = 'carrinho'
    id: Mapped[int] = mapped_column(index=True,primary_key=True)

    carrinho_id: Mapped[int] = mapped_column(ForeignKey('criar_carrinho.carrinho_id'),index=True)
    carrinho_usuario_id: Mapped[int] = mapped_column(ForeignKey('usuario.usuario_id'),index=True)
    produto_id: Mapped[int] = mapped_column(ForeignKey('produtos_loja.produto_id'),index=True)

    usuario = relationship('UsuarioDB', back_populates='carrinho')
    produto_no_carrinho = relationship('ProdutosLojaDB',back_populates='carrinho')
    criar_carrinho = relationship('CriarCarrinhoDB',back_populates='carrinho_usuario')
    confirmar_pagamento = relationship('ConfirmarPagamentoDB',back_populates='carrinho')

# Tabela que cria o carrinho
class CriarCarrinhoDB(Base):
    __tablename__ = 'criar_carrinho'
    id: Mapped[int] = mapped_column(index=True,primary_key=True)

    carrinho_id: Mapped[int] = mapped_column(index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey('usuario.usuario_id'),index=True)

    carrinho_usuario = relationship('CarrinhoUsuarioDB',back_populates='criar_carrinho')

# Tabela do endereco do usuario
class EnderecoUsuarioDB(Base):
    __tablename__ = 'endereco_usuario'
    id: Mapped[int] = mapped_column(primary_key=True,index=True)

    usuario_id: Mapped[int] = mapped_column(ForeignKey('usuario.usuario_id'),index=True)
    
    endereco_nomeado: Mapped[str] = mapped_column(index=True)
    bairro: Mapped[str] = mapped_column(index=True)
    numero: Mapped[int] = mapped_column(nullable=True)
    cidade: Mapped[str] = mapped_column(index=True)
    estado: Mapped[str] = mapped_column(index=True)
    cep: Mapped[str] = mapped_column(index=True)
    complemento: Mapped[str] = mapped_column(index=True,nullable=True)

    confirmar_pagamento = relationship('ConfirmarPagamentoDB',back_populates='endereco')

# Tabela que cadastra os cartoes de credito
class CartoesDB(Base):
    __tablename__ = 'cartoes'
    id: Mapped[int] = mapped_column(index=True,primary_key=True)
    
    usuario_id: Mapped[int] = mapped_column(index=True)
    nome_cartao: Mapped[str] = mapped_column(index=True)
    hash_cartao: Mapped[str] = mapped_column(index=True,unique=True)    
    cartao_credito: Mapped[str] = mapped_column(index=True,unique=True,nullable=True)
    cartao_debito: Mapped[str] = mapped_column(index=True,unique=True,nullable=True)
    nome_do_usuario_do_cartao: Mapped[str] = mapped_column(index=True)
    cvc: Mapped[str] = mapped_column(index=True)
    data_validade_cartao: Mapped[str] = mapped_column(index=True)

# Tabela que confirma o pagemnto
class ConfirmarPagamentoDB(Base):
    __tablename__ = 'confirmar_pagamento'
    id: Mapped[int] = mapped_column(index=True,primary_key=True)
    usuario_id: Mapped[int] = mapped_column(index=True)
    
    endereco_nomeado: Mapped[str] = mapped_column(ForeignKey('endereco_usuario.endereco_nomeado'),index=True)
    carrinho_id: Mapped[int] = mapped_column(ForeignKey('carrinho.carrinho_id'),index=True)

    endereco = relationship('EnderecoUsuarioDB',back_populates='confirmar_pagamento')
    carrinho = relationship('CarrinhoUsuarioDB',back_populates='confirmar_pagamento')

Base.metadata.create_all(bind=engine)

# Criacao do body model
class BODYUsuario(BaseModel):
    nome_usuario: str
    cpf: str

class BODYProdutosLoja(BaseModel):
    nome_produto: str
    preco_produto: float
    categoria_produto: str

class BODYCarrinhoUsuario(BaseModel):
    carrinho_usuario_id: int
    carrinho_id: int
    produto_id: int

class BODYCriarCarrinho(BaseModel):
    carrinho_id: int
    usuario_id: int

class BODYEnderecoUsuario(BaseModel):
    usuario_id: int
    bairro: str
    numero: Optional[int] = None
    cidade: str
    estado: str
    endereco_nomeado: str
    cep: str
    complemento: Optional[str] = None

class BODYCartao(BaseModel):
    nome_cartao: str
    usuario_id: int
    cartao_credito: Optional[str] = None
    cartao_debito: Optional[str] = None
    data_validade_cartao: str
    nome_do_usuario_do_cartao: str
    cvc: str

class BODYConfirmarPagamento(BaseModel):
    usuario_id: int
    endereco_nomeado: str
    carrinho_id: int
    nome_cartao: str

# Basemodel PUT
class BODYCartaoPUT(BaseModel):
    usuario_id: int
    nome_cartao: Optional[str] = None
    cartao_credito: Optional[str] = None
    cartao_debito: Optional[str] = None
    data_validade_cartao: Optional[str] = None
    nome_do_usuario_do_cartao: Optional[str] = None
    cvc: Optional[str] = None

class BODYEnderecoUsuarioPUT(BaseModel):
    usuario_id: int
    endereco_nomeado: Optional[str] = None
    bairro: Optional[str] = None
    numero: Optional[int] = None
    cidade: Optional[str] = None
    estado: Optional[str] = None
    cep: Optional[str] = None
    complemento: Optional[str] = None

class BODYProdutosLojaPUT(BaseModel):
    nome_produto: Optional[str] = None
    preco_produto: Optional[float] = None
    categoria_produto: Optional[str] = None

def sessao_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
    
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
            'cpf': valor.cpf
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
@app.get('/site/carrinho/{usuario_id}')
async def mostrar_carrinho(usuario_id: int,carrinho_id: int = None,db: Session = Depends(sessao_db)):
    # Verifica se o usuario_id existe
    usuario = db.query(UsuarioDB).filter(UsuarioDB.usuario_id==usuario_id).first()
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
    carrinho_usuario = carrinho.filter(CarrinhoUsuarioDB.carrinho_usuario_id == usuario_id).all()
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
@app.get('/site/endereco/{usuario_id}')
async def mostrar_endereco(usuario_id: int,db: Session = Depends(sessao_db)):
    # Chave do redis que mostra o endereco
    key = f'endereco:{usuario_id}'
    # Verifica se o redis existe
    redis = redis_client2.get(key)
    # Retorna o redis caso exista
    if redis:
        return {'enderecos':json.loads(redis),'ttl':redis_client2.ttl(key)}
    
    # Verifica se o usuario tem algum endereco cadastrado existe
    endereco = db.query(EnderecoUsuarioDB).filter(EnderecoUsuarioDB.usuario_id == usuario_id).all()
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
            'estado': valor.estado
        })

    redis_client2.setex(f'endereco:{usuario_id}',300,json.dumps(dicionario_redis))

    return {'enderecos':dicionario_redis}

# ==============
# |    POST    |
# ==============

# Cria um usuario
@app.post('/site/usuario', response_model=BODYUsuario)
async def criar_usuario(body: BODYUsuario, db: Session = Depends(sessao_db)):

    dados = body.model_dump()
    
    # gera hash do cpf
    hash_cpf = hashlib.sha256(dados["cpf"].encode()).hexdigest()

    # Verifica duplicidade
    duplicidade = db.query(UsuarioDB).filter(UsuarioDB.hash_cpf == hash_cpf).first()
    if duplicidade:
        raise HTTPException(
            status_code=400,
            detail='CPF ja cadastrado'
        )

    # criptografa o cpf
    dados["cpf"] = criptografar(dados["cpf"])

    # Salva hash 
    dados["hash_cpf"] = hash_cpf

    usuario = UsuarioDB(**dados)

    db.add(usuario)
    db.commit()
    db.refresh(usuario)

    return usuario

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
async def adicionar_produto_carrinho(body: BODYCarrinhoUsuario, db: Session = Depends(sessao_db)):
    # Verifica se o carrinho existe
    existe_carrinho = db.query(CriarCarrinhoDB).filter(CriarCarrinhoDB.usuario_id == body.carrinho_usuario_id, CriarCarrinhoDB.carrinho_id == body.carrinho_id).first()
    if existe_carrinho is None:
        raise HTTPException(
            status_code=400,
            detail='Esse carrinho nao existe'
        )

    # Verifica se o usuario existe
    usuario = db.query(UsuarioDB).filter(UsuarioDB.usuario_id == body.carrinho_usuario_id).first()
    if usuario is None:
        raise HTTPException(
            status_code=404,
            detail='Esse usuario nao existe'
        )
    
    # Verifica se o produto existe
    produto = db.query(ProdutosLojaDB).filter(ProdutosLojaDB.produto_id == body.produto_id).first()
    if produto is None:
        raise HTTPException(
            status_code=404,
            detail='Esse produto nao existe'
        )
    
    # Adiciona o produto no carrinho
    carrinho = CarrinhoUsuarioDB(**body.model_dump())
    db.add(carrinho)
    db.commit()
    db.refresh(carrinho)

    return carrinho


# Cria um carrinho
@app.post('/site/criar/carrinho')
async def criar_carrinho(body: BODYCriarCarrinho,db: Session = Depends(sessao_db)):
    # Verifica se o carrinho ja existe
    carrinho = db.query(CriarCarrinhoDB).filter(CriarCarrinhoDB.usuario_id == body.usuario_id, CriarCarrinhoDB.carrinho_id == body.carrinho_id).first()
    if carrinho:
        raise HTTPException(
            status_code=400,
            detail='Esse carrinho ja existe'
        )
    
    # Verifica se o usuario existe
    usuario_db = db.query(UsuarioDB).filter(UsuarioDB.usuario_id == body.usuario_id).first()
    if usuario_db is None:
        raise HTTPException(
            status_code=404,
            detail='Esse usuario nao existe'
        )

    # Cria um carrinho
    criar_carrinho = CriarCarrinhoDB(**body.model_dump())
    db.add(criar_carrinho)
    db.commit()
    db.refresh(criar_carrinho)

    return criar_carrinho   

# Adiciona um endereco da casa do usuario
@app.post('/site/endereco')
async def criar_endereco(body:BODYEnderecoUsuario ,db: Session = Depends(sessao_db)):
    # Verifica se a quantidade de enderecos ultrapassou 3
    quantidade_enderecos = db.query(EnderecoUsuarioDB).filter(EnderecoUsuarioDB.usuario_id == body.usuario_id).count()
    if quantidade_enderecos >= 10:
        raise HTTPException(
            status_code=400,
            detail='Voce ja atingiu o limite de enderecos cadastrados'
        )
    
    # Verifica se o usuario existe
    usuario = db.query(UsuarioDB).filter(UsuarioDB.usuario_id == body.usuario_id).first()
    if usuario is None:
        raise HTTPException(
            status_code=404,
            detail='Esse usuario nao existe'
        )
    
    # Verifica se o endereco ja existe
    endereco = db.query(EnderecoUsuarioDB).filter(EnderecoUsuarioDB.usuario_id == body.usuario_id, EnderecoUsuarioDB.endereco_nomeado == body.endereco_nomeado).first()
    if endereco:
        raise HTTPException(
            status_code=400,
            detail='Esse endereco ja existe'
        )
    
    # Adiciona o endereco no banco de dados
    adicionar_endereco = EnderecoUsuarioDB(**body.model_dump())
    db.add(adicionar_endereco)
    db.commit()
    db.refresh(adicionar_endereco)

    # -------- Exclui todas as informacoes do redis no endereco --------
    
    # Verifica se tem algo adicionado no redis
    valor = redis_client2.get(f'endereco:{body.usuario_id}')
    if valor:
        redis_client2.delete(f'endereco:{body.usuario_id}')


    return adicionar_endereco

# Adiciona a forma de pagamento
@app.post('/site/pagamento',response_model=BODYCartao)
async def adicionar_forma_pagamento(body: BODYCartao,db: Session = Depends(sessao_db)):
    # Atribui um valor None para evitar o erro
    hash_cartao = None
    verificacao_hash_cartao = None

    # Verifica se o usuario existe
    usuario = db.query(UsuarioDB).filter(UsuarioDB.usuario_id == body.usuario_id).first()
    if usuario is None:
        raise HTTPException(
            status_code=404,
            detail='Esse usuario nao existe'
        )

    # Verifica se ja existe um cartao com esse nome
    nome_cartao = db.query(CartoesDB).filter(CartoesDB.nome_cartao == body.nome_cartao, CartoesDB.usuario_id == body.usuario_id).first()
    if nome_cartao:
        raise HTTPException(
            status_code=400,
            detail='Voce ja possui um cartao com esse nome'
        )

    # Verifica se o usuario colocou algo nos campos de cartoes de credito
    if body.cartao_credito is None and body.cartao_debito is None:
        raise HTTPException(
            status_code=400,
            detail='Voce deve colocar algum cartao de credito'
        )

    cartao = body.model_dump()

    # Gera hash
    if cartao["cartao_credito"] is not None:
        hash_cartao = hashlib.sha256(cartao["cartao_credito"].encode()).hexdigest()
    
    elif cartao["cartao_debito"] is not None:
        hash_cartao = hashlib.sha256(cartao["cartao_debito"].encode()).hexdigest()
    
    # Verifica se ha duplicidade
    verificacao_hash_cartao = db.query(CartoesDB).filter(CartoesDB.hash_cartao == hash_cartao).first()

    # Tratamento de erro caso o cartao ja exista
    if verificacao_hash_cartao:
        raise HTTPException(
            status_code=400,
            detail='Ocorreu um erro'
        )

    # criptografa o cartao de credito
    if cartao["cartao_credito"] is not None:
        cartao["cartao_credito"] = criptografar(cartao["cartao_credito"])
     
    # criptografa de debito
    if cartao["cartao_debito"] is not None:
        cartao["cartao_debito"] = criptografar(cartao["cartao_debito"])

    # Criptografa o cvc
    cartao['cvc'] = criptografar(cartao['cvc'])

    # Salva o hash
    cartao['hash_cartao'] = hash_cartao

    cartoes = CartoesDB(**cartao)

    db.add(cartoes)
    db.commit()
    db.refresh(cartoes)

    return cartoes

# Finaliza o pagamento
@app.post('/site/finalizar-compra')
async def finalizar_compra(body: BODYConfirmarPagamento, db: Session = Depends(sessao_db)):
    # Verifica se o usuario ja possui um endereco
    endereco = db.query(EnderecoUsuarioDB).filter(EnderecoUsuarioDB.usuario_id == body.usuario_id,  EnderecoUsuarioDB.endereco_nomeado == body.endereco_nomeado).first()
    # Tratamento de erro caso nao exista o endereco
    if endereco is None:
        raise HTTPException(
            status_code=404,
            detail='Voce nao possui esse endereco'
        )
    
    # Verifica se a forma de pagamento existe
    pagamento = db.query(CartoesDB).filter(CartoesDB.usuario_id == body.usuario_id,CartoesDB.nome_cartao == body.nome_cartao).first()
    if pagamento is None:
        raise HTTPException(
            status_code=404,
            detail='Adicione alguma forma de pagamento'
        )

    # Verifica se o carrinho existe
    carrinho = db.query(CarrinhoUsuarioDB).filter(CarrinhoUsuarioDB.carrinho_id == body.carrinho_id, CarrinhoUsuarioDB.carrinho_usuario_id == body.usuario_id).all()
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
    envio = ConfirmarPagamentoDB(**body.model_dump())
    
    db.add(envio)
    
    # Deleta o carrinho que o usuario escolheu
    db.query(CarrinhoUsuarioDB).filter(CarrinhoUsuarioDB.carrinho_usuario_id == body.usuario_id, CarrinhoUsuarioDB.carrinho_id == body.carrinho_id).delete()
   
    # Deleta o carrinho em criar carrinho 
    db.query(CriarCarrinhoDB).filter(CriarCarrinhoDB.usuario_id == body.usuario_id, CriarCarrinhoDB.carrinho_id == body.carrinho_id).delete()
    db.commit()
    db.refresh(envio)


    return {
        'message':'Envio realizado com sucesso.',
        'endereco': f'Endereco de envio: bairro:{envio.endereco.bairro},numero: {envio.endereco.numero},estado: {envio.endereco.estado},cidade: {envio.endereco.cidade},cep: {envio.endereco.cep}',
        'usuario': f'carrinho escolhido: {body.carrinho_id}',
        'Produtos enviados': produtos
        }
    

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
@app.delete('/site/endereco/{usuario_id}/{endereco_nomeado}')
async def deletar_endereco(usuario_id: int,endereco_nomeado: str, db: Session = Depends(sessao_db)):
    # Verifica se o usuario existe e o endereco existem
    verificacao = db.query(EnderecoUsuarioDB).filter(EnderecoUsuarioDB.usuario_id == usuario_id, EnderecoUsuarioDB.endereco_nomeado == endereco_nomeado).first()
    if verificacao is None:
        raise HTTPException(
            status_code=404,
            detail='Usuario ou endereco nao existem'
        )
    # Deleta o endereco
    db.delete(verificacao)
    db.commit()

    # Deleta o endereco no redis
    key = redis_client2.get(f'endereco:{usuario_id}')
    # Verifica se existe
    if key:
        # Trasforma em dicionario
        lista = json.loads(key)
        for i,v in enumerate(lista):
            if v['endereco_nomeado'] == endereco_nomeado:
                del lista[i]
        
        redis_client2.setex(f'endereco:{usuario_id}',300,lista)
    
    return verificacao

# Deletar carrinho
@app.delete('/site/carrinho/{usuario_id}/{carrinho_id}')
async def deletar_carrinho(usuario_id: int, carrinho_id: int, db: Session = Depends(sessao_db)):
    # Verifica se o usuario possui esse carrinho
    carrinho = db.query(CriarCarrinhoDB).filter(CriarCarrinhoDB.usuario_id == usuario_id, CriarCarrinhoDB.carrinho_id).first()
    if carrinho is None:
        raise HTTPException(
            status_code=404,
            detail='Esse usuario nao possui esse carrinho'
        )
    # Deleta o carrinho que esta no Banco de Dados CriarCarrinhoDB
    db.delete(carrinho)
    # Deleta o carrinho que esta em CarrinhoUsuarioDB
    carrinho_usuario = db.query(CarrinhoUsuarioDB).filter(CarrinhoUsuarioDB.carrinho_usuario_id == usuario_id, CarrinhoUsuarioDB.carrinho_id == carrinho_id).delete()
    db.commit()

    return {'message':f'Carrinho {carrinho_id} deletado com sucesso'}

# Deleta um cartao cadastrado
@app.delete('/site/cartoes/{usuario_id}/{nome_cartao}')
async def deletar_cartao(usuario_id: int, nome_cartao:str, db: Session = Depends(sessao_db)):
    # Verifica se o cartao existe
    cartao = db.query(CartoesDB).filter(CartoesDB.usuario_id == usuario_id, CartoesDB.nome_cartao == nome_cartao).first()
    if cartao is None:
        raise HTTPException(
            status_code=404,
            detail='Esse cartao nao existe'
        )
    db.delete(cartao)
    db.commit()

    return {'message':'Cartao excluido com sucesso'}

# Deleta um item de um carrinho
@app.delete('/site/carrinho-item/{usuario_id}/{produto_id}')
async def deletar_produto_carrinho(usuario_id: int, produto_id: int, db: Session = Depends(sessao_db)):
    # Verifica se o item existe no carrinho do usuario
    item_carrinho = db.query(CarrinhoUsuarioDB).filter(CarrinhoUsuarioDB.produto_id == produto_id, CarrinhoUsuarioDB.carrinho_usuario_id == usuario_id).first()
    if item_carrinho is None:
        raise HTTPException(
            status_code=404,
            detail='Esse item não existe'
        )
    db.delete(item_carrinho)
    db.commit()

    return {'message':f'Item deletado com sucesso'}
    

# ===========
# |   PUT   |
# ===========

# Altera o cartao ja cadastrado
@app.put('/site/cartao/{nome_cartao}')
async def alterar_cartao(nome_cartao:str,body: BODYCartaoPUT,db: Session = Depends(sessao_db)):
    # Verifica se o usuario possui algum cartao cadastrado
    usuario = db.query(CartoesDB).filter(CartoesDB.usuario_id == body.usuario_id,CartoesDB.nome_cartao == nome_cartao).first()
    if usuario is None:
        raise HTTPException(
            status_code=404,
            detail='Esse usuario nao possui nenhum cartao cadastrado'
        )
    
    # Verifica se o usuario colocou algo no body
    if body.cartao_credito is None and body.cartao_debito is None:
        raise HTTPException(
            status_code=400,
            detail='Voce deve colocar um numero do cartao de credito'
        )

    cartao = body.model_dump()

    # Verifica se no body o campo cartao_credito esta vazio
    if body.cartao_credito is not None:
        usuario.cartao_credito = criptografar(cartao["cartao_credito"])
    # Verifica se no body o campo cartao_debito esta vazio
    if body.cartao_debito is not None:
        usuario.cartao_debito = criptografar(cartao['cartao_debito'])
    # Verifica se no body o campo cvc esta vazio
    if body.cvc is not None:
        usuario.cvc = criptografar(cartao['cvc'])
    # Verifica se no body o campo data_validade_cartao esta vazio
    if body.data_validade_cartao is not None:
        usuario.data_validade_cartao = body.data_validade_cartao
    # Verifica se no body o campo nome_do_usuario_do_cartao esta vazio
    if body.nome_do_usuario_do_cartao is not None:
        usuario.nome_do_usuario_do_cartao = body.nome_do_usuario_do_cartao
    # Verifica se no body o campo nome_cartao esta vazio
    if body.nome_cartao is not None:
        usuario.nome_cartao = body.nome_cartao
    
    db.commit()
    db.refresh(usuario)

    return {
    "message": "Cartão atualizado com sucesso"
    }

# Altera o endereco do usuario
@app.put('/site/alterar-endereco/{usuario_id}/{endereco_nomeado}')
async def alterar_endereco(
    usuario_id: int, 
    endereco_nomeado: str, 
    body: BODYEnderecoUsuarioPUT, 
    db: Session = Depends(sessao_db)
    ):
    # Verifica se o usuario possui esse endereco
    endereco = db.query(EnderecoUsuarioDB).filter(
        EnderecoUsuarioDB.usuario_id == usuario_id,
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