# script.ps1
# Sobe todo o ambiente Kubernetes: Podman, minikube, Redis, Zookeeper, Kafka, Celery e API

# 1. Inicia o Podman
Write-Host "Iniciando Podman..."
$podmanStatus = podman machine list 2>&1
if ($podmanStatus -match "Currently running") {
    Write-Host "Podman já está rodando."
} else {
    podman machine start
    Start-Sleep -Seconds 5
}

# 2. Inicia o minikube
Write-Host "Verificando minikube..."
if (Get-Command minikube -ErrorAction SilentlyContinue) {
    $status = minikube status 2>&1
    if ($status -match "Running") {
        Write-Host "Minikube já está rodando."
    } else {
        Write-Host "Iniciando minikube..."
        minikube start --driver=podman
    }
} else {
    Write-Host "Minikube não instalado. Instale em: https://minikube.sigs.k8s.io/docs/start"
    exit 1
}

# 3. Verifica se o ConfigMap existe, cria se não existir
Write-Host "Verificando ConfigMap..."
$configmap = kubectl get configmap e-commerce-api-env 2>&1
if ($configmap -match "not found" -or $configmap -match "Error") {
    Write-Host "Criando ConfigMap e-commerce-api-env..."
    kubectl create configmap e-commerce-api-env --from-env-file=env_test.env
} else {
    Write-Host "ConfigMap já existe."
}

# 4. Verifica se a imagem existe no minikube, builda se não existir
Write-Host "Verificando imagem e-commerce-api no minikube..."
$imagem = minikube image ls 2>&1 | Select-String "e-commerce-api"
if (-not $imagem) {
    Write-Host "Imagem não encontrada. Configurando variáveis de ambiente do Minikube..."
    
    # Aponta os comandos de container para dentro do nó do Minikube
    minikube docker-env | Invoke-Expression
    
    Write-Host "Buildando imagem com Podman diretamente no Minikube (usando .dockerignore)..."
    podman build -t e-commerce-api:latest .
} else {
    Write-Host "Imagem já existe no minikube."
}

# 5. Sobe Redis e Zookeeper
Write-Host "Subindo Redis e Zookeeper..."
kubectl apply -f kubernetes/redis.yaml
kubectl apply -f kubernetes/zookeeper.yaml

Write-Host "Aguardando Zookeeper ficar pronto..."
kubectl wait --for=condition=available --timeout=60s deployment/zookeeper

# 6. Sobe Kafka
Write-Host "Subindo Kafka..."
kubectl apply -f kubernetes/kafka.yaml

Write-Host "Aguardando Kafka ficar pronto (pode demorar ate 2 minutos)..."
kubectl wait --for=condition=available --timeout=120s deployment/kafka

# 7. Sobe API e Celery
Write-Host "Subindo API e Celery..."
kubectl apply -f kubernetes/deployment.yaml
kubectl apply -f kubernetes/service.yaml
kubectl apply -f kubernetes/celery-worker.yaml

Write-Host "Aguardando API ficar pronta..."
kubectl wait --for=condition=available --timeout=60s deployment/e-commerce-api

# 8. Mostra status final
Write-Host ""
Write-Host "Status dos pods:"
kubectl get pods

# 9. Inicia port-forward em background
Write-Host ""
Write-Host "Iniciando port-forward para localhost:8000..."
$job = Start-Job -ScriptBlock {
    kubectl port-forward svc/e-commerce-service 8000:80
}

Start-Sleep -Seconds 3

# 10. Abre o navegador
Start-Process "http://localhost:8000/docs"

Write-Host "Aplicacao disponivel em http://localhost:8000/docs"
Write-Host "Pressione Ctrl+C para parar o port-forward."

try {
    while ($true) { Start-Sleep -Seconds 1 }
} finally {
    Write-Host "Parando port-forward..."
    Stop-Job -Job $job -ErrorAction SilentlyContinue
    Remove-Job -Job $job -ErrorAction SilentlyContinue
}