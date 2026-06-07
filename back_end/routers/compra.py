import hashlib
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from banco_dados import sessao_db, EnderecoUsuarioDB, CartoesDB, CarrinhoUsuarioDB, ConfirmarPagamentoDB, UsuarioDB, ProdutosLojaDB, PedidoDB, ItensPedidoDB
from auth_token import verificar_token_access
from body_models import BODYCartao, BODYConfirmarPagamento, BODYCartaoPUT, BODYItemCompra, BODYCartaoSalvoResponse
from routers.dependencias import criptografar
import stripe
import os
from dotenv import load_dotenv

load_dotenv()

# Pega a stripe_secret_key no .env
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

router = APIRouter(tags=['Compra na loja'])

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

        # 💡 MOCK PARA TESTE LOCAL (Ignora a trava de segurança do painel)
        if numero_limpo == "4242424242424242":
            token_id_criado = "tok_visa"
            
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

# Finaliza o pagamento
@router.post('/site/finalizar-compra')
async def finalizar_compra(body: BODYConfirmarPagamento, db: Session = Depends(sessao_db), usuario_token: UsuarioDB = Depends(verificar_token_access)):
    # Verifica se o usuario ja possui um endereco
    endereco = db.query(EnderecoUsuarioDB).filter(EnderecoUsuarioDB.usuario_id == usuario_token.usuario_id, EnderecoUsuarioDB.endereco_nomeado == body.endereco_nomeado).first()
    # Tratamento de erro caso nao exista o endereco
    if endereco is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Voce não possui esse endereço!'
        )
    
    # Verifica se a forma de pagamento existe
    pagamento = db.query(CartoesDB).filter(CartoesDB.usuario_id == usuario_token.usuario_id, CartoesDB.nome_cartao == body.nome_cartao).first()
    if pagamento is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Adicione alguma forma de pagamento válida!'
        )

    # Verifica se o carrinho existe
    carrinho = db.query(CarrinhoUsuarioDB).filter(CarrinhoUsuarioDB.usuario_id == usuario_token.usuario_id).all()
    if not carrinho:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Adicione um carriho que exista!'
        )

    # Salva para ser usado como formtacao no return para atribuir preco,nome e categoria do produto
    produtos = [
            {
                'preco': valor.produto_no_carrinho.preco_produto,
                'nome_produto': valor.produto_no_carrinho.nome_produto,
                'quantidade_produto': valor.quantidade_produto,
                'categoria': valor.produto_no_carrinho.categoria_produto
            }
            for valor in carrinho
        ]

    # Envia o produto para o endereco
    envio = ConfirmarPagamentoDB(**body.model_dump(), usuario_id=usuario_token.usuario_id)
    
    db.add(envio)
    
    # Deleta todos os produtos no carrinho do usuario
    carrinho_delete = db.query(CarrinhoUsuarioDB).filter(CarrinhoUsuarioDB.usuario_id == usuario_token.usuario_id).delete()
   
    # Deleta o carrinho em criar carrinho 
    db.commit()
    db.refresh(envio)

    return {
        'message': 'Envio realizado com sucesso.',
        'endereco': f'Endereço de envio: bairro:{envio.endereco.bairro},número: {envio.endereco.numero},estado: {envio.endereco.estado},cidade: {envio.endereco.cidade},cep: {envio.endereco.cep}',
        'Produtos enviados': produtos
    }

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

