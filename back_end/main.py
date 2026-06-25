from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from auth_token import auth_router
from auth_google import router as auth_google_router
from routers.carrinho import router as carrinho_router
from routers.usuarios import router as usuarios_router
from routers.endereco import router as endereco_router
from routers.cartoes import router as configuracao_cartoes_de_credito
from routers.produtos import router as produtos_router
from routers.compra_via_boleto import router as compra_via_boleto
from routers.compra_via_cartao import router as compra_via_cartao

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permite qualquer origem (em produção, coloque o IP do front)
    allow_methods=["*"],
    allow_headers=["*"],    
)

app.mount("/uploads", StaticFiles(directory="fotos_produtos"), name="fotos_produtos")
app.mount("/front", StaticFiles(directory="../front_end"), name="front")

app.include_router(auth_router)
app.include_router(auth_google_router)
app.include_router(carrinho_router)
app.include_router(usuarios_router)
app.include_router(endereco_router)
app.include_router(configuracao_cartoes_de_credito)
app.include_router(produtos_router)
app.include_router(compra_via_boleto)
app.include_router(compra_via_cartao)