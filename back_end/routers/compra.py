import hashlib
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from banco_dados import sessao_db, EnderecoUsuarioDB, CartoesDB, CarrinhoUsuarioDB, ConfirmarPagamentoDB, CriarCarrinhoDB, UsuarioDB
from auth_token import verificar_token_access
from body_models import BODYCartao, BODYConfirmarPagamento, BODYCartaoPUT
from routers.dependencias import criptografar

router = APIRouter()

# Adiciona a forma de pagamento
@router.post('/site/pagamento', response_model=BODYCartao)
async def adicionar_forma_pagamento(body: BODYCartao, db: Session = Depends(sessao_db), usuario_token: UsuarioDB = Depends(verificar_token_access)):
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
@router.post('/site/finalizar-compra')
async def finalizar_compra(body: BODYConfirmarPagamento, db: Session = Depends(sessao_db), usuario_token: UsuarioDB = Depends(verificar_token_access)):
    # Verifica se o usuario ja possui um endereco
    endereco = db.query(EnderecoUsuarioDB).filter(EnderecoUsuarioDB.usuario_id == usuario_token.usuario_id, EnderecoUsuarioDB.endereco_nomeado == body.endereco_nomeado).first()
    # Tratamento de erro caso nao exista o endereco
    if endereco is None:
        raise HTTPException(
            status_code=404,
            detail='Voce nao possui esse endereco'
        )
    
    # Verifica se a forma de pagamento existe
    pagamento = db.query(CartoesDB).filter(CartoesDB.usuario_id == usuario_token.usuario_id, CartoesDB.nome_cartao == body.nome_cartao).first()
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
    envio = ConfirmarPagamentoDB(**body.model_dump(), usuario_id=usuario_token.usuario_id)
    
    db.add(envio)
    
    # Deleta o carrinho que o usuario escolheu
    db.query(CarrinhoUsuarioDB).filter(CarrinhoUsuarioDB.carrinho_usuario_id == usuario_token.usuario_id, CarrinhoUsuarioDB.carrinho_id == body.carrinho_id).delete()
   
    # Deleta o carrinho em criar carrinho 
    db.query(CriarCarrinhoDB).filter(CriarCarrinhoDB.usuario_id == usuario_token.usuario_id, CriarCarrinhoDB.carrinho_id == body.carrinho_id).delete()
    db.commit()
    db.refresh(envio)

    return {
        'message': 'Envio realizado com sucesso.',
        'endereco': f'Endereço de envio: bairro:{envio.endereco.bairro},número: {envio.endereco.numero},estado: {envio.endereco.estado},cidade: {envio.endereco.cidade},cep: {envio.endereco.cep}',
        'usuario': f'carrinho escolhido: {body.carrinho_id}',
        'Produtos enviados': produtos
    }

# Deleta um cartao cadastrado
@router.delete('/site/cartoes/{nome_cartao}')
async def deletar_cartao(nome_cartao: str, db: Session = Depends(sessao_db), usuario_token: UsuarioDB = Depends(verificar_token_access)):
    # Verifica se o cartao existe
    cartao = db.query(CartoesDB).filter(CartoesDB.usuario_id == usuario_token.usuario_id, CartoesDB.nome_cartao == nome_cartao).first()
    if cartao is None:
        raise HTTPException(
            status_code=404,
            detail='Esse cartao nao existe'
        )
    db.delete(cartao)
    db.commit()

    return {'message': 'Cartao excluido com sucesso'}

# Altera o cartao ja cadastrado
@router.put('/site/cartao/{nome_cartao}')
async def alterar_cartao(nome_cartao: str, body: BODYCartaoPUT, db: Session = Depends(sessao_db), usuario_token: UsuarioDB = Depends(verificar_token_access)):
    
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
