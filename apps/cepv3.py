from flask import request, Response
import requests
from lxml import etree
import logging
import re
from utils.gerar_erro import gerar_erro_xml
from utils.adicionar_campo import adicionar_campo
from utils.adicionar_table_field import adicionar_table_field

def consultar_cepv3():
    try:
        content_type = request.headers.get("Content-Type", "").lower()
        logging.debug(f"Tipo de conteúdo recebido: {content_type}")
        
        # Tenta extrair o XML de várias fontes possíveis
        xml_data = None
        
        # Tenta do form primeiro (com vários nomes possíveis)
        if request.form:
            for possible_name in ["TextXML", "textxml", "xmldata", "xml", "application/x-www-form-urlencoded"]:
                if possible_name in request.form:
                    xml_data = request.form.get(possible_name)
                    logging.debug(f"XML encontrado no campo {possible_name}")
                    break
            
            # Se não encontrou por nome específico, tenta o primeiro campo do form
            if not xml_data and len(request.form) > 0:
                first_key = next(iter(request.form))
                xml_data = request.form.get(first_key)
                logging.debug(f"Usando primeiro campo do form: {first_key}")
        
        # Se não encontrou no form, tenta do corpo da requisição
        if not xml_data and request.data:
            try:
                xml_data = request.data.decode('utf-8')
                logging.debug("Usando dados brutos do corpo da requisição")
            except:
                pass
        
        if not xml_data:
            return gerar_erro_xml("Não foi possível encontrar dados XML na requisição", "Erro")
        
        logging.debug(f"XML para processar: {xml_data}")

        # Tenta fazer o parse do XML
        try:
            root = etree.fromstring(xml_data.encode("utf-8"))
        except etree.XMLSyntaxError:
            return gerar_erro_xml("Erro ao processar o XML recebido.", "Erro")

        # Processa os campos do XML
        campos = processar_campos(root)

        # Faz a requisição à API ViaCEP
        cep = campos.get("CEP")
        if not cep:
            return gerar_erro_xml("Erro: CEP não informado no campo CEP.", "CEP invalido")

        response = requests.get(f"https://viacep.com.br/ws/{cep}/json/")
        if response.status_code != 200:
            return gerar_erro_xml("Erro ao consultar o CEP - Verifique e tente novamente.", "Erro")

        data = response.json()
        if "erro" in data:
            return gerar_erro_xml("Erro: CEP inválido ou não encontrado.", "Erro")

        # Verifica se deve buscar múltiplos endereços
        logging.debug(f"Verificando se deve buscar múltiplos endereços para CEP: {cep}")
        
        if deve_buscar_multiplos_enderecos(data, cep):
            logging.debug("Buscando múltiplos endereços...")
            enderecos_multiplos = buscar_enderecos_multiplos(data, cep)
            
            if enderecos_multiplos and len(enderecos_multiplos) > 1:
                logging.debug(f"Encontrados {len(enderecos_multiplos)} endereços múltiplos")
                return gerar_value_selection(enderecos_multiplos)
        
        # Retorna o formato normal ResponseV2
        logging.debug("Retornando ResponseV2 normal")
        return gerar_resposta_xml_v2(data)

    except Exception as e:
        logging.error(f"Erro interno: {str(e)}")
        import traceback
        logging.error(f"Traceback: {traceback.format_exc()}")
        return gerar_erro_xml(f"Erro interno no servidor: {str(e)}", "Erro")

def deve_buscar_multiplos_enderecos(data, cep):
    """
    Verifica se o CEP/endereço indica que pode haver múltiplos endereços.
    Baseado em características como CEP terminado em 000, complemento vazio, etc.
    """
    
    # CEPs que terminam em 000 geralmente são de logradouros grandes
    cep_limpo = cep.replace("-", "")
    if cep_limpo.endswith("000"):
        logging.debug(f"CEP {cep} termina em 000 - pode ter múltiplos endereços")
        return True
    
    # Se o complemento está vazio, pode indicar que há várias opções
    complemento = data.get("complemento", "")
    if not complemento or complemento.strip() == "":
        logging.debug(f"CEP {cep} sem complemento - pode ter múltiplos endereços")
        return True
    
    # Logradouros muito genéricos (avenidas, ruas principais)
    logradouro = data.get("logradouro", "").lower()
    logradouros_genericos = [
        "avenida", "rodovia", "estrada", "via", "marginal", 
        "alameda principal", "rua principal"
    ]
    
    for generico in logradouros_genericos:
        if generico in logradouro:
            logging.debug(f"Logradouro genérico detectado: {logradouro}")
            return True
    
    return False

