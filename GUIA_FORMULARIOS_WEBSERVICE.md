# GUIA COMPLETO DE FORMULÁRIOS E WEB SERVICES OFFICETRACK

Este manual detalha como configurar cada formulário dentro do **Criador de Formulários do OfficeTrack**, listando os **IDs exatos**, as **rotas correspondentes** e o comportamento esperado no aplicativo móvel.

---

## 🌐 Endereço Base do Servidor
Nas configurações de cada botão Web Service Call no OfficeTrack, o endereço será:
* **Produção (Cloudflare Tunnel):** `https://seu-dominio.com/<NOME_DA_ROTA>`
* **Desenvolvimento Local:** `http://<SEU_IP_LOCAL>:5001/<NOME_DA_ROTA>`
* **Método HTTP:** Sempre **`POST`**
* **Parâmetro de envio:** Padrão (`Data` ou `TextXML`)

---

## 📋 Índice dos Serviços Disponíveis

1. [Consulta de CNPJ e Dados Cadastrais (`/consultar_cnpj`)](#1-consulta-de-cnpj-e-dados-cadastrais)
2. [Consulta e Identificação de Veículo por Placa (`/consultar_placa`)](#2-consulta-e-identificação-de-veículo-por-placa)
3. [Geração Automática de Laudo Técnico com IA (`/gerar_laudo_ia`)](#3-geração-automática-de-laudo-técnico-com-ia)
4. [Assistente Técnico de Diagnóstico de Falhas (`/diagnostico_ia`)](#4-assistente-técnico-de-diagnóstico-de-falhas)
5. [Calculadora Automática de Orçamento e Peças (`/calcular_orcamento`)](#5-calculadora-automática-de-orçamento-e-peças)
6. [Histórico de Manutenções do Equipamento (`/historico_equipamento`)](#6-histórico-de-manutenções-do-equipamento)
7. [Validação de Conformidade SESMT / NR (`/validar_conformidade_nr`)](#7-validação-de-conformidade-sesmt--nr)
8. [Disparo de Notificação WhatsApp (`/notificar_whatsapp`)](#8-disparo-de-notificação-whatsapp)
9. [Validador Universal de Duplicidade em Tabelas (`/validar_duplicidade`)](#9-validador-universal-de-duplicidade-em-tabelas)
10. [Aprovação / Preenchimento Externo em Tempo Real (`/iniciar_aprovacao_externa`)](#10-aprovação--preenchimento-externo-em-tempo-real)
11. [Chatbot Interativo GPT-4o-mini na Tela (`/iniciar_chat_ia`)](#11-chatbot-interativo-gpt-4o-mini-na-tela)
12. [Assinatura Digital à Distância com Link PNG para Report Designer (`/iniciar_assinatura_remota`)](#12-assinatura-digital-à-distância-com-link-png-para-report-designer)

---

## 1. Consulta de CNPJ e Dados Cadastrais

* **Rota:** `POST /consultar_cnpj`
* **Objetivo:** O técnico digita o CNPJ e o Web Service busca na Receita Federal preenchendo Razão Social, Fantasia, Situação e Endereço completo.

### Estrutura do Formulário no OfficeTrack:

| Tipo de Campo | Rótulo (Label) | ID do Campo (Exato) | Visível? | Função |
| :--- | :--- | :--- | :---: | :--- |
| **Texto / Número** | Digite o CNPJ | `CNPJ` | Sim | Entrada (com ou sem máscara) |
| **Web Service Call** | Consultar CNPJ | `BTN_CNPJ` | Sim | Dispara `POST /consultar_cnpj` |
| **Texto** | Razão Social | `RAZAO_SOCIAL` | Sim | Preenchido automaticamente |
| **Texto** | Nome Fantasia | `NOME_FANTASIA` | Sim | Preenchido automaticamente |
| **Texto** | Situação Cadastral | `SITUACAO` | Sim | Preenchido (Ativa, Inapta, etc.) |
| **Texto** | Logradouro | `LOGRADOURO` | Sim | Preenchido automaticamente |
| **Texto** | Número | `NUMERO` | Sim | Preenchido automaticamente |
| **Texto** | Bairro | `BAIRRO` | Sim | Preenchido automaticamente |
| **Texto** | Cidade | `CIDADE` | Sim | Preenchido automaticamente |
| **Texto** | Estado (UF) | `ESTADO` | Sim | Preenchido automaticamente |
| **Texto** | CEP | `CEP` | Sim | Preenchido automaticamente |
| **Texto / Telefone** | Telefone | `TELEFONE` | Sim | Preenchido automaticamente |

---

## 2. Consulta e Identificação de Veículo por Placa

* **Rota:** `POST /consultar_placa`
* **Objetivo:** Valida a placa (Mercosul ou antiga) e preenche marca, modelo, ano, cor e status da frota.

### Estrutura do Formulário no OfficeTrack:

| Tipo de Campo | Rótulo (Label) | ID do Campo (Exato) | Visível? | Função |
| :--- | :--- | :--- | :---: | :--- |
| **Texto** | Placa do Veículo | `PLACA` | Sim | Entrada (ex: ABC1234 ou ABC1D23) |
| **Web Service Call** | Validar Placa | `BTN_PLACA` | Sim | Dispara `POST /consultar_placa` |
| **Texto** | Marca | `MARCA` | Sim | Preenchido automaticamente |
| **Texto** | Modelo do Veículo | `MODELO` | Sim | Preenchido automaticamente |
| **Texto** | Ano Fabricação/Modelo | `ANO` | Sim | Preenchido automaticamente |
| **Texto** | Cor | `COR` | Sim | Preenchido automaticamente |
| **Texto** | Tipo | `TIPO_VEICULO` | Sim | Ex: Carga, Utilitário, Passeio |
| **Texto** | Status da Frota | `STATUS_VEICULO` | Sim | Ex: Regular / Ativo |

---

## 3. Geração Automática de Laudo Técnico com IA

* **Rota:** `POST /gerar_laudo_ia`
* **Objetivo:** A IA lê as anotações do técnico e as não conformidades de qualquer tabela do checklist, transformando tudo em um parecer técnico formal pronto para assinatura.

### Estrutura do Formulário no OfficeTrack:

| Tipo de Campo | Rótulo (Label) | ID do Campo (Exato) | Visível? | Função |
| :--- | :--- | :--- | :---: | :--- |
| **Área de Texto** | Observações do Técnico | `OBS_TECNICA` | Sim | Notas brutas ou transcrição de voz |
| **Tabela (Opcional)** | Checklist de Vistoria | Qualquer ID | Sim | Varre itens com "Não Conforme" |
| **Web Service Call** | Gerar Laudo Pericial com IA | `BTN_GERAR_LAUDO` | Sim | Dispara `POST /gerar_laudo_ia` |
| **Área de Texto** | Parecer Técnico Executivo | `LAUDO_FINAL` | Sim | Parecer pericial formal pela IA |
| **Área de Texto** | Ações Recomendadas | `RECOMENDACOES` | Sim | Ações corretivas sugeridas |

---

## 4. Assistente Técnico de Diagnóstico de Falhas

* **Rota:** `POST /diagnostico_ia`
* **Objetivo:** Guia o técnico no local informando possíveis causas raízes e os testes práticos com instrumentos para solucionar o defeito.

### Estrutura do Formulário no OfficeTrack:

| Tipo de Campo | Rótulo (Label) | ID do Campo (Exato) | Visível? | Função |
| :--- | :--- | :--- | :---: | :--- |
| **Texto** | Equipamento / Máquina | `EQUIPAMENTO` | Sim | Ex: Chiller, Bomba, Transformador |
| **Área de Texto** | Sintoma ou Defeito | `SINTOMA_DEFEITO` | Sim | Ex: Desarme por sobretemperatura |
| **Web Service Call** | Obter Diagnóstico de Falha | `BTN_DIAGNOSTICO` | Sim | Dispara `POST /diagnostico_ia` |
| **Área de Texto** | Prováveis Causas | `DIAGNOSTICO_SUGERIDO` | Sim | As 3 causas prováveis pela IA |
| **Área de Texto** | Procedimento de Testes | `PASSO_A_PASSO_TESTES` | Sim | Checklist de medições a fazer |

---

## 5. Calculadora Automática de Orçamento e Peças

* **Rota:** `POST /calcular_orcamento`
* **Objetivo:** Lê cada linha de uma tabela de peças/serviços, calcula o total da linha e totaliza o orçamento na tela com descontos.

### Estrutura do Formulário no OfficeTrack:

#### A. Tabela de Peças / Serviços (`TABELA_ITENS` ou qualquer ID de tabela):
Colunas da Tabela:
* Coluna 1: `ITEM` (Texto - Nome da peça ou serviço)
* Coluna 2: `QTD` (Número - Quantidade aplicada)
* Coluna 3: `VALOR_UNIT` (Número ou Moeda - Preço unitário)
* Coluna 4: `VALOR_TOTAL_ITEM` (Número ou Moeda - Calculado automaticamente)

#### B. Campos Gerais no Formulário:

| Tipo de Campo | Rótulo (Label) | ID do Campo (Exato) | Visível? | Função |
| :--- | :--- | :--- | :---: | :--- |
| **Moeda / Número** | Desconto Aplicado (R$) | `DESCONTO` | Sim | Opcional (ex: 50,00) |
| **Web Service Call** | Calcular Orçamento | `BTN_CALCULAR` | Sim | Dispara `POST /calcular_orcamento` |
| **Texto / Moeda** | Subtotal dos Itens | `SUBTOTAL` | Sim | Preenchido automaticamente |
| **Texto / Moeda** | Total Geral a Pagar | `VALOR_TOTAL_GERAL` | Sim | Preenchido automaticamente |
| **Número** | Quantidade Total de Peças | `TOTAL_ITENS` | Sim | Quantidade somada de peças |

---

## 6. Histórico de Manutenções do Equipamento

* **Rota:** `POST /historico_equipamento`
* **Objetivo:** O técnico escaneia o QR Code ou digita o código do equipamento e o Web Service carrega na hora uma tabela com as últimas manutenções feitas naquele ativo.

### Estrutura do Formulário no OfficeTrack:

#### A. Campos de Entrada e Cabeçalho:

| Tipo de Campo | Rótulo (Label) | ID do Campo (Exato) | Visível? | Função |
| :--- | :--- | :--- | :---: | :--- |
| **Texto / Código de Barras** | Código do Ativo / Serial | `COD_EQUIPAMENTO` | Sim | Entrada (ou leitor de QR Code) |
| **Web Service Call** | Puxar Histórico | `BTN_HISTORICO` | Sim | Dispara `POST /historico_equipamento` |
| **Texto** | Fabricante | `FABRICANTE` | Sim | Preenchido automaticamente |
| **Texto** | Modelo do Ativo | `MODELO_EQUIPAMENTO` | Sim | Preenchido automaticamente |
| **Texto** | Status da Garantia | `STATUS_GARANTIA` | Sim | Preenchido automaticamente |
| **Texto** | Data da Última Revisão | `ULTIMA_REVISAO` | Sim | Preenchido automaticamente |

#### B. Tabela de Histórico (ID obrigatório: `TAB_HISTORICO`):
Crie uma tabela com o ID exato **`TAB_HISTORICO`** e as seguintes colunas:
* Coluna 1: `DATA` (Data da intervenção)
* Coluna 2: `TECNICO` (Nome do responsável)
* Coluna 3: `SERVICO` (Descrição do reparo realizado)
* Coluna 4: `STATUS` (Status do reparo)

---

## 7. Validação de Conformidade SESMT / NR

* **Rota:** `POST /validar_conformidade_nr`
* **Objetivo:** Antes de liberar um trabalho de risco (Altura, Eletricidade, Espaço Confinado), valida se o ASO e os certificados de NR do técnico estão válidos no sistema.

### Estrutura do Formulário no OfficeTrack:

| Tipo de Campo | Rótulo (Label) | ID do Campo (Exato) | Visível? | Função |
| :--- | :--- | :--- | :---: | :--- |
| **Lista de Seleção** | Tipo de Atividade | `TIPO_SERVICO` | Sim | Opções: `ALTURA / NR-35`, `ELETRICA / NR-10`, `ESPACO CONFINADO / NR-33`, `GERAL` |
| **Web Service Call** | Validar Liberação SESMT | `BTN_SESMT` | Sim | Dispara `POST /validar_conformidade_nr` |
| **Texto** | Status da Liberação | `STATUS_LIBERACAO` | Sim | `LIBERADO` ou `BLOQUEADO` |
| **Texto** | Validade do ASO | `VALIDADE_ASO` | Sim | Preenchido automaticamente |
| **Texto** | Certificação NR | `CERTIFICADO_NR` | Sim | Situação do treinamento |
| **Área de Texto** | Parecer do SESMT | `MENSAGEM_SESMT` | Sim | Instruções de segurança |

> **Comportamento:** Se a certificação estiver vencida, o botão fica `BLOQUEADO` e abre um pop-up de alerta crítico proibindo o início do trabalho até a regularização!

---

## 8. Disparo de Notificação WhatsApp

* **Rota:** `POST /notificar_whatsapp`
* **Objetivo:** Dispara mensagem instantânea no WhatsApp do cliente informando que a OS foi concluída, com resumo do atendimento.

### Estrutura do Formulário no OfficeTrack:

| Tipo de Campo | Rótulo (Label) | ID do Campo (Exato) | Visível? | Função |
| :--- | :--- | :--- | :---: | :--- |
| **Telefone** | WhatsApp do Cliente | `TEL_CLIENTE` | Sim | Número com DDD (ex: 11999998888) |
| **Texto** | Nome do Cliente | `NOME_CLIENTE` | Sim | Nome para saudação personalizada |
| **Área de Texto** | Resumo do Serviço | `RESUMO_SERVICO` | Sim | O que foi feito na OS |
| **Web Service Call** | Enviar WhatsApp ao Cliente | `BTN_NOTIFICAR` | Sim | Dispara `POST /notificar_whatsapp` |
| **Texto** | Status do Envio | `STATUS_WHATSAPP` | Sim | `ENVIADO COM SUCESSO` ou `FALHA` |
| **Texto** | Data e Hora do Envio | `DATA_HORA_ENVIO` | Sim | Registro de auditoria |
| **Texto** | Comprovante de Entrega | `COMPROVANTE_ENVIO` | Sim | Número de destino registrado |

---

## 9. Validador Universal de Duplicidade em Tabelas

* **Rota:** `POST /validar_duplicidade`
* **Objetivo:** Verifica se o técnico repetiu itens na tabela (ex: mesmo extintor, hidrante, número de patrimônio ou equipamento).

### Estrutura do Formulário no OfficeTrack:

#### A. Em qualquer Tabela do formulário:
* Uma das colunas deve obrigatoriamente ter o ID: **`IDLOCAL`** (ou `LOCAL`).
* O ID da tabela pode ser **qualquer um** (`TABEXSTINTORES`, `TAB_HIDRANTES`, `ITENS`, etc.).

#### B. Campos fora da Tabela:

| Tipo de Campo | Rótulo (Label) | ID do Campo (Exato) | Visível? | Função |
| :--- | :--- | :--- | :---: | :--- |
| **Web Service Call** | Validar Duplicidade | `BTN_VALIDAR` | Sim | Dispara `POST /validar_duplicidade` |
| **Texto** | Retorno da Validação | `RETORNO` | Não (Oculto) | Recebe `OK` ou `NOK` |

---

## 10. Aprovação Executiva / Preenchimento Externo em Tempo Real

* **Rota Principal (Botão):** `POST /iniciar_aprovacao_externa`
* **Rota de Fallback (Opcional):** `POST /consultar_aprovacao_manual`
* **Objetivo:** O técnico solicita aprovação ou validação de uma pessoa remota (supervisor ou cliente). O webservice monta automaticamente um **Laudo Executivo Completo** no navegador do aprovador:
  - Resumo contextual: Cliente, Endereço/Unidade, Equipamento/Série e Técnico responsável.
  - Laudo Técnico: Defeito constatado vs. Serviço executado e observações técnicas.
  - Tabela de Peças e Itens: Lista de peças/serviços com quantidades, valores unitários e totais.
  - Resumo financeiro: Subtotal, desconto e valor total autorizado.
  - Galeria de fotos/evidências (se houver fotos antes/depois).
  - Assinatura digital com trilha de auditoria: Botões de aprovação e reprovação (com justificativa obrigatória), nome e cargo/documento.
  - Disparo automático de WhatsApp executivo formatado via Evolution API.
  - Quando o técnico fecha a Sala de Espera no app (`OpenUrl`), o OfficeTrack importa automaticamente a decisão, aprovador, cargo, parecer e valor para o formulário!

### Estrutura do Formulário no OfficeTrack:

| Tipo de Campo | Rótulo (Label) | ID do Campo (Exato) | Visível? | Função |
| :--- | :--- | :--- | :---: | :--- |
| **Texto** | Nome do Cliente / Local | `CLIENTE` ou `NOME_CLIENTE` | Sim | Nome da empresa ou cliente |
| **Texto** | Equipamento / Ativo | `EQUIPAMENTO` | Sim | Nome ou tag da máquina/sistema |
| **Texto** | Número de Série | `NUMERO_SERIE` | Sim | Serial / Tag do ativo (opcional) |
| **Área de Texto** | Defeito Constatado | `DEFEITO_CONSTATADO` | Sim | Problema/sintoma verificado pelo técnico |
| **Área de Texto** | Serviço Executado | `SERVICO_EXECUTADO` | Sim | Resumo do trabalho realizado |
| **Tabela Dinâmica** | Tabela de Peças / Itens | `TABELA_PECAS` ou `TABELA_ITENS` | Sim | Itens com colunas: `ITEM`, `QTD`, `VALOR_UNIT`, `TOTAL` |
| **Numérico/Moeda** | Valor Total | `VALOR_TOTAL` | Sim | Total da OS autorizado |
| **Texto** | Nome do Aprovador | `NOME_APROVADOR` | Sim | Nome de quem vai aprovar |
| **Telefone** | WhatsApp do Aprovador | `TEL_APROVADOR` | Sim | Número com DDD (ex: 11999998888) |
| **Web Service Call** | Solicitar Aprovação Externa | `BTN_APROVACAO` | Sim | Dispara `POST /iniciar_aprovacao_externa` |
| **Texto** | Protocolo da Sessão | `TXID_EXTERNO` | Não/Sim | Preenchido automaticamente (ex: `CF3320CE`) |
| **Texto** | Decisão / Status | `STATUS_EXTERNO` | Sim | `APROVADO`, `REPROVADO` ou `AGUARDANDO RESPOSTA` |
| **Texto** | Aprovado Por | `NOME_APROVADOR_EXT` | Sim | Nome digitado no laudo |
| **Texto** | Cargo / Documento | `CARGO_APROVADOR_EXT` | Sim | Cargo, CPF ou matrícula do aprovador |
| **Área de Texto** | Parecer / Justificativa | `OBS_EXTERNA` | Sim | Parecer de liberação ou motivo da reprovação |
| **Texto** | Valor Aprovado | `VALOR_APROVADO_EXT` | Sim | Valor total aprovado |
| **Texto** | Data/Hora Confirmação | `DATA_HORA_EXT` | Sim | Carimbo de data e hora da resposta |
| **Web Service Call** | Buscar Resposta (Opcional) | `BTN_CONSULTAR` | Sim | Caso feche antes, dispara `POST /consultar_aprovacao_manual` |

---

## 11. Chatbot Interativo GPT-4o-mini na Tela

* **Rota do Botão:** `POST /iniciar_chat_ia`
* **Variável de Ambiente Obrigatória (Render / Docker):** `OPENAI_API_KEY` (e opcional `OPENAI_MODEL=gpt-4o-mini`).
* **Objetivo:** Abre uma interface real de Chat estilo ChatGPT dentro do app OfficeTrack (`OpenUrl`). A IA já recebe automaticamente o contexto dos campos preenchidos no formulário, conversa livremente com o técnico e, ao fechar o chat, envia o resumo e o histórico da conversa direto para o formulário!

### Estrutura do Formulário no OfficeTrack:

| Tipo de Campo | Rótulo (Label) | ID do Campo (Exato) | Visível? | Função |
| :--- | :--- | :--- | :---: | :--- |
| **Web Service Call** | Abrir Assistente IA | `BTN_CHAT` | Sim | Tipo: **Preencher Form** • Rota: `POST /iniciar_chat_ia` |
| **Texto** | Código da Sessão Chat | `CHAT_ID` | Não (Oculto) | Preenchido automaticamente |
| **Área de Texto** | Parecer / Resumo da IA | `CHAT_RESUMO_IA` | Sim | Resumo ou última orientação gerada pela IA |
| **Área de Texto** | Histórico da Conversa | `CHAT_HISTORICO_IA` | Sim/Não | Transcrição completa do chat |

---

## 12. Assinatura Digital à Distância com Link PNG para Report Designer

* **Rota Principal (Botão):** `POST /iniciar_assinatura_remota`
* **Rota de Fallback (Opcional):** `POST /consultar_assinatura_manual`
* **Objetivo:** Envia um link para o cliente revisar o serviço e assinar com o dedo no quadro Canvas do navegador. O servidor salva a assinatura como uma **imagem PNG real** e devolve o **link direto da imagem (`.../assinatura_img/TXID.png`)** para o campo de texto do formulário — que você pode vincular direto no componente de **Foto/Imagem do Report Designer**!

### Estrutura do Formulário no OfficeTrack:

| Tipo de Campo | Rótulo (Label) | ID do Campo (Exato) | Visível? | Função |
| :--- | :--- | :--- | :---: | :--- |
| **Texto** | Nome do Cliente | `NOME_CLIENTE` | Sim | Nome de quem vai assinar |
| **Telefone** | WhatsApp do Cliente | `TEL_CLIENTE` | Sim | Número com DDD |
| **Área de Texto** | Resumo do Serviço | `RESUMO_SERVICO` | Sim | O cliente vê isso antes de assinar |
| **Web Service Call** | Coletar Assinatura Remota | `BTN_ASSINATURA` | Sim | Tipo: **Preencher Form** • Rota: `POST /iniciar_assinatura_remota` |
| **Texto** | Protocolo Assinatura | `TXID_ASSINATURA` | Não (Oculto) | Código da sessão |
| **Texto** | Status da Assinatura | `STATUS_ASSINATURA` | Sim | `ASSINADO DIGITALMENTE` ou `AGUARDANDO` |
| **Texto** | Nome do Assinante | `ASSINANTE_NOME` | Sim | Nome digitado pelo cliente |
| **Texto** | CPF / Documento | `ASSINANTE_DOC` | Sim | Documento digitado pelo cliente |
| **Texto** | Link Direto da Imagem PNG | `LINK_ASSINATURA` | Sim/Não | URL `.../assinatura_img/TXID.png` (**Vincular no Report Designer!**) |
| **Texto** | Link do Comprovante Completo | `LINK_COMPROVANTE` | Sim/Não | Página com assinatura + IP + Data + Hash |
| **Texto** | Hash de Auditoria | `HASH_AUDITORIA` | Não/Sim | Hash SHA-256 + Data/Hora + IP |
| **Web Service Call** | Consultar Assinatura (Opcional) | `BTN_CONSULTA_ASSIN` | Sim | Caso feche antes, dispara `POST /consultar_assinatura_manual` |

---

## 13. Roleta da Sorte e Raspadinha Gamificada

* **Rota de Início:** `POST /iniciar_premio`
* **Rota de Consulta Manual:** `POST /consultar_premio_manual`
* **Objetivo:** Abre roleta ou raspadinha para o técnico ao concluir uma meta ou OS.

### Estrutura do Formulário no OfficeTrack:

| Tipo de Campo | Rótulo (Label) | ID do Campo (Exato) | Visível? | Função |
| :--- | :--- | :--- | :---: | :--- |
| **Web Service Call** | Rodar Prêmio | `BTN_PREMIO` | Sim | Dispara `POST /iniciar_premio` |
| **Texto** | Prêmio Ganho | `PREMIO_GANHO` | Sim | Preenchido automaticamente com o prêmio |
| **Texto** | Código do Voucher | `CODIGO_VOUCHER` | Sim | Código único do voucher para resgate |
| **Texto** | XP Ganho | `XP_GANHO` | Sim | Pontos conquistados na rodada |
| **Texto** | XP Total | `XP_TOTAL` | Sim | Acumulado do técnico |
| **Texto** | Nível | `NIVEL_TECNICO` | Sim | Bronze, Prata, Ouro ou Diamante |
| **Texto** | Modo Jogado | `MODO_JOGO` | Não/Sim | `ROLETA` ou `RASPADINHA` |
| **Texto** | Protocolo Prêmio | `TXID_PREMIO` | Não | ID da sessão |
| **Web Service Call** | Consultar Prêmio (Opcional) | `BTN_CONSULTA_PREMIO` | Sim | Caso feche antes, dispara `POST /consultar_premio_manual` |

---

## 14. Dashboard Visual da Tabela Dinâmica de Manutenção

* **Rota de Início:** `POST /iniciar_dashboard_tabela`
* **Rota de Consulta Manual:** `POST /consultar_dashboard_manual`
* **Objetivo:** O técnico adiciona N linhas na Tabela Dinâmica (equipamento, sistema, tipo de manutenção, status e custo/obs). O botão fora da tabela lê todas as linhas e abre um Dashboard executivo mobile com gráfico Donut, barras por sistema, cartões de KPI e lista filtrável, preenchendo o resumo na OS ao fechar.

### Estrutura da Tabela Dinâmica (ID sugerido: `TABELA_EQUIPAMENTOS`):

| Tipo de Campo | Rótulo (Label) | ID da Coluna (Exato) | Observação |
| :--- | :--- | :--- | :--- |
| **Lista / Texto** | Equipamento / Ativo | `EQUIPAMENTO` | Ex.: Ar Condicionado, Gerador, Bomba, etc. |
| **Lista / Texto** | Sistema / Setor | `SISTEMA` | Ex.: Climatização, Elétrica, Hidráulica |
| **Lista / Texto** | Tipo de Manutenção | `MANUTENCAO` | Ex.: Preventiva, Corretiva, Calibração, Limpeza |
| **Lista / Texto** | Status / Condição | `STATUS` | `Operacional` (Verde), `Atenção` (Amarelo) ou `Crítico` (Vermelho) |
| **Número / Decimal** | Custo Estimado | `CUSTO` | Opcional (valor do reparo ou peças) |
| **Texto** | Observações / Defeito | `OBS` | Opcional (detalhes da avaria) |

### Campos Fora da Tabela (no formulário principal):

| Tipo de Campo | Rótulo (Label) | ID do Campo (Exato) | Visível? | Função |
| :--- | :--- | :--- | :---: | :--- |
| **Web Service Call** | 📊 Gerar Dashboard | `BTN_GERAR_DASH` | Sim | Dispara `POST /iniciar_dashboard_tabela` |
| **Texto / Número** | Total de Ativos | `TOTAL_EQUIPAMENTOS` | Sim | Quantidade de linhas levantadas |
| **Texto** | Índice de Saúde | `INDICE_SAUDE` | Sim | Percentual de conformidade geral (ex: 85%) |
| **Texto** | Status do Parque | `STATUS_GERAL_PARQUE` | Sim | `PARQUE SAUDÁVEL`, `ATENÇÃO REQUERIDA` ou `RISCO OPERACIONAL` |
| **Texto / Número** | Operacionais | `TOTAL_OPERACIONAIS` | Sim | Quantidade de ativos OK |
| **Texto / Número** | Em Atenção | `TOTAL_ATENCAO` | Sim | Quantidade de ativos em alerta |
| **Texto / Número** | Críticos | `TOTAL_CRITICOS` | Sim | Quantidade de ativos parados |
| **Texto** | Custo Total Estimado | `CUSTO_TOTAL_MANUTENCAO` | Sim | Somatório dos custos informados |
| **Texto** | Sistema Mais Afetado | `SISTEMA_MAIS_CRITICO` | Sim | Sistema com mais itens com problema |
| **Texto** | Protocolo Dashboard | `TXID_DASHBOARD` | Não | ID da sessão |
| **Web Service Call** | Recarregar Dashboard | `BTN_CONSULTA_DASH` | Não/Sim | Opcional: dispara `POST /consultar_dashboard_manual` |

---

## 15. Validação de Crachá e Liberação Condicional do Formulário

* **Opção A (Câmera com Leitor QR Code OpenUrl):** `POST /iniciar_scanner_cracha` *(Abre a câmera do celular com mira de scanner e lê automaticamente ao apontar pro crachá)*
* **Opção B (Modo Direto via Digitação/Leitor de Barcode):** `POST /validar_cracha`
* **Objetivo:** O técnico escaneia com a câmera ou digita o código do crachá. O Web Service valida a credencial no banco de autorizados: se estiver ativo, devolve `FLAG_LIBERACAO = 1` e preenche nome, cargo, empresa e nível de acesso. Se estiver inativo, bloqueado ou inexistente, devolve `FLAG_LIBERACAO = 0` e emite alerta de bloqueio impeditivo.

### Estrutura do Formulário no OfficeTrack:

| Tipo de Campo | Rótulo (Label) | ID do Campo (Exato) | Visível? | Função |
| :--- | :--- | :--- | :---: | :--- |
| **Web Service Call (Recomendado)** | 📷 Escanear Crachá (Câmera) | `BTN_SCANNER_CRACHA` | Sim | **Abre o Leitor de QR Code na tela via Câmera** (`POST /iniciar_scanner_cracha`) |
| **Texto / Barcode** | Código do Crachá | `COD_CRACHA` | Sim | Preenchido automaticamente pelo scanner ou digitado manual |
| **Web Service Call (Opcional)** | Validar Crachá (Direto) | `BTN_VALIDAR_CRACHA` | Não/Sim | Valida o código digitado sem abrir câmera (`POST /validar_cracha`) |
| **Texto / Check** | Flag Liberação | `FLAG_LIBERACAO` | Não (Oculto) | **`1` (Liberado) ou `0` (Bloqueado)** — **Use nas regras de visibilidade das outras seções!** |
| **Texto** | Status da Autorização | `STATUS_AUTORIZACAO` | Sim | `AUTORIZADO`, `BLOQUEADO` ou `NÃO AUTORIZADO` |
| **Texto** | Nome do Titular | `NOME_AUTORIZADO` | Sim | Preenchido automaticamente com o nome |
| **Texto** | Cargo / Função | `CARGO_AUTORIZADO` | Sim | Especialidade do titular |
| **Texto** | Empresa | `EMPRESA_AUTORIZADO` | Sim | Prestadora ou setor interno |
| **Texto** | Nível de Acesso | `NIVEL_ACESSO` | Sim | Nível de permissão (ex.: Nível 4 - Total) |
| **Texto** | Áreas Permitidas | `AREAS_PERMITIDAS` | Sim/Não | Subestações, CPD, Climatização, etc. |
| **Texto** | Validade | `VALIDADE_CRACHA` | Sim | Data de validade da credencial |
| **Texto** | Mensagem / Motivo | `MOTIVO_BLOQUEIO` | Não/Sim | Motivo caso ocorra recusa |
| **Texto** | Link Crachá Digital | `LINK_CRACHA_DIGITAL` | Sim/Não | URL da credencial digital com foto |

---

## 💡 Dicas de Boas Práticas no OfficeTrack

1. **Maiúsculas e Minúsculas:** Os IDs no criador de formulários do OfficeTrack são sensíveis ao caso em algumas versões. Recomendamos criar os IDs exatamente como constam neste guia (em maiúsculas).
2. **Campos de Controle Ocultos:** Campos como `RETORNO`, `STATUS_LIBERACAO` ou flags de auditoria podem ser colocados como `IsVisible = Não` no formulário para não poluir a tela do técnico.
3. **Reset com Lixeira:** Quando um serviço retornar erro (`NOK` ou `BLOQUEADO`), o app OfficeTrack exibirá o ícone de lixeira ao lado do botão. O operador deve tocar na lixeira para resetar o botão após corrigir as informações na tela.

