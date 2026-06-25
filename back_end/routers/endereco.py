import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from banco_dados import sessao_db, EnderecoUsuarioDB, UsuarioDB
from auth_token import verificar_token_access
from body_models import BODYEnderecoUsuario, BODYEnderecoUsuarioPUT
from redis_config import redis_client

router = APIRouter(tags=['Endereço'])

# Mostra os enderecos cadastrado do usuario
@router.get('/site/endereco')
async def mostrar_endereco(db: Session = Depends(sessao_db), usuario_token: UsuarioDB = Depends(verificar_token_access)):
    # Chave do redis que mostra o endereco
    key = f'endereco:{usuario_token.usuario_id}'
    # Verifica se o redis existe
    redis = redis_client.get(key)
    # Retorna o redis caso exista
    if redis:
        return {'enderecos': json.loads(redis), 'ttl': redis_client.ttl(key)}
    
    # Verifica se o usuario tem algum endereco cadastrado existe
    endereco = db.query(EnderecoUsuarioDB).filter(EnderecoUsuarioDB.usuario_id == usuario_token.usuario_id).all()
    if not endereco:
        raise HTTPException(
            status_code=404,
            detail='Ainda nao ha nenhum endereco cadastrado'
        )
    
    dicionario_redis = []

    for valor in endereco:  
        dicionario_redis.append({
            'usuario_id': valor.usuario_id,
            'endereco_nomeado': valor.endereco_nomeado,
            'bairro': valor.bairro,
            'numero': valor.numero,
            'cidade': valor.cidade,
            'estado': valor.estado,
            'complementeo': valor.complemento,
            'cep': valor.cep
        })

    redis_client.setex(f'endereco:{usuario_token.usuario_id}', 300, json.dumps(dicionario_redis))

    return {'enderecos': dicionario_redis}



# Adiciona um endereco da casa do usuario
@router.post('/site/endereco')
async def criar_endereco(body: BODYEnderecoUsuario, db: Session = Depends(sessao_db), usuario_token: UsuarioDB = Depends(verificar_token_access)):
    # Verifica se a quantidade de enderecos ultrapassou 3
    quantidade_enderecos = db.query(EnderecoUsuarioDB).filter(EnderecoUsuarioDB.usuario_id == usuario_token.usuario_id).count()
    if quantidade_enderecos >= 10:
        raise HTTPException(
            status_code=400,
            detail='Voce ja atingiu o limite de enderecos cadastrados'
        )
    
    # Verifica se o endereco ja existe
    endereco = db.query(EnderecoUsuarioDB).filter(EnderecoUsuarioDB.usuario_id == usuario_token.usuario_id, EnderecoUsuarioDB.endereco_nomeado == body.endereco_nomeado).first()
    if endereco:
        raise HTTPException(
            status_code=400,
            detail='Esse endereco ja existe'
        )
    
    # Tira o "-" do CEP
    cep_formatado = "".join(filter(str.isnumeric,body.cep))
    
    # Verifica se ha 8 digitos
    if len(cep_formatado) != 8:
        raise HTTPException(
            status_code=400,
            detail='Informe um CEP válido!'
        )

    # Adiciona o endereco no banco de dados
    adicionar_endereco = EnderecoUsuarioDB(
        endereco_nomeado=body.endereco_nomeado,
        rua=body.rua,
        bairro=body.bairro,
        numero=body.numero,
        cidade=body.cidade.upper(),
        estado=body.estado,
        cep=cep_formatado,
        complemento=body.complemento,
        usuario_id=usuario_token.usuario_id
    )
    db.add(adicionar_endereco)
    db.commit()
    db.refresh(adicionar_endereco)

    # -------- Exclui todas as informacoes do redis no endereco --------
    
    # Verifica se tem algo adicionado no redis
    valor = redis_client.get(f'endereco:{usuario_token.usuario_id}')
    if valor:
        redis_client.delete(f'endereco:{usuario_token.usuario_id}')

    return adicionar_endereco



# Deleta um endereco do usuario
@router.delete('/site/endereco/{nome_endereco}')
async def deletar_endereco(nome_endereco: str, db: Session = Depends(sessao_db), usuario_token: UsuarioDB = Depends(verificar_token_access)):
    # Verifica se o usuario existe e o endereco existem
    verificacao = db.query(EnderecoUsuarioDB).filter(EnderecoUsuarioDB.usuario_id == usuario_token.usuario_id, EnderecoUsuarioDB.endereco_nomeado == nome_endereco).first()
    if verificacao is None:
        raise HTTPException(
            status_code=404,
            detail='Esse endereço não existe!'
        )
    # Deleta o endereco
    db.delete(verificacao)
    db.commit()

    # Deleta o endereco no redis
    key = redis_client.get(f'endereco:{usuario_token.usuario_id}')
    # Verifica se existe
    if key:
        # Trasforma em dicionario
        lista = json.loads(key)
        for i, v in enumerate(lista):
            if v['endereco_nomeado'] == nome_endereco:
                del lista[i]
        
        redis_client.setex(f'endereco:{usuario_token.usuario_id}', 300, json.dumps(lista))
    
    return {'message': 'Endereço deletado com sucesso!'}

# Altera o endereco do usuario
@router.put('/site/alterar-endereco/{endereco_nomeado}')
async def alterar_endereco(
    endereco_nomeado: str, 
    body: BODYEnderecoUsuarioPUT, 
    db: Session = Depends(sessao_db),
    usuario_token: UsuarioDB = Depends(verificar_token_access)
    ):
    # Verifica se o usuario possui esse endereco
    endereco = db.query(EnderecoUsuarioDB).filter(
        EnderecoUsuarioDB.usuario_id == usuario_token.usuario_id,
        EnderecoUsuarioDB.endereco_nomeado == endereco_nomeado
    ).first()
    if endereco is None:
        raise HTTPException(
            status_code=404,
            detail='Esse endereço não existe'
        )
    
    # Verifica se o campo endereco_nomeado esta preenchido
    if body.endereco_nomeado is not None:
        endereco.endereco_nomeado = body.endereco_nomeado
    
    # Verifica se o campo bairro esta preenchido
    if body.bairro is not None:
        endereco.bairro = body.bairro
    
    # Verifica se o campo numero esta preenchido
    if body.numero is not None:
        endereco.numero = body.numero
    
    # Verifica se o campo cidade esta preenchido
    if body.cidade is not None:
        endereco.cidade = body.cidade
    
    # Verifica se o campo estado esta preenchido
    if body.estado is not None:
        endereco.estado = body.estado.upper()
    
    # Verifica se o campo cep esta preenchido
    if body.cep is not None:
        
        # Tira o "-" do CEP
        cep_formatado = "".join(filter(str.isnumeric,body.cep))
        
        # Verifica se ha 8 digitos
        if len(cep_formatado) != 8:
            raise HTTPException(
                status_code=400,
                detail='Informe um CEP válido!'
            )
        endereco.cep = cep_formatado

    # Verifica se o campo complemento esta vazio
    if body.complemento is not None:
        endereco.complemento = body.complemento
    
    # Verifica se o campo rua esta vazio
    if body.rua is not None:
        endereco.rua = body.rua
    
    db.commit()
    db.refresh(endereco)

    return endereco
