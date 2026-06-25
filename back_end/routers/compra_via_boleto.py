from fastapi import APIRouter, Depends, HTTPException,status,Request,Header
from body_models import BODYCompraViaBoleto
import stripe
from validate_docbr import CPF
import os
from dotenv import load_dotenv
from auth_token import verificar_token_access
from banco_dados import UsuarioDB, sessao_db,Session,EnderecoUsuarioDB,CarrinhoUsuarioDB,ProdutosLojaDB,PedidoDB,ItensPedidoDB

load_dotenv()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
ENDPOINT_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')

router = APIRouter(
    tags=['Compra Via Boleto']
)

# Gera o boleto
@router.post("/site/v1/cobrar-boleto", status_code=status.HTTP_200_OK)
async def realizar_cobranca_boleto(
    body: BODYCompraViaBoleto,
    db: Session = Depends(sessao_db),
    token: UsuarioDB = Depends(verificar_token_access)
):  
    # 1. Verifica se o usuário possui o endereço selecionado
    endereco = db.query(EnderecoUsuarioDB).filter(
        EnderecoUsuarioDB.usuario_id == token.usuario_id, 
        EnderecoUsuarioDB.endereco_nomeado == body.endereco_nomeado
    ).first()
    
    if endereco is None:
        raise HTTPException(status_code=404, detail='Você não possui esse endereço!')

    # 2. Limpa e valida o CPF matematicamente antes de gastar processamento com banco/Stripe
    cpf_limpo = "".join(filter(str.isdigit, body.cpf))
    validador_cpf = CPF()
    if not validador_cpf.validate(cpf_limpo):
        raise HTTPException(status_code=400, detail="O CPF informado é inválido.")

    try:
        # 3. Busca os itens do carrinho
        carrinho_do_usuario = db.query(CarrinhoUsuarioDB).filter(
            CarrinhoUsuarioDB.usuario_id == token.usuario_id
        ).all()
        
        if not carrinho_do_usuario:
            raise HTTPException(status_code=400, detail="Seu carrinho está vazio.")

        # --- 🔒 BLOQUEIO E VALIDAÇÃO DE ESTOQUE ---
        total_calculado_centavos = 0
        for itens in carrinho_do_usuario:
            produto_estoque = db.query(ProdutosLojaDB).filter(
                ProdutosLojaDB.produto_id == itens.produto_id
            ).with_for_update().first()
            
            if not produto_estoque:
                raise HTTPException(status_code=404, detail="Um dos produtos sumiu do catálogo.")
            
            itens.produto_no_carrinho = produto_estoque
            total_calculado_centavos += int((itens.produto_no_carrinho.preco_produto * itens.quantidade_produto) * 100)
            
            if itens.quantidade_produto > itens.produto_no_carrinho.quantidade_disponivel:
                raise HTTPException(
                    status_code=400,
                    detail=f'Estoque insuficiente para o produto {itens.produto_no_carrinho.nome_produto}!'
                )
        
        if body.valor_em_centavos != total_calculado_centavos:
            raise HTTPException(status_code=400, detail=f"O valor total divergiu do backend.")
        # --- ---------------------------------- ---

        # 4. Cria o Pedido no banco com status 'Aguardando Pagamento'
        novo_pedido = PedidoDB(
            usuario_id=token.usuario_id,
            total_centavos=total_calculado_centavos,
            status_pedido='Pendente' 
        )
        db.add(novo_pedido)
        db.flush() 

        # 5. Cria o PaymentIntent na Stripe configurado para BOLETO com expiração de 2 dias
        intent = stripe.PaymentIntent.create(
            amount=total_calculado_centavos,
            currency="brl",
            payment_method_types=["boleto"],
            receipt_email=token.email,
            metadata={
                "id_interno_pedido": str(novo_pedido.id) 
            },
            payment_method_options={
                "boleto": {
                    "expires_after_days": 2  # Vence em 2 dias
                }
            }
        )

        # 6. Confirma o boleto enviando os dados fiscais e o endereço formatado
        intent_confirmado = stripe.PaymentIntent.confirm(
            intent.id,
            payment_method_data={
                "type": "boleto",
                "billing_details": {
                    "name": token.nome_usuario, 
                    "email": token.email,
                    "address": {
                        "line1": f"{endereco.rua}, {endereco.numero}",
                        "line2": endereco.bairro, 
                        "city": endereco.cidade,
                        "state": endereco.estado.upper(), 
                        "postal_code": endereco.cep,
                        "country": "BR",
                    }
                },
                "boleto": {
                    "tax_id": cpf_limpo 
                }
            },
            return_url="http://localhost:8000/docs"
        )

        # 7. Captura os dados do boleto gerado pela Stripe (Formato Dicionário Correto)
        boleto_data = intent_confirmado['next_action']['boleto_display_details']
        
        # Salva o ID da transação no pedido
        novo_pedido.stripe_charge_id = intent.id

        # 8. Salva os itens do pedido e limpa o carrinho
        for itens in carrinho_do_usuario:
            produtos_pedidos = ItensPedidoDB(
                pedido_id=novo_pedido.id,
                produto_id=itens.produto_id,
                quantidade=itens.quantidade_produto,
                preco_unitario_centavos=int(itens.produto_no_carrinho.preco_produto * 100)
            )
            db.add(produtos_pedidos)
            db.delete(itens) 
        
        db.commit()

        # 9. Devolve para o Front-End os dados limpos
        return {
            "sucesso": True,
            "id_pedido": novo_pedido.id,
            "payment_intent_id": intent.id,
            "boleto_url_pdf": boleto_data['hosted_voucher_url'],
            "boleto_codigo_barras": boleto_data['number'],
            "expires_at": boleto_data['expires_at']
        }

    except stripe.error.StripeError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Erro Stripe: {e.user_message if e.user_message else str(e)}")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao gerar boleto: {str(e)}")


