# Geração de PDF — o que é garantido

O StölbenVetorial existe para produzir arquivos vetoriais prontos para corte,
plotagem e impressão. Duas promessas sustentam isso, e as duas têm teste
automatizado em `jobs/tests.py::OutputFidelityTests` e
`editor/tests.py::BackgroundImageFidelityTests`.

## 1. O fundo sai igual ao que entrou

O PDF gerado **é** o PDF de fundo com uma camada por cima. O `pikepdf` abre o
arquivo enviado e o salva de volta copiando os streams como estão, então:

- `MediaBox` e `CropBox` continuam com os mesmos valores;
- a imagem embutida mantém os mesmos bytes, a mesma resolução em pixels, o
  mesmo filtro de compressão e o mesmo perfil de cor — nada é reamostrado nem
  recomprimido;
- o `/Rotate` da página é preservado.

O teste `test_output_keeps_the_background_image_untouched` compara o stream de
imagem do fundo com o do arquivo gerado byte a byte.

### Fundo enviado como imagem

Um PNG, JPG ou WebP vira uma página de PDF com **1 pixel = 1 ponto**
(`resolution=72`), sem perda:

- **JPEG**: os bytes originais entram direto no PDF como `DCTDecode`. Não há
  recodificação, então não existe segunda geração de artefato.
- **PNG / WebP / qualquer outro**: os pixels crus entram como `FlateDecode`,
  que é compressão sem perdas.
- O perfil **ICC** do arquivo, quando existe, é embutido como espaço de cor.
- Imagens com alfa são achatadas sobre branco: a página do PDF é opaca.
- A orientação EXIF é aplicada antes da conversão.

> Historicamente o Pillow salvava esses fundos como JPEG de qualidade 75 — um
> PNG de traço fino chegava a errar 127 de 255 em um canal. Fundos enviados
> antes dessa mudança seguem com a perda gravada no arquivo; reenviar o fundo
> do projeto resolve.

## 2. O texto sai como curva, não como fonte

Cada letra é extraída da fonte pelo `fontTools`, convertida em contorno e
escrita no PDF como caminho (`m`/`l`/`c`/`h`) preenchido com a regra não-zero.
Consequências:

- o PDF de saída **não embute fonte nenhuma** e não contém operador de texto
  (`BT`/`Tj`/`TJ`), o que é o que um fluxo de corte ou gravação precisa receber;
- o resultado é idêntico em qualquer máquina, sem depender de a fonte estar
  instalada;
- o contorno (`border_*`) é traçado sobre o mesmo caminho, com junção e ponta
  arredondadas, e o efeito de blur é feito com cópias do caminho em baixa
  opacidade — tudo vetorial, sem rasterizar.

O avanço de cada glifo vem do `hmtx`, a mesma tabela que alimenta o
`stringWidth` do reportlab usado para quebrar e alinhar as linhas: a linha
desenhada tem exatamente a largura já calculada.

## 3. O que o editor mostra é onde o texto cai

`editor/services.py:read_page_geometry` lê a caixa visível da página — a
`CropBox` quando existe, senão a `MediaBox`, recortada pelos limites da
`MediaBox` — e o `/Rotate`. É essa medida que vira `page_width`/`page_height`
do projeto, é nela que o `pdftoppm -cropbox` rasteriza o preview da bancada e é
nela que os campos são posicionados.

Na hora de compor, o overlay nasce do tamanho exato dessa caixa e é colocado
com uma matriz de translação pura (`1 0 0 1 x0 y0 cm`). Não existe reencaixe:
a escala é sempre 1:1. Se as medidas do fundo divergirem do que o projeto
registrou, a geração falha pedindo o reenvio do fundo em vez de esticar o
texto. Fundos com `/Rotate` recebem a transformação inversa, de modo que o
texto sai em pé na página girada.
