from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional


# Faz login no site
class BODYUsuario(BaseModel):
    email: EmailStr
    senha_usuario: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

# Cadastra um usuario no site
class BODYCadastrarUsuario(BaseModel):
    nome_usuario: str
    email: EmailStr
    senha_usuario: str = Field(..., min_length=6)
    confirmar_senha: str = Field(..., min_length=6)

# Adiciona um produto na loja
class BODYProdutosLoja(BaseModel):
    nome_produto: str
    preco_produto: float
    categoria_produto: str
    quantidade_disponivel: int

# Adiciona um produto no carrinho
class BODYCarrinhoUsuario(BaseModel):
    produto_id: int

# Cadastra um endereco pro usuario
class BODYEnderecoUsuario(BaseModel):
    bairro: str
    numero: Optional[int] = None
    cidade: str
    estado: str
    endereco_nomeado: str
    cep: str
    complemento: Optional[str] = None

# Esse continua sendo o de ENTRADA (com cvc e número completo)
class BODYCartao(BaseModel):
    nome_cartao: str
    cartao_credito: Optional[str] = None
    cartao_debito: Optional[str] = None
    data_validade_cartao: str
    cvc: str  # Enviado apenas na entrada
    nome_do_usuario_do_cartao: str

# 🆕 ESSE SERÁ O DE SAÍDA (Sem cvc e expondo apenas dados seguros)
class BODYCartaoSalvoResponse(BaseModel):
    id: int
    nome_cartao: str
    nome_do_usuario_do_cartao: str
    data_validade_cartao: str
    ultimos_4: str  # Mostra apenas o final do cartão para segurança
    token_stripe: Optional[str]

    class Config:
        from_attributes = True  # Permite que o Pydantic leia o objeto do SQLAlchemy (CartoesDB)

# Confirmar o pagamento
class BODYConfirmarPagamento(BaseModel):
    endereco_nomeado: str
    nome_cartao: str

# BODY Para escolher o nome do endereco
class BODYNomeEndereco(BaseModel):
    endereco_nomeado: str

# BODY para resetar a senha
class BODYResetSenhaRequest(BaseModel):
    nova_senha: str = Field(..., min_length=6)
    confirmar_senha: str = Field(..., min_length=6)
    token: str

# Body pra enviar o email para o usuario para que ele possa excluir a conta
class BODYEnviarEmailParaExcluirConta(BaseModel):
    email: EmailStr
    senha: Optional[str] = None

# Body que envia o token necessario para excluir (logicamente) a conta do usuario
class BODYExcluirConta(BaseModel):
    token: str

# Basemodel PUT
class BODYCartaoPUT(BaseModel):
    nome_cartao: Optional[str] = None
    cartao_credito: Optional[str] = None
    cartao_debito: Optional[str] = None
    data_validade_cartao: Optional[str] = None
    nome_do_usuario_do_cartao: Optional[str] = None

# Body que altera a o endereco do usuario
class BODYEnderecoUsuarioPUT(BaseModel):
    usuario_id: int
    endereco_nomeado: Optional[str] = None
    bairro: Optional[str] = None
    numero: Optional[int] = None
    cidade: Optional[str] = None
    estado: Optional[str] = None
    cep: Optional[str] = None
    complemento: Optional[str] = None

# Altera as configuracoes do protudo na loja
class BODYProdutosLojaPUT(BaseModel):
    nome_produto: Optional[str] = None
    preco_produto: Optional[float] = None
    categoria_produto: Optional[str] = None
    quantidade_disponivel: Optional[int] = None

# Body que envia o email para recuperar a senha
class BODYRecuperarSenha(BaseModel):
    email: EmailStr

# Body que envia as informacoes de pagamento para o front end
class BODYItemCompra(BaseModel):
    token_cartao: str  
    valor_em_centavos: int  # R$ 10,00 reais = 1000 centavos
    descricao: str