# Confirma se o boleto foi pago no painel stripe
@router.post("/api/webhooks/stripe")
async def stripe_webhook(
    request: Request, 
    stripe_signature: str = Header(None), 
    db: Session = Depends(sessao_db) 
    ):
    payload = await request.body()
    
    try:
        # 1. Valida se a requisição veio realmente da Stripe (Segurança)
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, ENDPOINT_SECRET
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Payload inválido.")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Assinatura do Webhook inválida.")

    # 2. Captura o evento de sucesso de pagamento
    if event["type"] == "payment_intent.succeeded":
        payment_intent = event["data"]["object"]
        
        # Recupera o ID do pedido que você salvou no metadata lá na criação!
        id_pedido = payment_intent["metadata"].get("id_interno_pedido")
        
        if id_pedido:
            try:
                # Busca o pedido no banco
                pedido = db.query(PedidoDB).filter(PedidoDB.id == int(id_pedido)).first()
                
                if pedido and pedido.status_pedido != 'Pago':
                    # Atualiza o status do pedido para pago
                    pedido.status_pedido = 'Pago'
                    db.commit()
                    print(f"Pedido {id_pedido} atualizado para PAGO com sucesso!")

            except Exception as e:
                db.rollback()
                # Retorna 500 para a Stripe tentar enviar de novo mais tarde se o seu banco falhar
                raise HTTPException(status_code=500, detail=f"Erro ao atualizar banco: {str(e)}")

    # 3. Retorna um status 200 para a Stripe saber que você recebeu o aviso
    return {"status": "success"}


# PRECISA COPIAR O URL DESSE ENDPOINT NO PAINEL DA STRIPE /api/webhooks/stripe
# PRECISA COPIAR O URL DESSE ENDPOINT NO PAINEL DA STRIPE /api/webhooks/stripe
# PRECISA COPIAR O URL DESSE ENDPOINT NO PAINEL DA STRIPE /api/webhooks/stripe
# PRECISA COPIAR O URL DESSE ENDPOINT NO PAINEL DA STRIPE /api/webhooks/stripe
# PRECISA COPIAR O URL DESSE ENDPOINT NO PAINEL DA STRIPE /api/webhooks/stripe
# PRECISA COPIAR O URL DESSE ENDPOINT NO PAINEL DA STRIPE /api/webhooks/stripe
# PRECISA COPIAR O URL DESSE ENDPOINT NO PAINEL DA STRIPE /api/webhooks/stripe
# PRECISA COPIAR O URL DESSE ENDPOINT NO PAINEL DA STRIPE /api/webhooks/stripe
# PRECISA COPIAR O URL DESSE ENDPOINT NO PAINEL DA STRIPE /api/webhooks/stripe
# PRECISA COPIAR O URL DESSE ENDPOINT NO PAINEL DA STRIPE /api/webhooks/stripe
# PRECISA COPIAR O URL DESSE ENDPOINT NO PAINEL DA STRIPE /api/webhooks/stripe
# PRECISA COPIAR O URL DESSE ENDPOINT NO PAINEL DA STRIPE /api/webhooks/stripe
# PRECISA COPIAR O URL DESSE ENDPOINT NO PAINEL DA STRIPE /api/webhooks/stripe
# PRECISA COPIAR O URL DESSE ENDPOINT NO PAINEL DA STRIPE /api/webhooks/stripe
# PRECISA COPIAR O URL DESSE ENDPOINT NO PAINEL DA STRIPE /api/webhooks/stripe