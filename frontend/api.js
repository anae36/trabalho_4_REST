//Consome  O API GATEWAY.
const URL_BASE = 'http://localhost:3000';

export async function consultarLeiloes() {
  try {
    const response = await axios.get(`${URL_BASE}/leiloes`);
    return response.data;
  } catch (error) {
    console.error('Erro ao obter leiloes:', error);
    throw error;
  }
}

export async function criarLeilao(dadosLeilao) {
  try {
    const response = await axios.post(`${URL_BASE}/leiloes`, dadosLeilao);
    return response.data;
  } catch (error) {
    console.error('Erro ao criar leilao:', error);
    throw error;
  }
}

export async function efetuarLance(id_leilao, id_usuario, valor) {
  try {
    const response = await axios.post(`${URL_BASE}/lances`, { id_leilao, id_usuario, valor });
    return response.data;
  } catch (error) {
    console.error('Erro ao efetuar lance:', error);
    throw error;
  }
}

export async function registrarInteresse(id_leilao, id_usuario) {
  try {
    const response = await axios.post(`${URL_BASE}/notificacoes/${id_leilao}`, { id_usuario });
    return response.data;
  } catch (error) {
    console.error('Erro ao registrar interesse:', error);
    throw error;
  }
}

export async function cancelarInteresse(id_leilao,id_usuario) {
  try {
    const response = await axios.delete(`${URL_BASE}/notificacoes/${id_leilao}`, 
       { data: { id_usuario: id_usuario }});
    return response.data;
  } catch (error) {
    console.error('Erro ao cancelar interesse:', error);
  }
}
