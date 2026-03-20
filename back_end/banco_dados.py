import os
import redis
from sqlalchemy.orm import sessionmaker, declarative_base, Mapped, mapped_column, relationship, Session
from sqlalchemy import create_engine, ForeignKey, String
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")

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

    usuario_id: Mapped[int] = mapped_column(primary_key=True, index=True)

    nome_usuario: Mapped[str] = mapped_column(index=True)
    email: Mapped[str] = mapped_column(unique=True, index=True)
    google_id: Mapped[str] = mapped_column(unique=True, index=True, nullable=True)
    senha_usuario: Mapped[str] = mapped_column(nullable=True)

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

    # Carrinho_id proviniente da tabela que CriarCarrinhoDB
    carrinho_id: Mapped[int] = mapped_column(ForeignKey('criar_carrinho.carrinho_id',ondelete="CASCADE"),index=True)
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
    cartao_credito: Mapped[str] = mapped_column(index=True, nullable=True)
    cartao_debito: Mapped[str] = mapped_column(index=True, nullable=True)
    nome_do_usuario_do_cartao: Mapped[str] = mapped_column(index=True)
    data_validade_cartao: Mapped[str] = mapped_column(index=True)
    ultimos_4: Mapped[str] = mapped_column(String(4))

# Tabela que confirma o pagemnto
class ConfirmarPagamentoDB(Base):
    __tablename__ = 'confirmar_pagamento'
    id: Mapped[int] = mapped_column(index=True,primary_key=True)
    usuario_id: Mapped[int] = mapped_column(index=True)
    
    endereco_nomeado: Mapped[str] = mapped_column(ForeignKey('endereco_usuario.endereco_nomeado'),index=True)
    carrinho_id: Mapped[int] = mapped_column(ForeignKey('carrinho.carrinho_id'),index=True)
    nome_cartao: Mapped[str] = mapped_column(ForeignKey('cartoes.nome_cartao'))

    endereco = relationship('EnderecoUsuarioDB',back_populates='confirmar_pagamento')
    carrinho = relationship('CarrinhoUsuarioDB',back_populates='confirmar_pagamento')

Base.metadata.create_all(bind=engine)

def sessao_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
