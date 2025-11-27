// Importa apenas as funções que você exportou do api.js
import { cancelarInteresse, consultarLeiloes, criarLeilao, efetuarLance, registrarInteresse } from './api.js';

// --- 1. Configurações Globais ---
const URL_BASE = 'http://localhost:3000';
let clienteId = null;
let sseConnection = null;

// --- 2. Referências aos elementos do HTML ---
const logNotificacoes = document.getElementById('notificacoes');
const btnConectar = document.getElementById('btnConectar');
const btnCriarLeilao = document.getElementById('btnCriarLeilao');
const btnDarLance = document.getElementById('btnDarLance');
const btnRegistrar = document.getElementById('btnRegistrar');
const btnCancelar = document.getElementById('btnCancelar');
const btnConsultar = document.getElementById('btnConsultar');
const inputClienteId = document.getElementById('clienteId');
const inputLeilaoIdInteracao = document.getElementById('leilaoIdInteracao');

// --- 3. Funções Auxiliares ---
function log(origem, mensagem) {
    console.log(origem, mensagem);
    const p = document.createElement('p');
    p.innerHTML = `<strong>[${origem}]:</strong> ${JSON.stringify(mensagem)}`;
    logNotificacoes.prepend(p);
}

// Conectar ao SSE
// --- 4. Lógica de Eventos ---

// Conectar ao SSE
btnConectar.onclick = function() {
    clienteId = inputClienteId.value;
    if (!clienteId) return alert('Digite um ID');

    if (sseConnection) sseConnection.close();
    log('SSE', `Conectando como: ${clienteId}`);
    
    sseConnection = new EventSource(`${URL_BASE}/stream?channel=${clienteId}`);
    sseConnection.onopen = () => log('SSE', 'Conexão estabelecida!');
    
    // Ouvindo os eventos
    sseConnection.addEventListener('novo_lance', (e) => log('SSE: Novo Lance', JSON.parse(e.data)));
    sseConnection.addEventListener('lance_invalido', (e) => log('SSE: Lance Inválido', JSON.parse(e.data)));
    sseConnection.addEventListener('leilao_vencedor', (e) => log('SSE: Vencedor', JSON.parse(e.data)));
    
    // Recebe o link de pagamento.
    sseConnection.addEventListener('link_pagamento', (e) => {
        const dados = JSON.parse(e.data);
        log('SSE: 💰 LINK DE PAGAMENTO', dados);
        alert(`Parabéns! Você venceu o leilão ${dados.id_leilao}. Link: ${dados.link}`);
    });
    
    // Recebe a atualização do status do pagamento (após o webhook do MS Pagamento).
    sseConnection.addEventListener('status_pagamento', (e) => {
        const dados = JSON.parse(e.data);
        log('SSE: ✅ STATUS PAGAMENTO', dados);
        alert(`Atualização do Pagamento (Leilão ${dados.id_leilao}): ${dados.status}`);
    });
};

// Criar Leilão (agora chama a função do api.js)
btnCriarLeilao.onclick = async function() {
    const dados = {
        produto: document.getElementById('leilaoProduto').value,
        descricao: "Descrição...",
        valor_inicial: 1.0, // (Pode adicionar os inputs depois)
        hora_inicio: new Date(document.getElementById('leilaoInicio').value).toISOString(),
        hora_fim: new Date(document.getElementById('leilaoFim').value).toISOString(),
    };

    log('API (Request)', dados);
    try {
        const resultado = await criarLeilao(dados);
        log('API (Sucesso)', resultado);
        alert('Leilão criado!');
    } catch (err) {
        log('API (Erro)', err.message);
    }
};

// Dar Lance (agora chama a função do api.js)
btnDarLance.onclick = async function() {
    if (!clienteId) return alert('Conecte-se primeiro.');

    const leilaoId = parseInt(inputLeilaoIdInteracao.value);
    const valor = parseFloat(document.getElementById('lanceValor').value);

    log('API (Lance)', { leilaoId, valor });
   try {
        // 1. Tenta efetuar o lance
        const resultado = await efetuarLance(leilaoId, clienteId, valor);
        log('API (Sucesso Lance)', resultado);
        
        // 2. Se o lance deu certo (não caiu no catch), registra o interesse automaticamente
        await registrarInteresse(leilaoId, clienteId);
        log('API (Auto-Registro)', `Interesse registrado automaticamente para o leilão ${leilaoId}`);
        
        alert('Lance efetuado e interesse registrado!');
        
    } catch (err) {
        // Se o lance falhar (ex: valor baixo), não registramos interesse
        log('API (Erro Lance)', err.message);
    }
};

// Registrar Interesse (agora chama a função do api.js)
btnRegistrar.onclick = async function() {
    if (!clienteId) return alert('Conecte-se primeiro.');
    
    const leilaoId = inputLeilaoIdInteracao.value;
    log('API (Registrar)', { leilaoId, clienteId });
    try {
        const resultado = await registrarInteresse(leilaoId, clienteId); 
        log('API (Sucesso Registro)', resultado);
        alert('Interesse registrado!');
    } catch (err) {
        log('API (Erro Registro)', err.message);
    }
};

btnCancelar.onclick= async function () {
    if (!clienteId) return alert('Conecte-se primeiro.');

    const leilaoId = inputLeilaoIdInteracao.value;
    log('API (Cancelar)', { leilaoId, clienteId });
    try {
        const resultado = await cancelarInteresse(leilaoId,clienteId);
        log('API (Sucesso Cancelamento de Interesse)', resultado);
        alert('Interesse cancelado!');
    } catch (err) {
        log('API (Erro de Cancelamento)', err.message);
    }
};

btnConsultar.onclick= async function () {
    const divLeiloes = document.getElementById('leiloesAtivos'); 
    divLeiloes.innerHTML = "Buscando..."; 

    log('API (GET)', 'Consultando leilões ativos...');

    try {
        const listaLeiloes = await consultarLeiloes(); 
        
        log('API (Sucesso Consulta)', listaLeiloes);

        if (listaLeiloes.length === 0) {
            divLeiloes.innerHTML = "<p>Nenhum leilão ativo no momento.</p>";
            return;
        }

        divLeiloes.innerHTML = ""; 
        
        listaLeiloes.forEach(leilao => {
            const p = document.createElement('div');
            p.style.borderBottom = "1px solid #ccc";
            p.style.padding = "5px";
            p.style.marginBottom = "5px";
            
            const fim = new Date(leilao.hora_fim).toLocaleTimeString();

            p.innerHTML = `
                <strong>ID: ${leilao.id}</strong> - Produto: <b>${leilao.produto}</b> <br>
                Valor Inicial: R$ ${leilao.valor_inicial} | Termina às: ${fim}
            `;
            divLeiloes.appendChild(p);
        });
        
    } catch (err) {
        log('API (Erro de Consulta)', err.message);
        divLeiloes.innerHTML = "Erro ao consultar.";
    }
};
console.log("main.js e api.js carregados.");
