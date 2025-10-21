// erroooooo fataaaaaaaal

let leiloes = [];
let proximoIdLeilao = 0;
const hora_atual=Date.now()

const consultarLeiloes = (req, res) => {
  if(hora_inicio>hora_atual){
    res.json(leiloes); 
  }
  
};
const criarLeilao = (req, res) => {
    const { produto, descricao, valor_incial, hora_inicio, hora_fim } = req.body;  
    const novoLeilao = {
        id: proximoIdLeilao++,
        produto,
        descricao: descricao || '',
        valor_incial,
        hora_inicio,
        hora_fim,
        status: 'Pendente'};
  leiloes.push(novoLeilao); 
  res.status(201).json(novoLeilao); 
};

module.exports = { consultarLeiloes, criarLeilao};