def buscar_enderecos_multiplos(data_viacep, cep):
    """
    Busca múltiplos endereços baseado em CEPs próximos/similares.
    Foca apenas em variações do mesmo CEP base.
    """
    
    try:
        # Extrai o CEP base (sem os últimos 3 dígitos)
        cep_limpo = cep.replace("-", "")
        cep_base = cep_limpo[:-3]  # Ex: "01310000" → "01310"
        
        logging.debug(f"Buscando CEPs similares ao base: {cep_base}xxx")
        
        # Lista de variações de CEP para testar
        ceps_para_testar = gerar_ceps_similares(cep_base)
        
        enderecos = []
        enderecos_encontrados = set()  # Para evitar duplicatas
        
        for cep_teste in ceps_para_testar:
            try:
                # Formata o CEP com hífen
                cep_formatado = f"{cep_teste[:5]}-{cep_teste[5:]}"
                
                # Pula o CEP original (já temos os dados)
                if cep_formatado == cep:
                    continue
                
                # Consulta o CEP
                url_teste = f"https://viacep.com.br/ws/{cep_formatado}/json/"
                response = requests.get(url_teste, timeout=5)
                
                if response.status_code == 200:
                    resultado = response.json()
                    
                    # Verifica se é válido e se é do mesmo logradouro base
                    if not resultado.get("erro") and eh_endereco_similar(data_viacep, resultado):
                        cep_key = resultado.get("cep", "")
                        
                        # Evita duplicatas
                        if cep_key not in enderecos_encontrados:
                            enderecos_encontrados.add(cep_key)
                            
                            endereco_completo = montar_endereco_completo(resultado)
                            
                            endereco = {
                                "id": str(len(enderecos) + 1),
                                "endereco_completo": endereco_completo,
                                "cep": resultado.get("cep", ""),
                                "logradouro": resultado.get("logradouro", ""),
                                "complemento": resultado.get("complemento", ""),
                                "bairro": resultado.get("bairro", ""),
                                "cidade": resultado.get("localidade", ""),
                                "uf": resultado.get("uf", ""),
                                "dados_completos": resultado
                            }
                            enderecos.append(endereco)
                
                # Para não sobrecarregar a API
                if len(enderecos) >= 8:  # Limita a 8 resultados
                    break
                    
            except requests.RequestException:
                continue  # Ignora erros de CEPs individuais
        
        logging.debug(f"Encontrados {len(enderecos)} endereços similares")
        return enderecos
        
    except Exception as e:
        logging.error(f"Erro ao buscar endereços múltiplos: {str(e)}")
        return []

def gerar_ceps_similares(cep_base):
    """
    Gera lista de CEPs similares para testar.
    Ex: para "01310" gera ["01310000", "01310100", "01310200", ...]
    """
    ceps = []
    
    # Variações de 100 em 100 (mais comum para logradouros grandes)
    for i in range(0, 900, 100):  # 000, 100, 200, ..., 800
        cep_variacao = f"{cep_base}{i:03d}"
        ceps.append(cep_variacao)
    
    # Algumas variações específicas comuns
    variações_especiais = ["001", "010", "020", "050", "999"]
    for var in variações_especiais:
        cep_variacao = f"{cep_base}{var}"
        if cep_variacao not in ceps:
            ceps.append(cep_variacao)
    
    logging.debug(f"CEPs para testar: {ceps[:5]}... (total: {len(ceps)})")
    return ceps

