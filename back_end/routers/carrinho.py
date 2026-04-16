from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from banco_dados import sessao_db, CarrinhoUsuarioDB, CriarCarrinhoDB, ProdutosLojaDB, UsuarioDB
from auth_token import verificar_token_access
from body_models import BODYCarrinhoUsuario, BODYCriarCarrinho

router = APIRouter()

# Mostra o carrinho do usuario
@router.get('/site/carrinho/{carrinho_id}')
async def mostrar_carrinho(carrinho_id: int = None, db: Session = Depends(sessao_db), usuario_token: UsuarioDB = Depends(verificar_token_access)):
    # Verifica se o usuario_id existe
    usuario = db.query(UsuarioDB).filter(UsuarioDB.usuario_id == usuario_token.usuario_id).first()
    if usuario is None:
        raise HTTPException(
            status_code=404,
            detail='Esse usuario nao existe'
        )
    
    # Filtra por carrinho_id
    carrinho = db.query(CarrinhoUsuarioDB)
    if carrinho_id is not None:
        carrinho = carrinho.filter(CarrinhoUsuarioDB.carrinho_id == carrinho_id)

    # Verifica se ha algo adicionado no carrinho do usuario
    carrinho_usuario = carrinho.filter(CarrinhoUsuarioDB.carrinho_usuario_id == usuario_token.usuario_id).all()
    if not carrinho_usuario:  
        raise HTTPException(
            status_code=400,
            detail='Nao existe nada adicionado no carrinho'
        )

    carrinho = [
        {
            'nome_produto':valor.produto_no_carrinho.nome_produto,
            'preco_produto': valor.produto_no_carrinho.preco_produto,
            'carrinho_id': valor.carrinho_id,
            'quantidade': valor.quantidade_produto
        }
        for valor in carrinho_usuario
    ]

    # Lista com todos os carrinhos_id
    carrinhos_id = []
    for valor in carrinho:
        carrinhos_id.append(valor['carrinho_id'])

    carrinhos_id_formatado = list(set(carrinhos_id)) 
    
    # Criacao do dicionario que vai retornar corretamente cada carrinho
    lista = []
    for valor in carrinhos_id_formatado:
        lista.append({'carrinho_id':valor,'produtos':[],'soma_total': 0,})
   
    # for para adiiconar os items em cada carrinho
    for valor in carrinho:
        # Pega o index dos id do carrinho
        index = carrinhos_id_formatado.index(valor['carrinho_id'])
        # Adiciona no dicionario lista
        lista[index]['produtos'].append(valor)
        # Adiciona a soma total de produtos de cada carrinho
        lista[index]['soma_total'] += valor['preco_produto'] * valor['quantidade']
    
    return lista

# Adicionar produto no carrinho
@router.post('/site/carrinho')
async def adicionar_produto_carrinho(body: BODYCarrinhoUsuario, db: Session = Depends(sessao_db), usuario_token: UsuarioDB = Depends(verificar_token_access)):
    # Verifica se o carrinho existe
    existe_carrinho = db.query(CriarCarrinhoDB).filter(CriarCarrinhoDB.usuario_id == usuario_token.usuario_id, CriarCarrinhoDB.carrinho_id == body.carrinho_id).first()
    if existe_carrinho is None:
        raise HTTPException(
            status_code=400,
            detail='Esse carrinho não existe!'
        )
    
    # Verifica se o produto existe
    produto = db.query(ProdutosLojaDB).filter(ProdutosLojaDB.produto_id == body.produto_id).first()
    if produto is None:
        raise HTTPException(
            status_code=404,
            detail='Esse produto não existe!'
        )
    
    # Verifica se o produto ja ta no carrinho
    carrinho = db.query(CarrinhoUsuarioDB).filter(
        CarrinhoUsuarioDB.carrinho_usuario_id == usuario_token.usuario_id, 
        CarrinhoUsuarioDB.carrinho_id == body.carrinho_id,
        CarrinhoUsuarioDB.produto_id == body.produto_id
        ).first()
    
    # Adiciona mais 1 de quantidade se o produto ja estiver no carrinho
    if carrinho:
        carrinho.quantidade_produto += 1
    else:
        # Adiciona o produto no carrinho
        carrinho = CarrinhoUsuarioDB(
            **body.model_dump(),
            carrinho_usuario_id=usuario_token.usuario_id,
            nome_produto=produto.nome_produto,
            quantidade_produto=1
            )
        db.add(carrinho)    
    
    db.commit()
    db.refresh(carrinho)

    return carrinho

# Cria um carrinho
@router.post('/site/criar/carrinho')
async def criar_carrinho(body: BODYCriarCarrinho, db: Session = Depends(sessao_db), usuario_token: UsuarioDB = Depends(verificar_token_access)):
    # Verifica se o carrinho ja existe
    carrinho = db.query(CriarCarrinhoDB).filter(CriarCarrinhoDB.usuario_id == usuario_token.usuario_id, CriarCarrinhoDB.carrinho_id == body.carrinho_id).first()
    if carrinho:
        raise HTTPException(
            status_code=400,
            detail='Esse carrinho ja existe'
        )

    # Cria um carrinho
    criar_carrinho = CriarCarrinhoDB(**body.model_dump(), usuario_id=usuario_token.usuario_id)
    db.add(criar_carrinho)
    db.commit()
    db.refresh(criar_carrinho)

    return criar_carrinho   

# Deletar carrinho
@router.delete('/site/carrinho/{carrinho_id}')
async def deletar_carrinho(carrinho_id: int, db: Session = Depends(sessao_db), usuario_token: UsuarioDB = Depends(verificar_token_access)):
    # Verifica se o usuario possui esse carrinho
    carrinho = db.query(CriarCarrinhoDB).filter(CriarCarrinhoDB.usuario_id == usuario_token.usuario_id, CriarCarrinhoDB.carrinho_id == carrinho_id).first()
    if carrinho is None:
        raise HTTPException(
            status_code=404,
            detail='Esse usuário não possui esse carrinho!'
        )
    # Deleta o carrinho que esta no Banco de Dados CriarCarrinhoDB
    db.delete(carrinho)
    # Deleta o carrinho que esta em CarrinhoUsuarioDB
    carrinho_usuario = db.query(CarrinhoUsuarioDB).filter(CarrinhoUsuarioDB.carrinho_usuario_id == usuario_token.usuario_id, CarrinhoUsuarioDB.carrinho_id == carrinho_id).delete()
    db.commit()

    return {'message': f'Carrinho {carrinho_id} deletado com sucesso'}

# Deleta um item de um carrinho
@router.delete('/site/carrinho-item/{carrinho_id}/{produto_id}')
async def deletar_produto_carrinho(carrinho_id: int, produto_id: int, db: Session = Depends(sessao_db), usuario_token: UsuarioDB = Depends(verificar_token_access)):
    # Verifica se o item existe no carrinho do usuario
    item_carrinho = db.query(CarrinhoUsuarioDB).filter(
        CarrinhoUsuarioDB.produto_id == produto_id, 
        CarrinhoUsuarioDB.carrinho_usuario_id == usuario_token.usuario_id, 
        CarrinhoUsuarioDB.carrinho_id == carrinho_id
    ).first()
    if item_carrinho is None:
        raise HTTPException(
            status_code=404,
            detail='Item não encontrado.'
        )
    db.delete(item_carrinho)
    db.commit()

    return {'message': f'Item deletado com sucesso'}
