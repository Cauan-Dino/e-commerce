from pydantic import BaseModel, EmailStr, Field
from typing import Optional

# Criacao do body model
class BODYUsuario(BaseModel):
    email: EmailStr
    senha_usuario: Optional[str] = None
    
    class Config:
        from_attributes = True

class BODYCadastrarUsuario(BaseModel):
    nome_usuario: str
    email: EmailStr
    senha_usuario: str = Field(..., min_length=6)
    confirmar_senha: str = Field(..., min_length=6)

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

class BODYConfirmarPagamento(BaseModel):
    usuario_id: int
    endereco_nomeado: str
    carrinho_id: int
    nome_cartao: str

# BODY para resetar a senha
class BODYResetSenhaRequest(BaseModel):
    token: str
    nova_senha: str = Field(..., min_length=6)
    confirmar_senha: str = Field(..., min_length=6)

# Basemodel PUT
class BODYCartaoPUT(BaseModel):
    usuario_id: int
    nome_cartao: Optional[str] = None
    cartao_credito: Optional[str] = None
    cartao_debito: Optional[str] = None
    data_validade_cartao: Optional[str] = None
    nome_do_usuario_do_cartao: Optional[str] = None

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

# BODYMODEL para recuperar a senha
class BODYRecuperarSenha(BaseModel):
    email: EmailStr

