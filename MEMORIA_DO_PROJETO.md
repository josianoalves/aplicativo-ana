# Memória do Aplicativo Ana

## Objetivo

O Aplicativo Ana, chamado Radar Shopee AI na interface do projeto, ajuda a encontrar produtos na API de Afiliados da Shopee e a preparar material para divulgação. O painel roda no Windows, no endereço `http://127.0.0.1:8765`, e guarda o histórico em SQLite.

## Fluxos de trabalho

- **Vídeos para Shopee.** O Radar pesquisa, analisa e seleciona produtos, gera roteiros com variações e monta vídeos com clipes fornecidos pela usuária, narração e legendas. O painel gera um pacote para download. A publicação, a marcação do produto e o registro da comissão confirmada são feitos manualmente.
- **Resumo no WhatsApp.** Com o modo WhatsApp ativo, o Radar pesquisa as ofertas, ordena pela contagem de vendas e tenta enviar três links de afiliado via WhatsApp Business. Há um limite de uma tentativa de envio por dia. A aceitação pela API aparece no histórico, e a entrega pode ser conferida no WhatsApp.
- **Agendamento.** Os horários usam UTC−03:00. Para rodar no horário, mantenha o Radar aberto, o computador ligado e a conexão com a internet disponível.

## Como retomar o projeto

1. No Windows com Python 3.10 ou mais recente, execute `iniciar.bat`. O script prepara as dependências quando necessário e inicia o painel.
2. Use `configurar-chaves.bat` para preencher as integrações em `.env`, seguindo o modelo `.env.example`. A Shopee fornece o catálogo. A OpenAI é opcional para roteiros, o WhatsApp Business é usado para o resumo e o Azure Speech é uma opção de narração além da voz local do Windows.
3. Use **Configurações** para ajustar os horários e o fluxo. Consulte o [guia de instalação e operação](README.md) para configurar cada integração.

## Onde alterar

| Área | Arquivos |
| --- | --- |
| Painel e servidor local | `radar/static/` e `radar/server.py` |
| Catálogo e links de afiliado | `radar/shopee.py` |
| Pontuação e roteiros | `radar/analysis.py` |
| Execução e agendamento | `radar/pipeline.py` |
| Banco de dados e backup | `radar/store.py` |
| Renderização e narração | `radar/video.py` e `radar/azure_voice.py` |
| Envio pelo WhatsApp | `radar/whatsapp.py` |
| Testes automatizados | `tests/` |

Para rodar os testes no PowerShell após a instalação:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Dados locais e publicação no GitHub

O repositório deve conter o código, os testes, os scripts do Windows, a documentação e o modelo de configuração. As chaves reais ficam em `.env`. O banco, os clipes de produtos, os vídeos produzidos e os backups ficam em `dados/`. O ambiente virtual, as prévias, as páginas avulsas de demonstração e os pacotes locais também ficam fora do versionamento.

Para preservar o histórico em outra instalação, copie a pasta `dados/` com o Radar fechado nos dois computadores. Configure as credenciais no computador de destino.
