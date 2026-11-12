# Integração OfficeTrack: Envio de Link Externo com Retorno Automático no Mesmo Formulário

Este documento explica, em linguagem objetiva (com visão operacional e técnica), como funciona no **OfficeTrack** a arquitetura que permite:
1. Iniciar uma ação a partir de um formulário em campo;
2. Enviar um link para uma pessoa externa (cliente, gestor, recebedor) **sem que ela precise ter aplicativo ou login**;
3. Receber a resposta dessa pessoa **preenchida automaticamente de volta nos campos do mesmo formulário**.

---

## 1. O que essa arquitetura entrega na prática

Por padrão, um formulário móvel fica restrito a quem está com o aparelho em mãos. Com a integração via **Web Service + `OpenUrl` + Callback (`WebService`)**, o formulário passa a se comunicar com terceiros em tempo real mantendo os dados centralizados dentro da própria Ordem de Serviço (OS):

* **Zero redigitação:** o técnico não precisa copiar protocolos, digitar códigos manualmente nem tirar print de WhatsApp para provar o aceite.
* **Sem usuário ou app para o cliente final:** quem recebe o link abre uma página web segura direto no navegador do celular.
* **Retorno estruturado no formulário:** status, nome, documento, data/hora, observações e até imagem de assinatura voltam gravados como campos oficiais daquela tarefa no OfficeTrack (e podem ser impressos diretamente no PDF do **Report Designer**).
* **Trilha de auditoria:** cada transação gera protocolo único vinculado ao número da OS (`TaskNum`) e ao colaborador (`EmployeeNumber`), com registro de horário e IP de quem respondeu.

---

## 2. Como funciona o fluxo passo a passo

```text
[1] Técnico clica no botão do formulário (App OfficeTrack)
        │  envia XML com os dados da OS e do formulário
        ▼
[2] Servidor de Integração (Middleware)
        ├─ Cria sessão única (protocolo vinculado à OS)
        ├─ Dispara o link externo (ex.: WhatsApp / SMS / E-mail)
        └─ Devolve ao OfficeTrack:
             • <Action>OpenUrl</Action> (tela de acompanhamento em tempo real)
             • <WebService> (URL de retorno automático)
        │
        ├──────────────────────────────┐
        ▼                              ▼
[3A] Tela do Técnico (App)     [3B] Celular do Cliente/Gestor
  Exibe status em tempo real     Abre o link no navegador,
  e atualiza automaticamente     lê os dados da OS e envia a
  assim que o terceiro responde  resposta (ex.: aprova ou assina)
        │                              │
        └──────────┬───────────────────┘
                   ▼
[4] Técnico fecha a tela auxiliar no App
        │  OfficeTrack chama automaticamente a URL de <WebService>
        ▼
[5] Formulário atualizado na hora
    Os campos do mesmo formulário (Status, Nome, Horário, Link/Imagem)
    são preenchidos automaticamente sem perder os dados já digitados.
```

### Detalhamento de cada etapa

1. **Disparo dentro do formulário:**
   O técnico preenche os dados necessários na OS (por exemplo, nome e telefone do cliente ou resumo do serviço) e toca no botão configurado como *Web Service Call*.
2. **Criação da sessão e envio do link:**
   O servidor recebe os dados da OS em XML, gera um identificador único da solicitação (ex.: `TXID`), salva em banco de dados e envia a mensagem com o link exclusivo pelo canal integrado (como WhatsApp oficial/API).
3. **Acompanhamento em tempo real vs. Resposta externa:**
   * Na resposta dessa primeira chamada, o servidor instrui o aplicativo do técnico a abrir uma página de espera (`OpenUrl`) que verifica continuamente se o destinatário já respondeu.
   * No celular de quem recebeu o link, a página web mostra os dados resumidos daquela OS e coleta a ação esperada (aprovar/reprovar orçamento, preencher justificativa, assinar na tela, confirmar recebimento, etc.).
