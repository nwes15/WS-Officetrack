# MANUAL DE TREINAMENTO PARA IA: DESENVOLVIMENTO DE WEB SERVICES OFFICETRACK

Este documento é a base de conhecimento e diretriz técnica para qualquer Inteligência Artificial (ou desenvolvedor) que vá criar, modificar ou manter microsserviços integrados ao **OfficeTrack** via controle **Web Service Call**.

---

## 1. Visão Geral da Arquitetura OfficeTrack

O **OfficeTrack** é uma plataforma móvel corporativa de formulários e ordens de serviço em campo.
Quando um formulário possui um controle do tipo **Web Service Call** (que aparece como um botão na tela do celular do operador), o fluxo é o seguinte:

```
[Celular do Operador / OfficeTrack App]
              │
     (1) Pressiona o botão
              ▼
    HTTP POST com todo o XML do formulário
              ▼
[Middleware Flask / Web Service Externo]
              │
     (2) Extrai campos / Executa regra / Consulta APIs (ViaCEP, LLMs, ERP, etc.)
              │
     (3) Devolve XML formatado
              ▼
[Celular do Operador / OfficeTrack App]
              │
     (4) Aplica a resposta na tela (Pop-up, preenche campos, preenche tabelas ou envia o form)
```

---

## 2. Como o OfficeTrack Envia a Requisição (Entrada)

O aplicativo móvel envia uma requisição **HTTP POST** (`application/x-www-form-urlencoded` ou dados brutos).
O XML completo do formulário geralmente chega no parâmetro **`Data`** ou **`TextXML`** (ou `xmldata`).

### Estrutura do XML de Entrada do Formulário:
```xml
<Form>
  <Guid>0dd92525-9ef0-4f5b-9e8d-d3bbaf7c2957</Guid>
  <Employee>
    <EmployeeNumber>WH3</EmployeeNumber>
  </Employee>
  <Task>
    <TaskNum>123498674319877046</TaskNum>
  </Task>
  <Fields>
    <!-- Campo Simples -->
    <Field>
      <Id>CEP</Id>
      <Value>01310100</Value>
    </Field>
    
    <!-- Tabela Dinâmica -->
    <TableField>
      <Id>TABELA_ITENS</Id>
      <Rows>
        <Row>
          <Fields>
            <Field>
              <Id>CODIGO</Id>
              <Value>ITEM01</Value>
            </Field>
          </Fields>
        </Row>
      </Rows>
    </TableField>
  </Fields>
</Form>
```

> **Atenção:** Em algumas versões do app, o nó do identificador do campo pode vir como `<Id>` ou `<ID>`. O parser deve sempre aceitar ambos: `field.findtext("ID") or field.findtext("Id")`.

---

## 3. Tipos de Resposta Suportados

Conforme documentado no manual oficial da API (*Apêndice D, páginas 161 a 173*), existem três modalidades principais de resposta:

### Modalidade A: Validação Simples (Modo V1)
Usado para validações diretas (Aprovação ou Reprovação sem preenchimento complexo de tabelas):

* **Sucesso (envia o formulário automaticamente):**
```xml
<Response>
    <ReturnValue>
        <ShortText>Validado</ShortText>
        <LongText>Item validado com sucesso</LongText>
        <Value>OK</Value>
        <Action>SendEntry</Action> <!-- Força envio e fechamento do form -->
    </ReturnValue>
</Response>
```

* **Erro (abre pop-up com ícone):**
```xml
<Response>
    <Message>
        <Text>Código inválido!</Text>
        <Icon>Warning</Icon> <!-- Warning, Critical ou Info -->
        <ButtonText>OK</ButtonText>
    </Message>
    <ReturnValue>
        <Value>Failed</Value>
    </ReturnValue>
</Response>
```

---

### Modalidade B: Seleção de Valores (Value Selection)
Quando o Web Service deve retornar uma lista suspensa / popup de opções para o operador escolher uma delas:

```xml
<Response>
    <ReturnValue>
        <Items>
            <Item>
                <Text>Opção 1 - Centro</Text>
                <Value>01</Value>
            </Item>
            <Item>
                <Text>Opção 2 - Filial Sul</Text>
                <Value>02</Value>
            </Item>
        </Items>
    </ReturnValue>
</Response>
```

---

### Modalidade C: Validação e Preenchimento de Campos (`ResponseV2`) - **PADRÃO PRINCIPAL**
Este é o formato mais utilizado e obrigatório para preencher outros campos e tabelas dinâmicas.

