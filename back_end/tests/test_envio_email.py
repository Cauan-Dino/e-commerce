from fastapi.testclient import TestClient
from main import app
from routers.usuarios import sessao_db,verificar_token_access
import os

os.environ['SECRET_KEY'] = '13yad25tasc'

client = TestClient(app)

def test_enviar_email(mocker):
    import datetime
    from datetime import timezone, timedelta
    
    mock_usuario_token = mocker.MagicMock()
    mock_usuario_token.email = 'caun@gmail.com'
    mock_usuario_token.senha = 'dawe12ed'

    app.dependency_overrides[verificar_token_access] = lambda: mock_usuario_token

    mock_datetime = mocker.patch("routers.usuarios.datetime")
    fixed_now = datetime.datetime(2025, 1, 1, tzinfo=timezone.utc)
    mock_datetime.now.return_value = fixed_now

    mock_jwt_token = mocker.patch("routers.usuarios.jwt.encode")
    mock_jwt_token.return_value = 'fake_token'

    mock_tarefa = mocker.patch("routers.usuarios.enviar_tarefa")

    response = client.post('/site/deletar/conta')
    assert response.status_code == 200
    assert response.json() == {'message': 'Confirme a exclusão da sua conta no email.'}

    mock_tarefa.assert_called_once()
    mock_jwt_token.assert_called_once()
    mock_datetime.assert_called_once()

    app.dependency_overrides.clear()
    
    
# Utilizar return_value quando o retorno da função importa para a lógica. tipo: resultado = funcao() + 10
# Utilizar return_value quando o retorno da função importa para a lógica. tipo: resultado = funcao() + 10
# Utilizar return_value quando o retorno da função importa para a lógica. tipo: resultado = funcao() + 10
# Utilizar return_value quando o retorno da função importa para a lógica. tipo: resultado = funcao() + 10
# Utilizar return_value quando o retorno da função importa para a lógica. tipo: resultado = funcao() + 10
# Utilizar return_value quando o retorno da função importa para a lógica. tipo: resultado = funcao() + 10
# Utilizar return_value quando o retorno da função importa para a lógica. tipo: resultado = funcao() + 10
# Utilizar return_value quando o retorno da função importa para a lógica. tipo: resultado = funcao() + 10
# Utilizar return_value quando o retorno da função importa para a lógica. tipo: resultado = funcao() + 10
# Utilizar return_value quando o retorno da função importa para a lógica. tipo: resultado = funcao() + 10
# Utilizar return_value quando o retorno da função importa para a lógica. tipo: resultado = funcao() + 10
# Utilizar return_value quando o retorno da função importa para a lógica. tipo: resultado = funcao() + 10
# Utilizar return_value quando o retorno da função importa para a lógica. tipo: resultado = funcao() + 10
# Utilizar return_value quando o retorno da função importa para a lógica. tipo: resultado = funcao() + 10
# Utilizar return_value quando o retorno da função importa para a lógica. tipo: resultado = funcao() + 10