4. **Preenchimento automático no mesmo formulário:**
   Assim que a resposta é concluída, a tela de acompanhamento no aparelho do técnico exibe a confirmação. Quando o técnico fecha essa janela no aplicativo, o próprio OfficeTrack dispara automaticamente a chamada de retorno (`<WebService>`) registrada na etapa 2. O servidor devolve um XML `ResponseV2` contendo os valores exatos para cada campo do formulário.
5. **Contingência caso falte sinal ou a janela seja fechada antes:**
   O código de protocolo (`TXID`) também é gravado no formulário. Se o técnico fechar a tela antes de o cliente responder (ou precisar seguir para outra etapa e consultar depois), basta acionar o botão de consulta com esse protocolo para puxar o resultado assim que o cliente concluir.

---

## 3. O que é necessário no OfficeTrack e fora dele

### No OfficeTrack (Configuração do Formulário)
* **Campos de entrada:** os dados que serão enviados ao terceiro (ex.: telefone, nome, descrição, valor).
* **Botão *Web Service Call*:** apontando para a rota inicial do servidor (ex.: `POST /iniciar_...`).
* **Campos de saída:** os campos com os IDs esperados pelo retorno do servidor (ex.: status da resposta, nome de quem respondeu, data/hora, link de comprovante ou imagem).
* **Report Designer (opcional):** se houver retorno de link direto de imagem (ex.: assinatura digital em JPEG/PNG), o relatório PDF da OS pode renderizar a imagem diretamente pelo campo de link.

### No Servidor Intermediário (Middleware)
* Recebe o XML padrão do OfficeTrack e extrai `TaskNum`, `EmployeeNumber` e os `<Field>` do formulário.
* Mantém o estado da sessão (`AGUARDANDO` → `CONCLUIDO`) em banco de dados para garantir consistência e evitar respostas duplicadas.
* Hospeda a página web responsiva onde o usuário externo responde (compatível com qualquer navegador móvel, sem login).
* Integra com o canal de disparo (WhatsApp, e-mail, SMS ou API interna do cliente).
* Devolve o XML no padrão nativo do OfficeTrack (`<Action>OpenUrl</Action>` na abertura e `ResponseV2` em UTF-16 no retorno).

---

## 4. Casos de uso reais com essa mesma mecânica

* **Assinatura remota de cliente ausente:** o responsável pela obra ou pelo equipamento não está no local; recebe o link no WhatsApp, revisa o resumo da OS, assina na tela do próprio celular e a assinatura volta para o formulário e para o PDF final da OS.
* **Aprovação de orçamento ou serviço adicional:** o técnico identifica uma peça extra em campo; envia o valor para o aprovador (cliente ou supervisor), que aprova ou reprova pelo link com justificativa, liberando ou bloqueando a continuidade na própria OS.
* **Confirmação de entrega ou liberação de acesso:** recebedor, portaria ou fiscal valida o recebimento/liberação pelo link recebido e grava o aceite com data, hora e identificação diretamente no formulário.
* **Coleta de dados ou telas auxiliares interativas:** além de links enviados a terceiros, a mesma mecânica permite abrir telas web avançadas para o próprio técnico (catálogos extensos, preenchimento guiado, captura com anotação em foto) devolvendo o resultado estruturado para os campos do formulário.

---

## 5. Como explicar para o cliente em uma reunião (texto direto)

> *"O OfficeTrack permite que um botão dentro do formulário chame uma integração externa em tempo real. Quando o técnico toca nesse botão, o formulário envia os dados da OS para o nosso servidor, que cria um protocolo único e dispara um link seguro para o cliente ou gestor — por exemplo, no WhatsApp. A pessoa abre esse link direto no navegador do celular, sem precisar baixar aplicativo nem ter login, confere os dados e envia a confirmação ou assinatura. No mesmo instante, o aplicativo do técnico recebe essa resposta de volta e preenche automaticamente os campos daquele mesmo formulário e do relatório final em PDF, com data, hora e registro de auditoria."*

