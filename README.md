# RADAR SHOPEE AI

Aplicativo local para Windows com painel no Chrome e dados em SQLite. A pasta funciona em outro computador após a instalação das dependências.

Para retomar o desenvolvimento, consulte a [memória do projeto](MEMORIA_DO_PROJETO.md).

## Abrir neste computador

1. Dê dois cliques em **iniciar.bat**. A instalação inicial usa a internet para baixar o FFmpeg. Se o navegador não abrir, acesse http://127.0.0.1:8765.
2. Abra o [Portal da API de Afiliados da Shopee](https://affiliate.shopee.com.br/open_api) na sua conta para conferir a disponibilidade do App ID e Secret.
3. Dê dois cliques em **configurar-chaves.bat**, preencha `SHOPEE_APP_ID` e `SHOPEE_SECRET` no Bloco de Notas e salve. Feche a janela do Radar e execute **iniciar.bat** novamente. Mantenha o arquivo `.env` privado. O programa não pede sua senha da Shopee.
4. No painel, abra **Configurações**, defina os termos separados por vírgula, a quantidade de produtos, as variações e os horários. Sem termos, a busca usa a ordenação por vendas.
5. Clique em **Executar agora**. Veja o resultado em **Produtos selecionados**. Para cada produto que quiser promover, envie um clipe próprio ou autorizado, em MP4, MOV, M4V ou WEBM, na seção de vídeos. Rode novamente para renderizar duas ou três variações.
6. Em **Publicações**, baixe o ZIP do vídeo e transfira-o para o celular. Abra o Shopee Vídeo, use a legenda do pacote e marque o produto no app antes de publicar. Depois registre o identificador da publicação no painel. Quando a comissão estiver confirmada, registre o valor no mesmo painel. [Como vincular produtos no app](https://help.shopee.com.br/portal/10/article/165032)

## Usar em outro Windows

1. Extraia o ZIP para uma pasta que você possa editar, por exemplo Documentos.
2. Instale Python 3.10 ou mais recente e o Chrome. Para a narração, tenha uma voz brasileira SAPI instalada no Windows.
3. Abra **iniciar.bat**. Para recuperar o histórico, copie a pasta `dados` inteira com o Radar fechado nos dois computadores. Para usar a mesma conta, configure as chaves localmente pelo **configurar-chaves.bat**.
4. Para abrir automaticamente ao entrar no Windows, execute **inicio-windows.bat** e confirme. Rode o mesmo arquivo e escolha Não para remover o atalho. A rotina depende do computador ligado e fora da suspensão e do processo do Radar em execução.

O agendamento usa UTC−03:00. Os horários iniciais são 08:05 para pesquisa, 08:20 para análise, 08:30 para seleção, 08:40 para roteiros e 09:00 para vídeos. Os horários são os primeiros momentos em que cada etapa pode começar. Uma etapa que demore faz as seguintes começarem depois. Uma execução manual segue diretamente de uma etapa para outra.

## Fontes, mídia e comissões

- O catálogo usa a API oficial de afiliados. Dados que a API não devolve ficam vazios. Tendência compara o total de vendas retornado com a observação anterior. A nota usa vendas, avaliações, comissão, preço e os demais indicadores quando disponíveis. O painel mostra a cobertura das métricas. Potencial de conversão é uma estimativa da nota. O catálogo não fornece medição direta de concorrência.
- Os roteiros locais variam gancho e edição. Para gerar roteiros por IA, preencha `OPENAI_API_KEY` em `.env`. Essa opção envia à API o nome do produto e o número da variação. O modelo pode ser configurado em `RADAR_AI_MODEL`.
- O vídeo usa clipe autorizado, narração SAPI brasileira e legendas por cena. Para música, coloque uma única faixa autorizada na pasta `dados/musica`. Para usar uma voz SAPI brasileira específica, configure o nome em `RADAR_VOICE`. Em outro PC, se não houver voz brasileira, instale a voz e reinicie o Radar.
- O pacote contém vídeo, legenda e a referência ao produto e ao link de afiliado. O fluxo de publicação é manual no app Shopee. O link do pacote não substitui a marcação do produto no app. [FAQ oficial do Shopee Vídeo](https://help.shopee.com.br/portal/10/article/171162)
- A comissão estimada soma uma venda hipotética de cada produto selecionado pelo preço e taxa retornados. A comissão confirmada é registrada manualmente conforme os resultados da sua conta.
- O botão **Backup** copia o banco para `dados/backups`. Para preservar clipes e vídeos, copie também a pasta `dados` inteira. Proteja o computador com sua conta do Windows. O painel escuta apenas no próprio computador.

## Estrutura

- `radar/server.py` — servidor local, segurança do painel, envio de mídia, download e registro de resultados.
- `radar/store.py` — banco SQLite, histórico de produtos e backup.
- `radar/shopee.py` — catálogo e links de afiliado.
- `radar/analysis.py` — pontuação e roteiros.
- `radar/pipeline.py` — orquestração, repetição limitada, pausa e horários.
- `radar/video.py` — produção audiovisual no Windows.
- `radar/static/` — painel no navegador.
- `tests/` — testes automatizados.

Para rodar os testes depois da instalação, use `.venv\Scripts\python.exe -m unittest discover -s tests -v`. Os testes da API usam respostas controladas. Os testes de vídeo renderizam arquivos reais com FFmpeg e uma voz SAPI.

## Receber os três mais vendidos no WhatsApp

O modo WhatsApp consulta as ofertas gerais da API de afiliados e ordena pela contagem de vendas informada pela Shopee. Envia três links de afiliado em uma mensagem. Nesse modo, a etapa de vídeos é pulada e você pode editar os vídeos manualmente.

1. Configure um remetente na [plataforma oficial WhatsApp Business da Meta](https://developers.facebook.com/documentation/business-messaging/whatsapp/overview). Você precisa do ID do número remetente, de um token com permissão de mensagens e de um número de destino habilitado para receber.
2. No WhatsApp Manager, envie um modelo para aprovação em português do Brasil (pt_BR), com três variáveis posicionais no corpo e sem variáveis extras, botões ou mídia. Um exemplo de texto:

       Seu Radar Shopee encontrou estas três ofertas com mais vendas.
       1º lugar: {{1}}
       2º lugar: {{2}}
       3º lugar: {{3}}
       Abra os links para conferir os produtos.

   Use links Shopee como amostras para a aprovação. A Meta define a aprovação, a categoria e a tarifação. [Modelos de mensagem](https://developers.facebook.com/docs/whatsapp/business-management-api/guides)
3. Abra **configurar-chaves.bat**. Preserve as linhas da Shopee e adicione as linhas abaixo. Use o DDI e DDD no destino, só com dígitos.

       RADAR_MODO_WHATSAPP=1
       WHATSAPP_PHONE_ID=
       WHATSAPP_DESTINO=
       WHATSAPP_TOKEN=
       WHATSAPP_MODELO=radar_shopee_diario
       WHATSAPP_GRAPH_VERSION=v27.0

   Preencha os três valores em branco, use o nome exato do modelo aprovado, salve e reinicie pelo **iniciar.bat**. Guarde o token apenas no computador.
4. Em **Configurações**, defina o horário de **Pesquisa** (padrão 08:05 de Brasília/Fortaleza). Deixe o Radar aberto e conectado à internet. Se abrir o aplicativo após o horário, ele roda a pesquisa daquele dia ao iniciar. Se clicar em **Iniciar pesquisa**, o Radar tenta adiantar o envio do dia. O limite é uma tentativa de envio por dia para evitar duplicatas, inclusive quando a Meta demora a responder. Consulte **Histórico** para ver se a API aceitou a mensagem. Confirme a entrega no próprio WhatsApp.

## Narração com Francisca, Antônio e Thalita

O Radar gera uma versão por voz quando a narração Azure está ativa. A ordem é Francisca, Antônio e Thalita. Essas vozes são sintetizadas nos servidores da Microsoft. O Radar envia o texto de cada cena e recebe o áudio em WAV para montar o vídeo.

1. Crie um recurso Azure Speech em um plano que permita uso comercial (por exemplo, S0). A síntese pode gerar cobrança. [Termos da Microsoft](https://www.microsoft.com/licensing/terms/productoffering/MicrosoftAzure/MCA)
2. Abra **configurar-chaves.bat** e acrescente as linhas abaixo, preenchendo a chave e a região do recurso Speech. Use o identificador de região do portal Azure, por exemplo `eastus` se essa for a região do seu recurso.

       RADAR_NARRACAO=azure
       AZURE_SPEECH_KEY=
       AZURE_SPEECH_REGION=

3. Salve e reinicie o Radar pelo **iniciar.bat**. Com um clipe autorizado enviado, execute a pesquisa no modo de produção de vídeos. Se o modo exclusivamente WhatsApp estiver ativo, use `RADAR_MODO_WHATSAPP=0` para essa execução. Ao usar Azure, o Radar produz as três versões mesmo se a quantidade salva for duas. O nome de cada voz aparece junto ao vídeo no painel.
