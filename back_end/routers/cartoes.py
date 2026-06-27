import hashlib
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from banco_dados import sessao_db, CartoesDB, UsuarioDB
from auth_token import verificar_token_access
from body_models import BODYCartao, BODYCartaoPUT, BODYCartaoSalvoResponse
from routers.dependencias import criptografar
import stripe
import os
from dotenv import load_dotenv

load_dotenv()

# Pega a stripe_secret_key no .env
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

router = APIRouter(tags=['Cartões de credito'])

# Adiciona a forma de pagamento
@router.post('/site/pagamento', response_model=BODYCartaoSalvoResponse)
async def adicionar_forma_pagamento(body: BODYCartao, db: Session = Depends(sessao_db), usuario_token: UsuarioDB = Depends(verificar_token_access)):
    # 1. Verifica nome duplicado
    if db.query(CartoesDB).filter(
        CartoesDB.nome_cartao == body.nome_cartao,
        CartoesDB.usuario_id == usuario_token.usuario_id
    ).first():
        raise HTTPException(400, 'Você já possui um cartão com esse nome')

    # 2. Deve ter pelo menos um tipo de cartão
    if not (body.cartao_credito or body.cartao_debito):
        raise HTTPException(400, 'Você deve informar um cartão')

    # Verifica se o usuario inserio valores em cartao_debito e carta_credito
    if body.cartao_credito and body.cartao_debito:
        raise HTTPException(400,'Você deve informar apenas um cartão!')

    # 3. Número do cartão (crédito ou débito)
    numero = body.cartao_credito or body.cartao_debito
    numero_limpo = numero.replace(" ", "")

    # 4. Validação simples: apenas dígitos e tamanho 13-19
    if not numero_limpo.isdigit() or not 13 <= len(numero_limpo) <= 19:
        raise HTTPException(400, 'Número do cartão inválido')

    # 5. Gera hash para checar duplicidade
    hash_cartao = hashlib.sha256(numero_limpo.encode()).hexdigest()

    if db.query(CartoesDB).filter(
        CartoesDB.hash_cartao == hash_cartao,
        CartoesDB.usuario_id == usuario_token.usuario_id
    ).first():
        raise HTTPException(400, 'Não foi possível processar o cadastro do cartão (Cartão já cadastrado)')

    # --- 🛡️ VALIDAÇÃO REAL COM O STRIPE ---
    token_id_criado = None
    try:
        # Tratamento caso a data venha com espaços (ex: " 12 / 2029 ")
        mes, ano = body.data_validade_cartao.split("/")

        # ===============================
        # |       💡 MOCK TESTE 💡      |
        # ===============================

        # Verifica se o cvc é numerico
        if not body.cvc.isnumeric() and len(body.cvc) != 3:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail='O CVC precisa ser um número!'
                )

        # v 💡 MOCK PARA TESTE LOCAL (Ignora a trava de segurança do painel) v
        if numero_limpo == "4242424242424242":
            token_id_criado = "tok_visa"
        # ^ 💡 MOCK PARA TESTE LOCAL (Ignora a trava de segurança do painel) ^
        else:
            # Para QUALQUER outro número, ele tenta chamar a Stripe real (e vai dar erro)
            token_stripe = stripe.Token.create(
                card={
                    "number": numero_limpo,
                    "exp_month": int(mes.strip()),
                    "exp_year": int(ano.strip()),
                    "cvc": body.cvc,
                    "name": body.nome_do_usuario_do_cartao
                },
            )
            token_id_criado = token_stripe.id

    except stripe.error.CardError as e:
        # Caso a Stripe real rejeite ou nosso simulador intercepte
        err = e.error if hasattr(e, 'error') else e
        detail_msg = err.message if hasattr(err, 'message') else str(e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cartão recusado pela operadora: {detail_msg}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro de comunicação com a operadora do cartão."
        )
    # --- --------------------------------- ---

    # Criptografa números (Opcional, já que agora você tem o Token do Stripe)
    cartao_credito = criptografar(numero_limpo) if body.cartao_credito else None
    cartao_debito = criptografar(numero_limpo) if body.cartao_debito else None

    # Salva no Banco de Dados
    novo_cartao = CartoesDB(
        usuario_id=usuario_token.usuario_id,
        nome_cartao=body.nome_cartao,
        hash_cartao=hash_cartao,
        cartao_credito=cartao_credito,
        cartao_debito=cartao_debito,
        nome_do_usuario_do_cartao=body.nome_do_usuario_do_cartao,
        data_validade_cartao=body.data_validade_cartao,
        ultimos_4=numero_limpo[-4:],
        token_stripe=token_id_criado # 👈 ADICIONE ESSA COLUNA NA SUA TABELA!
    )

    db.add(novo_cartao)
    db.commit()
    db.refresh(novo_cartao)

    return novo_cartao

# Deleta um cartao cadastrado
@router.delete('/site/cartoes/{nome_cartao}')
async def deletar_cartao(nome_cartao: str, db: Session = Depends(sessao_db), usuario_token: UsuarioDB = Depends(verificar_token_access)):
    # Verifica se o cartao existe
    cartao = db.query(CartoesDB).filter(CartoesDB.usuario_id == usuario_token.usuario_id, CartoesDB.nome_cartao == nome_cartao).first()
    if cartao is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
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
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Cartão não encontrado'
        )

    # ❗ Deve enviar pelo menos um número
    if body.cartao_credito is None and body.cartao_debito is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Dados inválidos'
        )

    # ❗ Não pode enviar os dois
    if body.cartao_credito and body.cartao_debito:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
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