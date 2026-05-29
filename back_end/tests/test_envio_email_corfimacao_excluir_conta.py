from fastapi.testclient import TestClient
from main import app
from routers.usuarios import sessao_db,verificar_token_access
import os

os.environ['SECRET_KEY'] = '13yad25tasc'

client = TestClient(app)


def test_envio_de_email_para_excluir_conta(mocker):
    import datetime
    from datetime import timezone, timedelta
    mock_usuario_token = mocker.MagicMock()
    mock_usuario_token.senha_usuario = 'asdawda'
    mock_usuario_token.email = 'cauan@gmail.com'

    payload = {
        'senha':'asdawda',
        'email':'cauan@gmail.com'
    }

    app.dependency_overrides[verificar_token_access] = lambda: mock_usuario_token

    mock_pwd_context = mocker.patch("routers.usuarios.pwd_context.verify")
    mock_jwt_encode = mocker.patch("routers.usuarios.jwt.encode")
    mock_enviar_tarefa = mocker.patch("routers.usuarios.enviar_tarefa")

    mock_datetime = mocker.patch("routers.usuarios.datetime")
    fixed_now = datetime.datetime(2025, 1, 1, tzinfo=timezone.utc)
    mock_datetime.now.return_value = fixed_now

    mock_pwd_context.return_value = True
    mock_jwt_encode.return_value = "fake_token_123"

    response = client.post('/site/deletar/conta',json=payload)
    assert response.status_code == 200
    assert response.json() == {'message': 'Confirme a exclusão da sua conta no email.'}

    mock_pwd_context.assert_called_once()
    
    mock_jwt_encode.assert_called_once()
    mock_enviar_tarefa.assert_called_once()

    app.dependency_overrides.clear()