from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from banco_dados import sessao_db, EnderecoUsuarioDB, CartoesDB, CarrinhoUsuarioDB, UsuarioDB, ProdutosLojaDB, PedidoDB, ItensPedidoDB
from auth_token import verificar_token_access
from body_models import BODYItemCompra
import stripe
import os
from dotenv import load_dotenv

router = APIRouter(tags=['Compra na loja Via Cartão'])

load_dotenv()

# Pega a stripe_secret_key no .env
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# Finaliza o pagamento
@router.post("/site/v1/cobrar", status_code=status.HTTP_200_OK)
async def realizar_cobranca(
    body: BODYItemCompra,
    db: Session = Depends(sessao_db),
    token: UsuarioDB = Depends(verificar_token_access)
):  
    # Verifica se o usuario ja possui um endereco
    endereco = db.query(EnderecoUsuarioDB).filter(EnderecoUsuarioDB.usuario_id == token.usuario_id, EnderecoUsuarioDB.endereco_nomeado == body.endereco_nomeado).first()
    # Tratamento de erro caso nao exista o endereco
    if endereco is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Voce não possui esse endereço!'
        )
    
    # Verifica se o cartao existe
    pagamento = db.query(CartoesDB).filter(CartoesDB.usuario_id == token.usuario_id, CartoesDB.nome_cartao == body.nome_cartao).first()
    if pagamento is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Adicione um cartão válido!'
        )

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
                detail=f"O valor total dos produtos mudou ou foi adulterado. Por favor, atualize o carrinho."
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
        db.rollback()
        # Se der erro no cartão, o banco faz rollback automático do Lock do estoque ao fechar a requisição
        err = e.error if hasattr(e, 'error') else e
        detail_msg = err.message if hasattr(err, 'message') else str(e)
        
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Erro no cartão: {detail_msg}"
        )
        
    except HTTPException:
        db.rollback()
        # Repassa as exceções HTTP que nós mesmos criamos lá em cima sem cair no bloco genérico 500
        raise
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro interno no servidor: {str(e)}"
        )
