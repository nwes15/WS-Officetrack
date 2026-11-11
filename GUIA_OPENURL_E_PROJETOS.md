# GUIA DEFINITIVO DO `<Action>OpenUrl</Action>` NO OFFICETRACK
### Arquitetura de Retorno Automático, Sala de Espera e Projetos Avançados

Este documento explica como funciona o recurso mais poderoso e pouco explorado do **OfficeTrack** (documentado nas **páginas 167 e 171** do manual oficial `api-reference.pdf`) e lista **10 projetos reais e ousados** que podem ser construídos com essa tecnologia.

---

## 1. Como funciona a "Mágica" do OpenUrl (Sem precisar clicar em Consultar!)

Muitos desenvolvedores acham que o Web Service do OfficeTrack só consegue devolver texto ou preencher campos de forma síncrona (em poucos segundos). Porém, o próprio aplicativo do OfficeTrack possui um motor de **fluxo em duas etapas com WebView**:

```
[1. Técnico clica no botão do Form]
               │
               ▼
[2. Middleware responde com <Action>OpenUrl</Action>]
   Contendo DUAS URLs:
   • <Url>        ➔ A página web que vai abrir na tela do celular
   • <WebService> ➔ A URL secreta que o app vai chamar SOZINHO ao fechar a página
               │
               ▼
[3. App abre a tela <Url> (Sala de Espera / Página Interativa)]
   • O app NÃO dá timeout enquanto essa janela está aberta!
   • A tela pode esperar 10 segundos, 5 minutos ou interagir com terceiros.
   • Quando a pessoa externa responde (ex: via WhatsApp), a tela atualiza
     sozinha em tempo real (polling/WebSocket) e fica VERDE: "Concluído!".
               │
               ▼
[4. Técnico fecha a janela (botão X ou Voltar)]
               │
               ▼
[5. GATILHO AUTOMÁTICO DO OFFICETRACK]
   Assim que a página fecha, o OfficeTrack dispara AUTOMATICAMENTE um HTTP POST
   para a URL que estava na tag <WebService> (/finalizar_aprovacao/<tx_id>)!
               │
               ▼
[6. Preenchimento Direto no Formulário]
   O servidor lê o resultado salvo e responde em ResponseV2 (UTF-16),
   preenchendo todos os campos e tabelas dentro do formulário sozinho!
```

### E para que serve o botão de consulta manual (`/consultar_aprovacao_manual`)?
Ele é **apenas um Plano B de segurança**:
* **Se o técnico deixar a janela aberta** até ficar verde e depois fechar ➔ **NÃO precisa de botão consultar!** O próprio OfficeTrack puxa tudo sozinho na hora que a janela fecha.
* **Se o técnico fechar a janela antes da pessoa responder** (ex: fechou sem querer enquanto a pessoa ainda ia abrir o WhatsApp) ➔ A sessão fica salva com o código `TXID_EXTERNO`. Depois que o cliente responder, o técnico pode usar o botão manual para buscar aquele código sem perder o atendimento.

---

## 2. Estrutura XML Exata Exigida pelo OfficeTrack

### Resposta do Passo 1 (Para abrir a tela no app):
```xml
<?xml version="1.0" encoding="utf-8"?>
<Response>
    <ReturnValue>
        <ShortText>Aguardando</ShortText>
        <LongText>Sessão C17D8C4A</LongText>
        <Value>OK</Value>
        <Action>OpenUrl</Action>
        <Url>https://seu-dominio.com/espera/C17D8C4A</Url>
        <WebService>https://seu-dominio.com/finalizar_aprovacao/C17D8C4A</WebService>
    </ReturnValue>
</Response>
```

### Resposta do Passo 2 (Quando o técnico fecha a janela e o app chama `<WebService>`):
```xml
<?xml version="1.0" encoding="utf-16"?>
<ResponseV2 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
    <MessageV2>
        <Text>Retorno Externo Recebido com Sucesso!</Text>
    </MessageV2>
    <ReturnValueV2>
        <Fields>
            <Field><ID>STATUS_EXTERNO</ID><Value>APROVADO</Value></Field>
            <Field><ID>NOME_APROVADOR_EXT</ID><Value>Carlos Gerente</Value></Field>
            <Field><ID>OBS_EXTERNA</ID><Value>Autorizado!</Value></Field>
        </Fields>
        <ShortText>APROVADO</ShortText>
        <Value>1</Value>
    </ReturnValueV2>
</ResponseV2>
```

> **Dica de Configuração no Portal OfficeTrack:** Configure o botão Web Service Call como **"Validação de dados e preenchimento de formulário"** (*Preencher Form*). Isso garante que ele aceite o `<Action>OpenUrl</Action>` na ida e preencha os campos do `ResponseV2` na volta!

---

## 3. Sobre a Automação via WhatsApp (Evolution Go)

