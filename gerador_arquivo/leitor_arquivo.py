#1 - Receber um arquivo e ler.
#- Cada linha uma requisição para uma API.
#- Pegar os dados da API e gerar um arquivo pra cada requisição feita.
#o arquivo, seria um txt, cada linha seria parametro para a API, e o resultado da API, alguns dados, gravar em um outro txt…..teriamos uns 2-3 desses codigos a fazer…


with open("c:/WS-Officetrack/gerador_arquivo/itens.txt", "a") as arquivo:
    arquivo.write('\n')
    arquivo.write("teste 5")
    arquivo.write("\n")
    arquivo.write("teste 6")