def eh_endereco_similar(endereco_original, endereco_teste):
    """
    Verifica se o endereço testado é realmente similar ao original.
    Evita trazer endereços muito diferentes.
    """
    
    # Deve ser da mesma cidade e UF
    if (endereco_original.get("localidade") != endereco_teste.get("localidade") or 
        endereco_original.get("uf") != endereco_teste.get("uf")):
        return False
    
    # Deve ser do mesmo bairro ou bairro muito próximo
    bairro_original = endereco_original.get("bairro", "").lower()
    bairro_teste = endereco_teste.get("bairro", "").lower()
    
    # Se os bairros são muito diferentes, rejeita
    if bairro_original and bairro_teste:
        # Permite se são exatamente iguais ou um contém o outro
        if bairro_original not in bairro_teste and bairro_teste not in bairro_original:
            # Verifica se ao menos têm uma palavra em comum
            palavras_original = set(bairro_original.split())
            palavras_teste = set(bairro_teste.split())
            
            if not palavras_original.intersection(palavras_teste):
                logging.debug(f"Bairros muito diferentes: '{bairro_original}' vs '{bairro_teste}'")
                return False
    
    # Verifica se o logradouro é similar
    logradouro_original = endereco_original.get("logradouro", "").lower()
    logradouro_teste = endereco_teste.get("logradouro", "").lower()
    
    if logradouro_original and logradouro_teste:
        # Extrai palavras-chave do logradouro
        palavras_original = set(logradouro_original.replace("avenida", "").replace("rua", "").replace("alameda", "").split())
        palavras_teste = set(logradouro_teste.replace("avenida", "").replace("rua", "").replace("alameda", "").split())
        
        # Remove palavras muito comuns
        palavras_comuns = {"de", "da", "do", "das", "dos", "e", "&", "santo", "santa"}
        palavras_original -= palavras_comuns
        palavras_teste -= palavras_comuns
        
        # Deve ter pelo menos uma palavra-chave em comum
        if palavras_original and palavras_teste:
            if not palavras_original.intersection(palavras_teste):
                logging.debug(f"Logradouros muito diferentes: '{logradouro_original}' vs '{logradouro_teste}'")
                return False
    
    return True

def limpar_logradouro_para_busca(logradouro):
    """
    Limpa o logradouro para fazer a busca na API do ViaCEP.
    Remove números, palavras muito específicas, etc.
    """
    
    # Remove números do logradouro
    logradouro_limpo = re.sub(r'\d+', '', logradouro).strip()
    
    # Remove palavras muito específicas que podem não dar match
    palavras_remover = ['de', 'da', 'do', 'das', 'dos', 'e', '&']
    palavras = logradouro_limpo.split()
    palavras_filtradas = [p for p in palavras if p.lower() not in palavras_remover and len(p) > 2]
    
    # Se sobrou pelo menos uma palavra, usa ela
    if palavras_filtradas:
        return ' '.join(palavras_filtradas[:3])  # Pega no máximo 3 palavras
    
    # Se não sobrou nada útil, retorna o original
    return logradouro

def montar_endereco_completo(dados_endereco):
    """
    Monta o endereço completo para exibição na lista de seleção.
    """
    
    partes = []
    
    # Logradouro
    if dados_endereco.get("logradouro"):
        partes.append(dados_endereco["logradouro"])
    
    # Complemento (se houver)
    if dados_endereco.get("complemento") and dados_endereco["complemento"].strip():
        partes.append(f"({dados_endereco['complemento']})")
    
    # Bairro
    if dados_endereco.get("bairro"):
        partes.append(f"- {dados_endereco['bairro']}")
    
    # Cidade e UF
    cidade = dados_endereco.get("localidade", "")
    uf = dados_endereco.get("uf", "")
    if cidade and uf:
        partes.append(f", {cidade} - {uf}")
    
    # CEP
    if dados_endereco.get("cep"):
        partes.append(f" (CEP: {dados_endereco['cep']})")
    
    return " ".join(partes)

def gerar_value_selection(enderecos):
    """Gera XML no formato Value Selection para múltiplos endereços."""
    
    # Criar o elemento Response
    response = etree.Element("Response")
    
    # Adicionar mensagem opcional
    message = etree.SubElement(response, "Message")
    etree.SubElement(message, "Text").text = "Múltiplos endereços encontrados. Selecione um:"
    etree.SubElement(message, "Icon").text = "Info"
    
    # Criar ReturnValue com Items
    return_value = etree.SubElement(response, "ReturnValue")
    items = etree.SubElement(return_value, "Items")
    
    # Adicionar cada endereço como um Item
    for endereco in enderecos:
        item = etree.SubElement(items, "Item")
        etree.SubElement(item, "Text").text = endereco["endereco_completo"]
        etree.SubElement(item, "Value").text = endereco["id"]
    
    # Gerar XML com encoding utf-16
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>'
    xml_str = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str = xml_declaration + "\n" + xml_str
    
    logging.debug(f"XML Value Selection: {xml_str}")
    
    return Response(xml_str.encode("utf-16"), content_type="application/xml; charset=utf-16")