> [!CRITICAL]
> **REQUISITOS OBRIGATÓRIOS DO RESPONSEV2:**
> 1. Encoding estritamente em **`UTF-16`** (`<?xml version="1.0" encoding="utf-16"?>`).
> 2. Cabeçalho HTTP: `Content-Type: application/xml; charset=utf-16`.
> 3. Namespaces `xsi` e `xsd` declarados no elemento raiz `<ResponseV2>`.

```xml
<?xml version="1.0" encoding="utf-16"?>
<ResponseV2 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
    
    <!-- Pop-up central na tela do celular (opcional, pode omitir se quiser silencioso) -->
    <MessageV2>
        <Text>Mensagem exibida no Pop-up nativo do celular</Text>
    </MessageV2>
    
    <ReturnValueV2>
        <!-- 1. CAMPOS QUE SERÃO PREENCHIDOS NO FORMULÁRIO -->
        <Fields>
            <!-- Preenchimento de campo simples de texto/número -->
            <Field>
                <ID>NOME_CAMPO</ID>
                <Value>Texto ou Valor</Value>
            </Field>

            <!-- Preenchimento de Tabela (TableField) -->
            <TableField>
                <ID>ID_DA_TABELA</ID>
                <Rows>
                    <Row>
                        <Fields>
                            <Field>
                                <ID>COLUNA_1</ID>
                                <Value>Dado 1</Value>
                            </Field>
                            <Field>
                                <ID>COLUNA_2</ID>
                                <Value>Dado 2</Value>
                            </Field>
                        </Fields>
                    </Row>
                </Rows>
            </TableField>
        </Fields>

        <!-- 2. CONTROLE DO BOTÃO DO FORMULÁRIO -->
        <ShortText>OK</ShortText> <!-- Texto escrito dentro/abaixo do botão (OK ou NOK) -->
        <LongText>Toque na lixeira para nova consulta após correção</LongText> <!-- Texto secundário de instrução -->
        <Value>1</Value> <!-- 1 = Sucesso | 0 = Falha -->
        
        <!-- SE QUISER ENVIAR O FORMULÁRIO AUTOMATICAMENTE: -->
        <!-- <Action>SendEntry</Action> -->
        <!-- SE NÃO QUISER FECHAR O FORMULÁRIO: NUNCA INCLUA A TAG <Action> -->
    </ReturnValueV2>
    
</ResponseV2>
```

---

## 4. O Comportamento da Tag `<Action>` (Fechar ou Manter Aberto)

* **Se a validação for OK e você QUER enviar o formulário:**
  Adicione `<Action>SendEntry</Action>` dentro de `<ReturnValueV2>`. O app fecha e transmite a tarefa.
* **Se a validação for de tabela ou etapas intermediárias (o formulário DEVE continuar aberto):**
  **NUNCA inclua a tag `<Action>`**. O formulário atualizará os dados e permanecerá na tela para o operador continuar trabalhando.

---

## 5. Como Funciona a Trava do Botão e o Ícone da Lixeira

No OfficeTrack móvel:
1. Após a execução de um Web Service, o aplicativo grava o status daquele botão e exibe um **ícone de lixeira** ao lado.
2. Essa trava é intencional da plataforma para evitar duplo clique ou perda de dados.
3. Se o retorno for de inconsistência (**NOK**):
   * Deve-se manter `<Value>0</Value>`.
   * Informar no `<LongText>`: `Toque na lixeira para nova consulta após correção`.
   * O operador toca na lixeira (resetando o botão) e pode clicar novamente após corrigir a tela.

---

## 6. Preenchimento de Tabelas (`TableField`)

Para manipular tabelas do formulário pelo Web Service:
* **Identificador da Tabela:** Deve bater exatamente com o `Id` do controle no criador de formulários (ex: `TABEXSTINTORES`, `TABELA_ITENS`).
* **Manipulação de Linha Ativa:** Quando o operador clica no botão enquanto está editando uma linha de tabela, o XML de entrada marca essa linha com o atributo `@IsCurrentRow='True'`.
* **Inserção Dinâmica:** O Web Service pode devolver quantas `<Row>` forem necessárias.

---

## 7. Estrutura de Pastas e Módulos do Repositório

