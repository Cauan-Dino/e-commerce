const BASE_URL = 'http://localhost:8000';

function showSection(section) {
    const sections = ['produtos-section', 'carrinho-section', 'usuario-section', 'admin-section'];
    sections.forEach(s => document.getElementById(s).style.display = 'none');
    document.getElementById(`${section}-section`).style.display = 'block';
    if(section === 'produtos') loadProdutos();
}

// --- ADMIN: ADICIONAR PRODUTO ---
document.getElementById('form-admin-produto').addEventListener('submit', async (e) => {
    e.preventDefault();
    const feedback = document.getElementById('admin-feedback');
    const user = document.getElementById('admin-user').value;
    const pass = document.getElementById('admin-pass').value;

    const formData = new FormData();
    // Enviamos 0 porque o campo é obrigatório no Form do Python, mas a PK cuida do valor real
    formData.append('produto_id', 0); 
    formData.append('nome_produto', document.getElementById('prod-nome').value);
    formData.append('preco_produto', document.getElementById('prod-preco').value);
    formData.append('categoria_produto', document.getElementById('prod-categoria').value);
    formData.append('file', document.getElementById('prod-file').files[0]);

    const credentials = btoa(`${user}:${pass}`);

    try {
        feedback.innerText = "Enviando...";
        const response = await fetch(`${BASE_URL}/site/produto/adicionar`, {
            method: 'POST',
            headers: { 'Authorization': `Basic ${credentials}` },
            body: formData
        });

        const data = await response.json();
        if (response.ok) {
            feedback.innerHTML = `<span style="color: green;">✓ ${data.message}</span>`;
            document.getElementById('form-admin-produto').reset();
            loadProdutos();
        } else {
            feedback.innerHTML = `<span style="color: red;">⚠ Erro: ${data.detail}</span>`;
        }
    } catch (err) {
        feedback.innerHTML = `<span style="color: red;">⚠ Erro de conexão com o servidor.</span>`;
    }
});

// --- LISTAR PRODUTOS ---
async function loadProdutos() {
    let url = `${BASE_URL}/site/produtos?page=1`;
    const nome = document.getElementById('search-nome').value;
    if (nome) url += `&nome_produto=${nome}`;

    try {
        const response = await fetch(url);
        const data = await response.json();
        const container = document.getElementById('lista-produtos');
        container.innerHTML = '';

        const produtos = Array.isArray(data) ? data : (data.produtos || []);

        produtos.forEach(p => {
            container.innerHTML += `
                <div class="card" style="border: 1px solid #ccc; padding: 10px; margin: 10px; border-radius: 8px; display: inline-block; width: 200px; text-align: center;">
                    <h3>${p.produto}</h3>
                    <p>R$ ${p.preco.toFixed(2)}</p>
                    <small>${p.categoria}</small>
                </div>`;
        });
    } catch (err) { console.error(err); }
}

// --- LIMPAR REDIS ---
async function limparCache() {
    try {
        const response = await fetch(`${BASE_URL}/site/redis`, { method: 'DELETE' });
        const data = await response.json();
        alert(data.message || data.detail);
    } catch (err) { alert("Erro ao limpar cache."); }
}

// --- CARRINHO ---
async function loadCarrinho() {
    const userId = document.getElementById('input-usuario-id').value;
    if (!userId) return alert("ID necessário");
    try {
        const response = await fetch(`${BASE_URL}/site/carrinho/${userId}`);
        const data = await response.json();
        const container = document.getElementById('detalhe-carrinho');
        container.innerHTML = response.ok ? JSON.stringify(data, null, 2) : data.detail;
    } catch (err) { alert("Erro no carrinho."); }
}

// --- USUÁRIO ---
document.getElementById('form-usuario').addEventListener('submit', async (e) => {
    e.preventDefault();
    const payload = {
        nome_usuario: document.getElementById('nome-usuario').value,
        email_usuario: document.getElementById('email-usuario').value
    };
    await fetch(`${BASE_URL}/site/usuario`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    alert("Usuário criado!");
    document.getElementById('form-usuario').reset();
});

loadProdutos();