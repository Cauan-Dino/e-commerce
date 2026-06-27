from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from banco_dados import sessao_db, CarrinhoUsuarioDB, ProdutosLojaDB, UsuarioDB
from auth_token import verificar_token_access
from body_models import BODYCarrinhoUsuario

router = APIRouter(tags=['Carrinho'])

# Mostra o carrinho do usuario
@router.get('/site/carrinho')
async def mostrar_carrinho(db: Session = Depends(sessao_db), usuario_token: UsuarioDB = Depends(verificar_token_access)):
    # Verifica se o usuario_id existe
    usuario = db.query(UsuarioDB).filter(UsuarioDB.usuario_id == usuario_token.usuario_id).first()
    if usuario is None:
        raise HTTPException(
            status_code=404,
            detail='Esse usuario nao existe'
        )

    # Verifica se ha algo adicionado no carrinho do usuario
    carrinho_usuario = db.query(CarrinhoUsuarioDB).filter(CarrinhoUsuarioDB.usuario_id == usuario_token.usuario_id).all()
    if not carrinho_usuario:  
        raise HTTPException(
            status_code=400,
            detail='Nao existe nada adicionado no carrinho'
        )
    
    # Formatacao para mostrar oq esta adicionando no carrinho
    carrinho = [
        {
            'nome_produto':valor.produto_no_carrinho.nome_produto,
            'preco_produto': valor.produto_no_carrinho.preco_produto,
            'quantidade': valor.quantidade_produto,
        }
        for valor in carrinho_usuario
    ]

    # Criacao do dicionario que vai retornar corretamente cada carrinho
    dicionario = {'produtos':[],'soma_total': 0,}
   
    # for para adiiconar os items em cada carrinho
    for valor in carrinho:
        # Adiciona a variavel carrinho no dicionario produtos
        dicionario['produtos'].append(valor)
        # Faz o calculo total do carrinho
        dicionario['soma_total'] += valor['preco_produto'] * valor['quantidade']
    
    return dicionario

# Adicionar produto no carrinho
@router.post('/site/carrinho')
async def adicionar_produto_carrinho(body: BODYCarrinhoUsuario, db: Session = Depends(sessao_db), usuario_token: UsuarioDB = Depends(verificar_token_access)):
    # Verifica se o produto existe
    produto = db.query(ProdutosLojaDB).filter(ProdutosLojaDB.produto_id == body.produto_id).first()
    if produto is None:
        raise HTTPException(
            status_code=404,
            detail='Esse produto não existe!'
        )
    
    # Verifica se o produto esta disponivel no estoque
    estoque = db.query(ProdutosLojaDB).filter(ProdutosLojaDB.quantidade_disponivel > 0,ProdutosLojaDB.produto_id == body.produto_id).first()
    if estoque is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Esse produto não está disponível no estoque!'
        )
    
    # Verifica se o produto ja ta no carrinho
    carrinho = db.query(CarrinhoUsuarioDB).filter(
        CarrinhoUsuarioDB.usuario_id == usuario_token.usuario_id, 
        CarrinhoUsuarioDB.produto_id == body.produto_id
        ).first()
    
    # Adiciona mais 1 de quantidade se o produto ja estiver no carrinho
    if carrinho:
        carrinho.quantidade_produto += 1
    else:
        # Adiciona o produto no carrinho
        carrinho = CarrinhoUsuarioDB(
            **body.model_dump(),
            usuario_id=usuario_token.usuario_id,
            quantidade_produto=1   
            )
        db.add(carrinho)    
    
    db.commit()
    db.refresh(carrinho)

    return carrinho


# Deleta um item de um carrinho
@router.delete('/site/carrinho-item/{produto_id}')
async def deletar_produto_carrinho(produto_id: int, db: Session = Depends(sessao_db), usuario_token: UsuarioDB = Depends(verificar_token_access)):
    # Verifica se o item existe no carrinho do usuario
    item_carrinho = db.query(CarrinhoUsuarioDB).filter(
        CarrinhoUsuarioDB.produto_id == produto_id, 
        CarrinhoUsuarioDB.usuario_id == usuario_token.usuario_id, 
    ).first()
    if item_carrinho is None:
        raise HTTPException(
            status_code=404,
            detail='Item não encontrado.'
        )
    # Verifica se a quantidade em maior que um
    if item_carrinho.quantidade_produto > 1:
        item_carrinho.quantidade_produto -= 1
    else:
        db.delete(item_carrinho)
    
    db.commit()
    return {'message': f'Item deletado com sucesso'}