```text
WS-Officetrack/
├── middleware.py           # Ponto de entrada Flask (registra todas as rotas e portas)
├── apps/                   # Pasta com as regras de negócio de cada serviço
│   ├── consultar_cep.py    # Consulta ViaCEP (V1)
│   ├── cepv2.py            # Consulta ViaCEP limpa (UTF-16)
│   ├── cepv3.py            # Híbrido: ResponseV2 ou Value Selection conforme resultado
│   ├── consultar_endereco.py # Geocodificação reversa via OpenStreetMap/GPS
│   ├── consultar_groq.py   # Assistente IA com Llama 3 via Groq
│   ├── talk_descript.py    # Correção de texto de voz via IA
│   ├── consultar_peso.py   # Simulação de balança e validação de peso
│   ├── validar_item.py     # Validação de catálogo e envio automático SendEntry
│   ├── validar_extintores.py # Validação dinâmica de duplicidade em extintores
│   ├── validar_duplicidade.py # Validação genérica de duplicidade de IDLOCAL para qualquer tabela
│   └── ...
└── utils/                  # Utilitários reaproveitáveis
    ├── xml_da_requisicao.py  # Extração resiliente de XML da requisição
    ├── adicionar_campo.py    # Helper para criar nós <Field>
    ├── adicionar_table_field.py # Helper para criar nós <TableField> e <Row>
    └── gerar_erro.py         # Helper para retorno padrão de erro XML
```

---

## 8. Template Padrão para Criar Novos Serviços

Toda nova função a ser criada na pasta `apps/` deve seguir este modelo pronto e testado:

```python
from flask import request, Response
from lxml import etree
import logging
from io import StringIO
from utils.xml_da_requisicao import obter_xml_da_requisicao
from utils.adicionar_campo import adicionar_campo

def meu_novo_servico():
    try:
        # 1. Obtém o XML da requisição de forma resiliente
        xml_data = obter_xml_da_requisicao()
        if not xml_data:
            return gerar_resposta_xml(sucesso=False, mensagem="Dados XML não encontrados.", short_text="Erro")

        # 2. Faz o parsing com recuperação de falhas
        parser = etree.XMLParser(recover=True)
        tree = etree.parse(StringIO(xml_data), parser)
        root = tree.getroot()

        # 3. Lê os campos necessários
        # Exemplo campo simples:
        # valor = root.xpath(".//Field[Id='MEU_CAMPO']/Value")[0].text
        
        # 4. Executa a lógica de negócio
        deu_certo = True # ou False
        
        if not deu_certo:
            return gerar_resposta_xml(
                sucesso=False,
                mensagem="Inconsistência encontrada! Verifique os dados.",
                short_text="NOK",
                retorno="NOK",
                long_text="Toque na lixeira para nova consulta após correção"
            )

        # 5. Sucesso (mantendo o formulário aberto)
        return gerar_resposta_xml(
            sucesso=True,
            mensagem="Operação realizada com sucesso!",
            short_text="OK",
            retorno="OK",
            long_text=""
        )

    except Exception as e:
        logging.error(f"Erro no serviço: {e}", exc_info=True)
        return gerar_resposta_xml(sucesso=False, mensagem=f"Erro interno: {str(e)}", short_text="Erro")


def gerar_resposta_xml(sucesso, mensagem, short_text, retorno="", long_text=""):
    """Construtor padrão ResponseV2 em UTF-16 para OfficeTrack"""
    nsmap = {
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        'xsd': 'http://www.w3.org/2001/XMLSchema'
    }
    response = etree.Element("ResponseV2", nsmap=nsmap)

    # Pop-up na tela
    message = etree.SubElement(response, "MessageV2")
    etree.SubElement(message, "Text").text = mensagem

    # Retornos
    return_value = etree.SubElement(response, "ReturnValueV2")
    fields = etree.SubElement(return_value, "Fields")

    # Preenchimento de campos no formulário
    if retorno:
        adicionar_campo(fields, "RETORNO", str(retorno))

    etree.SubElement(return_value, "ShortText").text = short_text
    if long_text:
        etree.SubElement(return_value, "LongText").text = long_text
    etree.SubElement(return_value, "Value").text = "1" if sucesso else "0"

    # NÃO adicionar <Action>SendEntry</Action> se o formulário deve continuar aberto

    # Serialização estritamente em UTF-16
    xml_header = '<?xml version="1.0" encoding="utf-16"?>\n'
    xml_body = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_final = xml_header + xml_body

    return Response(xml_final.encode("utf-16"), content_type="application/xml; charset=utf-16")
```

---

## 9. Como Registrar a Rota no `middleware.py`

Após criar o script em `apps/novo_servico.py`:
1. Abra `middleware.py`.
2. Importe a função: `from apps.novo_servico import meu_novo_servico`.
3. Registre a URL:
   ```python
   app.add_url_rule("/novo_servico", methods=['POST'], view_func=meu_novo_servico)
   ```
4. Certifique-se de que o servidor roda com `host='0.0.0.0'` na porta `5001`.

