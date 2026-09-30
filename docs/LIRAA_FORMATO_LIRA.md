# Formato `.lira` — evidência preliminar para futura exportação

Análise somente leitura de quatro arquivos de Almirante Tamandaré-PR,
guardados pelo usuário nas pastas FEVEREIRO, MAIO, SETEMBRO e NOVEMBRO de 2025.
O conteúdo segue a mesma ordem das 28 colunas da tabela `SVS` do
`LIRAaMunicipios.mdb` do programa LIRAa/LIA. **Não implementar exportação
oficial apenas com esta evidência:** é preciso conferir os cálculos e obter
aceitação do arquivo pelo destinatário.

Todos os exemplos têm 30 linhas não vazias, separador CRLF e duas linhas
vazias finais. O nome `Almirante Tamandaré` contém o byte `E9` para `é`,
compatível com codificação Windows-1252/Latin-1 e incompatível com UTF-8
direto. Valores decimais usam vírgula. Os dois primeiros campos foram `1`
e `30` nos quatro exemplos; podem representar cabeçalho/contagem, mas seu
significado formal não foi demonstrado.

| Linha | Campo observado/coluna `SVS` |
|---:|---|
| 1–2 | `1`, `30` — cabeçalho ainda não documentado |
| 3–4 | Município; UF |
| 5–6 | IIP; IB de *Aedes aegypti* |
| 7–12 | Estratos por três faixas de risco, cada uma como contagem e percentual |
| 13–26 | Tipos de recipientes A1, A2, B, C, D1, D2, E; cada um contagem e percentual |
| 27–28 | Período livre em texto; código do município |
| 29–30 | IIP; IB de *Aedes albopictus* |

Os três pares de faixas de risco somam cinco estratos e 100% em cada arquivo.
As sete porcentagens de recipientes somam 100%, exceto fevereiro (100,1%
devido a arredondamento decimal). O período não tem formato uniforme:
o arquivo na pasta FEVEREIRO declara `10/01/2025 a 14/01/2025`, enquanto o
de NOVEMBRO não explicita o ano. Não usar nome da pasta para inferir data.

O `.lira` contém **consolidado municipal**, não cadastro de quarteirões,
plano amostral ou inspeções individuais. A página `/liraa` primeiro precisa
registrar esses dados e calcular os índices antes de exportar. A orientação
do sistema legado descreve a ação “Gerar Dados para SVS”, que salva
`Município-UF.lira`: [Instruções do Sistema LIRAa/LIA](https://saude.rs.gov.br/upload/arquivos/carga20190405/16090540-14105744-instrucoes-i.pdf).
