from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from auth_token import auth_router
from auth_google import router as auth_google_router
from routers.carrinho import router as carrinho_router
from routers.usuarios import router as usuarios_router
from routers.endereco import router as endereco_router
from routers.compra import router as compra_router
from routers.produtos import router as produtos_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permite qualquer origem (em produção, coloque o IP do front)
    allow_methods=["*"],
    allow_headers=["*"],    
)

app.mount("/uploads", StaticFiles(directory="fotos_produtos"), name="fotos_produtos")
app.mount("/front", StaticFiles(directory="/front_end"), name="front")

app.include_router(auth_router)
app.include_router(auth_google_router)
app.include_router(carrinho_router)
app.include_router(usuarios_router)
app.include_router(endereco_router)
app.include_router(compra_router)
app.include_router(produtos_router)