No código em [`apps/aprovacao_externa.py`](file:///home/wesley-novais/WS-Officetrack/apps/aprovacao_externa.py), o envio automático já está integrado via API (`POST /send/text` no Evolution Go).
* Quando a instância do WhatsApp (`Agent_EM`) está conectada (`connected: true`), no exato milissegundo em que o técnico aperta o botão no OfficeTrack, **o próprio servidor já manda a mensagem no WhatsApp do cliente/supervisor** — o técnico não precisa copiar link nem sair do aplicativo!
* Caso a instância esteja desconectada ou sem número preenchido, a própria Sala de Espera exibe o botão verde de backup (`📲 Enviar Link via WhatsApp`) e o botão `📋 Copiar Link`.

---

## 4. 🚀 10 Projetos Incríveis que Conseguimos Fazer com Esse Recurso

Como a tag `<Url>` abre uma página HTML5/JavaScript moderna e interativa dentro do celular, nós eliminamos as limitações visuais do formulário padrão e conseguimos criar soluções de nível enterprise:

### 1. Aprovação Remota em Tempo Real (Alçada e Orçamentos)
* **Uso:** Técnico precisa aprovar troca de peça cara, hora extra ou desconto fora da alçada.
* **Fluxo:** Envia o link pro WhatsApp do supervisor ➔ Sala de Espera aguarda em tempo real ➔ Supervisor aprova no celular dele ➔ Ao fechar, o form do técnico recebe `STATUS = APROVADO` e `LIMITE_LIBERADO`.

### 2. Cobrança por PIX na Hora com Baixa Automática
* **Uso:** Manutenção ou entrega com pagamento na entrega (COD).
* **Fluxo:** O botão gera um **QR Code PIX dinâmico** (Mercado Pago / Asaas / Banco Inter) e abre via `OpenUrl` na tela do técnico para o cliente escanear. A página fica monitorando o webhook do banco em tempo real. Assim que o cliente paga, a tela fica verde (`PAGO!`), e ao fechar devolve `STATUS_PAGAMENTO = PAGO` e `ID_TRANSACAO` direto para o OfficeTrack liberar a entrega!

### 3. Leitor de QR Code / Código de Barras em Modo Contínuo (Bipagem Rápida)
* **Uso:** Inventário, carga/descarga de caminhão ou conferência de 50 extintores/caixas.
* **Fluxo:** Em vez de bipar 1 por 1 abrindo dezenas de linhas manualmente, o `OpenUrl` abre a câmera web em modo **scanner contínuo**: o técnico passa a câmera pelas 50 etiquetas em 15 segundos. Ao fechar a janela, o `<WebService>` injeta **todas as 50 linhas de uma só vez** dentro da `<TableField>` do formulário!

### 4. Buscador Avançado de Catálogo de Peças (50.000+ Itens)
* **Uso:** Quando a lista suspensa padrão do formulário é lenta ou grande demais.
* **Fluxo:** Abre uma página web com barra de busca instantânea, fotos das peças, preço e saldo de estoque em tempo real. O técnico marca as 5 peças que precisa, fecha a janela, e todas caem preenchidas na tabela de orçamento do OfficeTrack!

### 5. Seleção Visual em Planta Baixa ou Mapa Interativo
* **Uso:** Manutenção predial, shopping, hospitais, redes elétricas.
* **Fluxo:** Abre a planta baixa do andar ou mapa dos equipamentos com zoom. O técnico toca exatamente no ícone da máquina/sala no mapa. Ao fechar, preenche automaticamente `BLOCO`, `ANDAR`, `SALA`, `ID_EQUIPAMENTO` e `COORDENADAS` no formulário.

### 6. Termo de Ciência / Validação por Token OTP (SMS ou WhatsApp)
* **Uso:** Garantir que o cliente realmente acompanhou o teste ou autorizou o desligamento de energia.
* **Fluxo:** O sistema envia um código de 4 dígitos para o WhatsApp do cliente. O técnico digita esse código na tela `OpenUrl` (ou o cliente confirma no link). Ao fechar, grava `VALIDADO_POR_TOKEN = SIM` e o hash de auditoria no formulário.

### 7. Upload de Arquivos Pesados (PDFs, Laudos, Vídeos, NF-e XML)
* **Uso:** O formulário móvel padrão foca em fotos; às vezes é necessário subir PDFs de ART, notas fiscais ou vídeos longos de defeitos.
* **Fluxo:** Abre uma tela moderna de upload direto para S3 / Servidor / Google Drive. Ao fechar, o `<WebService>` preenche no formulário do OfficeTrack apenas os links permanentes gerados (`URL_VIDEO`, `URL_NF_PDF`), mantendo o app leve e rápido!

### 8. Croqui Técnico / Desenho Livre e Anotação em Foto
* **Uso:** Desenhar o esquema de ligação, marcar onde está a avaria no desenho de um carro ou planta.
* **Fluxo:** Abre um quadro branco HTML5 (`Canvas`) para desenhar com o dedo ou marcar sobre uma imagem modelo. Salva a imagem gerada no servidor e retorna a confirmação e o link para o formulário.

### 9. Agendamento Visual de Retorno na Agenda Real
* **Uso:** Quando o serviço precisa de uma segunda visita técnica.
* **Fluxo:** Abre um calendário em tempo real conectado à agenda das equipes. Mostra só os dias/horários disponíveis. O técnico escolhe junto com o cliente, confirma, e ao fechar preenche `DATA_AGENDAMENTO` e `TURNO` no OfficeTrack.

### 10. Assinatura Remota de Cliente Ausente (Aceite Digital com CPF/Geolocalização)
* **Uso:** Técnico finalizou o serviço na loja/filial, mas o gerente responsável não está presente para assinar na tela do celular do técnico.
* **Fluxo:** O link é enviado para o gerente; ele vê as fotos e o resumo da OS no celular dele, assina com o dedo na tela web dele, e a assinatura + comprovante com IP/Data retornam para o formulário do técnico fechar a OS com validade jurídica!

