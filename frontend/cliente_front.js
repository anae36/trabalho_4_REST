const axios = require('axios');
const URL_BASE = 'http://localhost:3000/api';
async function consultarLeiloes() {
  try {
    const response = await axios.get(`${URL_BASE}/leiloes`);
    return response.data;
  } catch (error) {
    console.error('Erro ao obter leiloes:', error);
  }
}
async function criarLeilao(produto, descricao, valor_incial,hora_inicio, hora_fim) {
  try {
    const response = await axios.post(`${URL_BASE}/leiloes`, { produto, descricao, valor_incial,hora_inicio, hora_fim });
    return response.data;
  } catch (error) {
    console.error('Erro ao criar leilao:', error);
  }
}
//Ver como pegar o id do cliente
async function efetuarLance(id_leilao, valor) {
  try {
    const response = await axios.post(`${URL_BASE}/lances`, { id_leilao,valor});
    return response.data;
  } catch (error) {
    console.error('Erro ao efetuar lance:', error);
  }
}
async function registrarInteresse(id_leilao) {
  try {
    const response = await axios.post(`${URL_BASE}/notificacoes/${id_leilao}`, { id_leilao});
    return response.data;
  } catch (error) {
    console.error('Erro ao registrar interesse:', error);
  }
}
async function cancelarInteresse(id_leilao) {
  try {
    const response = await axios.delete(`${URL_BASE}/notificacoes/${id_leilao}`);
    return response.data;
  } catch (error) {
    console.error('Erro ao cancelar interesse:', error);
  }
}
module.exports = { consultarLeiloes, criarLeilao, efetuarLance, registrarInteresse,cancelarInteresse };