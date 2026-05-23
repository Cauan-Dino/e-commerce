import json
import uuid
import shutil
from fastapi import APIRouter, Depends, HTTPException, Form, UploadFile, File
from sqlalchemy.orm import Session

from banco_dados import sessao_db, ProdutosLojaDB, UsuarioDB
from redis_config import redis_client
from auth_token import verificar_token_access
from body_models import BODYProdutosLojaPUT
from routers.dependencias import autorizacao

router = APIRouter()

# Mostra todos os produtos cadastrados
@router.get('/site/produtos')
async def produtos_cadastrados(db: Session = Depends(sessao_db), produto_id: int = None, categoria_produto: str = None, page: int = 1, nome_produto: str = None):
    limit = 30
    if page < 1:
        raise HTTPException(
            status_code=400,
            detail='A pagina nao pode ser menos que 1'
        )
    
    key = f'produtos:page:{page}:limit:{limit}:categoria:{categoria_produto}:id:{produto_id}:nome_produto:{nome_produto}'

    cache = redis_client.get(key)
    if cache:
        return {'produtos': json.loads(cache), 'ttl': redis_client.ttl(key)}

    produto = db.query(ProdutosLojaDB)
    # Filtra por nome
    if nome_produto is not None:
        produto = produto.filter(ProdutosLojaDB.nome_produto == nome_produto)

    # Filtra por categoria
    if categoria_produto is not None:
        produto = produto.filter(ProdutosLojaDB.categoria_produto == categoria_produto)

    # Filtro por id
    if produto_id is not None:
        produto = produto.filter(ProdutosLojaDB.produto_id == produto_id)
        
    produto_all = produto.offset((page-1)*limit).limit(limit).all()

    if not produto_all:
        raise HTTPException(
            status_code=404,
            detail='Ocorreu um erro na filtragem'
        )
    
    paginacao = [
        {
            'produto': valor.nome_produto,
            'preco': valor.preco_produto,
            'categoria': valor.categoria_produto,
            'produto_id': valor.produto_id
        }
        for valor in produto_all
    ]

    redis_client.setex(key, 300, json.dumps(paginacao))

    return paginacao

# Mostra todo o redis
@router.get('/site/mostrar/redis-inteiro')
async def mostrar_todo_redis(_: None = Depends(autorizacao)):
    # Pega todas as chaves do redis
    keys = redis_client.keys('produtos:*')
    
    # Verifica se o redis esta vazio
    if not keys:
        raise HTTPException(
            status_code=404,
            detail='Nao ha nada cadastrado no redis'
        )
    
    lista = []
    for key in keys:
        valor = redis_client.get(key)
        ttl = redis_client.ttl(key)
        lista.append({'chave': key, 'valor': json.loads(valor), 'ttl': ttl})
    
    return lista

# Adiciona um produto no site
@router.post('/site/produto/adicionar')
async def adicionar_produto(
    nome_produto: str = Form(...),
    preco_produto: float = Form(...),
    categoria_produto: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(sessao_db),
    __: None = Depends(autorizacao)
    ):

    # 1. Validação básica (sem ler o conteúdo ainda)
    if not file.content_type.startswith("image/"):
        return {"erro": "O arquivo enviado não é uma imagem válida."}
    
    extensao = file.filename.split(".")[-1]
    nome_unico = f"{uuid.uuid4()}.{extensao}"
    caminho_no_disco = f"fotos_produtos/{nome_unico}"

     # 3. Salvar o arquivro
    try:
        with open(caminho_no_disco, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        return {"erro": f"Falha ao salvar arquivo: {str(e)}"}


    produto = ProdutosLojaDB(
        nome_produto=nome_produto,
        preco_produto=preco_produto,
        categoria_produto=categoria_produto,
        url_foto_produto=caminho_no_disco
    )
    
    db.add(produto)
    db.commit()
    
    # Exclui tudo que esta no redis
    key = 'produtos:*'
    keys = redis_client.keys(key)
    # For para excluir todas as chaves
    for key in keys:
        redis_client.delete(key)

    return {
        'message': f'produto {nome_produto} cadastrado com sucesso',
        'nome_arquvio': nome_unico
    }

# Altera informacoes de um produto
@router.put('/site/alterar-produto/{produto_id}')
async def alterar_produto(
    produto_id: int,
    body: BODYProdutosLojaPUT,
    db: Session = Depends(sessao_db),
    _: None = Depends(autorizacao)
    ):
    
    # Verifica se o produto existe
    produto = db.query(ProdutosLojaDB).filter(
        ProdutosLojaDB.produto_id == produto_id
    ).first()

    if produto is None:
        raise HTTPException(
            status_code=404,
            detail='Esse produto não existe'
        )
    
    # Verifica se o campo nome esta preenchido
    if body.nome_produto is not None:
        produto.nome_produto = body.nome_produto
    # Verifica se o campo preco esta preenchido
    if body.preco_produto is not None:
        produto.preco_produto = body.preco_produto
    # Verifica se o campo categoria esta preenchido
    if body.categoria_produto is not None:
        produto.categoria_produto = body.categoria_produto

    db.commit()
    db.refresh(produto)

    # Deleta todo o redis que armazena os produtos
    keys = redis_client.keys('produtos:*')
    for key in keys:
        redis_client.delete(key)

    return {'message': 'Produto alterado com sucesso'}

# Deleta todo o redis
@router.delete('/site/redis')
async def deletar_redis():
    # Pega todas as chaves do redis
    keys = redis_client.keys('produtos:*')
    # Verifica se o redis existe
    if not keys:
        raise HTTPException(
            status_code=400,
            detail='Nao existe nada no redis'
        )
    # Deleta todo o redis
    for key in keys:
        redis_client.delete(key)
    
    return {'message': 'todo o redis foi deletado'}
