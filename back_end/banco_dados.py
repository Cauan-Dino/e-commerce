import os
from sqlalchemy.orm import sessionmaker, declarative_base, Mapped, mapped_column, relationship, Session
from sqlalchemy import create_engine, ForeignKey, String,DateTime
from datetime import datetime,timezone
from typing import List
from dotenv import load_dotenv

load_dotenv(dotenv_path="env_test.env")

# Criacao do banco de dados
engine = create_engine(os.getenv('DATABASE_URL'),connect_args={'check_same_thread': False})
SessionLocal = sessionmaker(autoflush=False,autocommit=False,bind=engine)
Base = declarative_base()

# --------------- Criacao das tabelas do banco de dados -------------------

# Tabela Usuario
class UsuarioDB(Base):
    __tablename__ = 'usuario'

    usuario_id: Mapped[int] = mapped_column(primary_key=True, index=True)

    nome_usuario: Mapped[str] = mapped_column(String(100),index=True)
    email: Mapped[str] = mapped_column(String(150),unique=True, index=True)
    google_id: Mapped[str] = mapped_column(unique=True, index=True, nullable=True)
    senha_usuario: Mapped[str] = mapped_column(nullable=True)
    usuario_ativo: Mapped[bool] = mapped_column(nullable=True,default=True)

    carrinho = relationship('CarrinhoUsuarioDB', back_populates='usuario')



# Tabela produtos cadastrados na loja
class ProdutosLojaDB(Base):
    __tablename__ = 'produtos_loja'
    produto_id: Mapped[int] = mapped_column(primary_key=True,index=True)
    nome_produto: Mapped[str] = mapped_column(String(200),index=True)
    preco_produto: Mapped[float] = mapped_column(index=True)
    quantidade_disponivel: Mapped[int] = mapped_column()
    categoria_produto: Mapped[str] = mapped_column(String(100),index=True)
    url_foto_produto: Mapped[str] = mapped_column()

    carrinho: Mapped["CarrinhoUsuarioDB"] = relationship('CarrinhoUsuarioDB',back_populates='produto_no_carrinho')



# Tabela que permite adicionar itens no carrinho do usuario
class CarrinhoUsuarioDB(Base):
    __tablename__ = 'carrinho'
    id: Mapped[int] = mapped_column(index=True,primary_key=True)

    usuario_id: Mapped[int] = mapped_column(ForeignKey('usuario.usuario_id'),index=True)
    produto_id: Mapped[int] = mapped_column(ForeignKey('produtos_loja.produto_id'),index=True)
    quantidade_produto: Mapped[int] = mapped_column(index=True)

    usuario = relationship('UsuarioDB', back_populates='carrinho')
    produto_no_carrinho: Mapped["ProdutosLojaDB"] = relationship('ProdutosLojaDB',back_populates='carrinho')
    confirmar_pagamento = relationship('ConfirmarPagamentoDB',back_populates='carrinho')



# Tabela do endereco do usuario
class EnderecoUsuarioDB(Base):
    __tablename__ = 'endereco_usuario'
    id: Mapped[int] = mapped_column(primary_key=True,index=True)

    usuario_id: Mapped[int] = mapped_column(ForeignKey('usuario.usuario_id'),index=True)
    
    endereco_nomeado: Mapped[str] = mapped_column(String(100),index=True)
    rua: Mapped[str] = mapped_column(String(100),index=True)
    bairro: Mapped[str] = mapped_column(String(100),index=True)
    numero: Mapped[int] = mapped_column(nullable=True)
    cidade: Mapped[str] = mapped_column(String(100),index=True)
    estado: Mapped[str] = mapped_column(String(100),index=True)
    cep: Mapped[str] = mapped_column(String(8),index=True)
    complemento: Mapped[str] = mapped_column(String(150),index=True,nullable=True)

    confirmar_pagamento = relationship('ConfirmarPagamentoDB',back_populates='endereco')



# Tabela que cadastra os cartoes de credito
class CartoesDB(Base):
    __tablename__ = 'cartoes'
    id: Mapped[int] = mapped_column(index=True,primary_key=True)
    
    usuario_id: Mapped[int] = mapped_column(index=True)
    nome_cartao: Mapped[str] = mapped_column(String(100),index=True)
    hash_cartao: Mapped[str] = mapped_column(String(64),index=True)  
    cartao_credito: Mapped[str] = mapped_column(String(255),nullable=True)
    cartao_debito: Mapped[str] = mapped_column(String(255),nullable=True)
    nome_do_usuario_do_cartao: Mapped[str] = mapped_column(String(100),index=True)
    data_validade_cartao: Mapped[str] = mapped_column(String(7),index=True)
    ultimos_4: Mapped[str] = mapped_column(String(4))
    token_stripe: Mapped[str] = mapped_column(index=True, nullable=True)



# Tabela que confirma o pagemnto
class ConfirmarPagamentoDB(Base):
    __tablename__ = 'confirmar_pagamento'
    id: Mapped[int] = mapped_column(index=True,primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey('carrinho.usuario_id'),index=True)
    
    endereco_nomeado: Mapped[str] = mapped_column(String(100),ForeignKey('endereco_usuario.endereco_nomeado'),index=True)
    nome_cartao: Mapped[str] = mapped_column(String(50),ForeignKey('cartoes.nome_cartao'))

    endereco = relationship('EnderecoUsuarioDB',back_populates='confirmar_pagamento')
    carrinho = relationship('CarrinhoUsuarioDB',back_populates='confirmar_pagamento')

    

# Armazena as informacoes sobre tudo que o usuario pediu no carrinho
class PedidoDB(Base):
    __tablename__ = 'pedidos'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(index=True) # Quem comprou
    
    # Informações Financeiras
    total_centavos: Mapped[int] = mapped_column() # Valor total do pedido
    status_pedido: Mapped[str] = mapped_column(String(50), default="Pendente") # Pago, Recusado, Enviado
    
    # Integração com a Stripe
    stripe_charge_id: Mapped[str] = mapped_column(String(100), index=True, nullable=True)
    
    # Auditoria
    data_criacao: Mapped[datetime] = mapped_column(DateTime, default=datetime.now(timezone.utc))

    # Relacionamento: Um pedido pode ter vários itens
    itens: Mapped[List["ItensPedidoDB"]] = relationship("ItensPedidoDB", back_populates="pedido", cascade="all, delete-orphan")



# Armazena cada produto que o usuario pediu
class ItensPedidoDB(Base):
    __tablename__ = 'itens_pedido'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    pedido_id: Mapped[int] = mapped_column(ForeignKey('pedidos.id', ondelete="CASCADE"))
    produto_id: Mapped[int] = mapped_column(index=True) # O ID do produto vendido
    
    # Dados do produto no momento exato da compra
    quantidade: Mapped[int] = mapped_column()
    preco_unitario_centavos: Mapped[int] = mapped_column() # 👈 Crucial para o histórico financeiro

    # Relacionamento de volta para o Pedido
    pedido: Mapped["PedidoDB"] = relationship("PedidoDB", back_populates="itens")

Base.metadata.create_all(bind=engine)

def sessao_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