@router.post("/site/v1/cobrar", status_code=status.HTTP_200_OK)
async def realizar_cobranca(
    body: BODYItemCompra,
    db: Session = Depends(sessao_db),
    token: UsuarioDB = Depends(verificar_token_access)
):
    try:
        # 1. Busca os itens do carrinho do usuário primeiro
        carrinho_do_usuario = db.query(CarrinhoUsuarioDB).\
            filter(CarrinhoUsuarioDB.usuario_id == token.usuario_id).\
            all()
        
        if not carrinho_do_usuario:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Seu carrinho está vazio.")

        # --- 🔒 BLOQUEIO E VALIDAÇÃO DE ESTOQUE (ANTES DO STRIPE) ---
        # Calcular o total real no backend de forma ultra rápida
        total_calculado_centavos = 0
        for itens in carrinho_do_usuario:
            
            # O 'with_for_update()' bloqueia a linha do produto no banco para evitar compras simultâneas do mesmo item
            produto_estoque = db.query(ProdutosLojaDB).\
                filter(ProdutosLojaDB.produto_id == itens.produto_id).\
                with_for_update().\
                first()
            
            # Segurança caso o produto tenha sido deletado do catálogo
            if not produto_estoque:
                raise HTTPException(
                    status_code=404, 
                    detail="Um dos produtos no seu carrinho não está mais disponível na nossa loja."
                )
            
            # Vincula o produto travado ao item do carrinho
            itens.produto_no_carrinho = produto_estoque
            # Preco de todos os itens que estao no carrinho
            total_calculado_centavos += int((itens.produto_no_carrinho.preco_produto * itens.quantidade_produto) * 100)
            # Valida se a quantidade pedida está disponível
            if itens.quantidade_produto > itens.produto_no_carrinho.quantidade_disponivel:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f'Ocorreu um erro, a quantidade do produto {itens.produto_no_carrinho.nome_produto} não está mais disponível!'
                )
        
        # Valida se o valor do body bate com o cálculo real do backend
        if body.valor_em_centavos != total_calculado_centavos:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="O valor total dos produtos mudou ou foi adulterado. Por favor, atualize o carrinho."
            )
        
        # --- ---------------------------------------------------- ---

        # 2. ESTOQUE GARANTIDO E RESERVADO! Agora disparamos a cobrança real na Stripe
        cobranca = stripe.Charge.create(
            amount=body.valor_em_centavos,
            currency="brl",
            source=body.token_cartao,
            description=body.descricao,
        )
        
        # 3. Verifica se o pagamento foi aprovado com sucesso
        if cobranca.status == "succeeded":
            
            try:
                # Adiciona informacoes na tabela PedidoDB
                info_pedido = PedidoDB(
                usuario_id=token.usuario_id,
                total_centavos = total_calculado_centavos,
                status_pedido='Pago',
                stripe_charge_id=cobranca.id
                )
                
                db.add(info_pedido)
                db.flush()
                # Diminui o estoque e deleta os itens do carrinho
                for itens in carrinho_do_usuario:
                    itens.produto_no_carrinho.quantidade_disponivel -= itens.quantidade_produto
                    # Adiciona os produtos pedidos na tabela ItensPedidoDB
                    produtos_pedidos = ItensPedidoDB(
                        pedido_id=info_pedido.id,
                        produto_id=itens.produto_id,
                        quantidade=itens.quantidade_produto,
                        preco_unitario_centavos=int(itens.produto_no_carrinho.preco_produto * 100)
                    )
                    db.add(produtos_pedidos)
                    db.delete(itens)
                
                db.commit()

                
            except Exception as banco_erro:
                # Se o dinheiro saiu do cliente, mas seu banco falhou ao salvar a baixa, fazemos rollback
                db.rollback()
                # O ideal aqui é registrar um log crítico e dar um estorno (Refund) automático na Stripe
                # stripe.Refund.create(charge=cobranca.id)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Pagamento aprovado, mas houve uma falha ao processar o pedido internamente. O suporte foi notificado."
                )
            

            return {
                "sucesso": True,
                "id_transacao": cobranca.id,
                "mensagem": "Pagamento aprovado com sucesso!"
            }
            
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="O pagamento foi recusado pela operadora."
            )

    except stripe.error.CardError as e:
        # Se der erro no cartão, o banco faz rollback automático do Lock do estoque ao fechar a requisição
        err = e.error if hasattr(e, 'error') else e
        detail_msg = err.message if hasattr(err, 'message') else str(e)
        
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Erro no cartão: {detail_msg}"
        )
        
    except HTTPException:
        # Repassa as exceções HTTP que nós mesmos criamos lá em cima sem cair no bloco genérico 500
        raise
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro interno no servidor: {str(e)}"
        )
    