def processar_campos(root):
    """Processa os campos do XML e retorna um dicionário com os valores."""
    campos = {}
    for field in root.findall(".//Field"):
        id = field.findtext("ID") or field.findtext("Id")  # Tenta ambos os formatos
        value = field.findtext("Value")
        if id and value:
            campos[id] = value

    for table_field in root.findall(".//TableField"):
        table_id = table_field.findtext("ID")
        rows = []
        for row in table_field.findall(".//Row"):
            row_data = {}
            for field in row.findall(".//Field"):
                id = field.findtext("ID")
                value = field.findtext("Value")
                if id and value:
                    row_data[id] = value
            rows.append(row_data)
        campos[table_id] = rows

    return campos

def gerar_resposta_xml_v2(data):
    """Gera a resposta XML V2 com os dados do endereço."""
    # Definir namespaces
    nsmap = {
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        'xsd': 'http://www.w3.org/2001/XMLSchema'
    }
    
    # Criar o elemento raiz com namespaces
    response = etree.Element("ResponseV2", nsmap=nsmap)
    
    # Adicionar seção de mensagem
    message = etree.SubElement(response, "MessageV2")
    etree.SubElement(message, "Text").text = "CEP encontrado com sucesso"
    
    # Criar seção ReturnValueV2
    return_value = etree.SubElement(response, "ReturnValueV2")
    fields = etree.SubElement(return_value, "Fields")
    
    # Mapear dados do CEP para os novos campos
    adicionar_campo(fields, "LOGRADOURO", data.get("logradouro", ""))
    adicionar_campo(fields, "COMPLEMENTO", data.get("complemento", ""))
    adicionar_campo(fields, "BAIRRO", data.get("bairro", ""))
    adicionar_campo(fields, "CIDADE", data.get("localidade", ""))
    adicionar_campo(fields, "ESTADO", data.get("estado", ""))
    adicionar_campo(fields, "UF", data.get("uf", ""))
    
    # Adicionar TableField exemplo
    table_field_id = "TABCAIXA1"
    rows_data = [
        {"TextTable": "Y", "CX1PESO": "9,0"},
        {"TextTable": "X", "CX1PESO": "8,0"},
    ]
    adicionar_table_field(fields, table_field_id, rows_data)
    
    # Adicionar campos adicionais do ReturnValueV2
    etree.SubElement(return_value, "ShortText").text = "CEP ENCONTRADO - INFOS ABAIXO"
    etree.SubElement(return_value, "LongText")  # Vazio
    etree.SubElement(return_value, "Value").text = "58"
    
    # Gerar XML com declaração e encoding utf-16
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>'
    xml_str = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str = xml_declaration + "\n" + xml_str
    
    logging.debug(f"XML de Resposta V2: {xml_str}")
    
    return Response(xml_str.encode("utf-16"), content_type="application/xml; charset=utf-16")

def gerar_erro_xml(mensagem, short_text):
    """Gera um XML de erro com mensagem personalizada."""
    # Definir namespaces
    nsmap = {
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        'xsd': 'http://www.w3.org/2001/XMLSchema'
    }
    
    # Criar o elemento raiz com namespaces
    response = etree.Element("ResponseV2", nsmap=nsmap)
    
    # Adicionar seção de mensagem
    message = etree.SubElement(response, "MessageV2")
    etree.SubElement(message, "Text").text = mensagem
    
    # Criar seção ReturnValueV2 vazia
    return_value = etree.SubElement(response, "ReturnValueV2")
    etree.SubElement(return_value, "Fields")
    etree.SubElement(return_value, "ShortText").text = short_text
    etree.SubElement(return_value, "LongText")
    etree.SubElement(return_value, "Value").text = "0"
    
    # Gerar XML com declaração e encoding utf-16
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>'
    xml_str = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str = xml_declaration + "\n" + xml_str
    
    return Response(xml_str.encode("utf-16"), content_type="application/xml; charset=utf-16")