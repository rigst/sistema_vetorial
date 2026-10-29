# Estouros — o que é garantido

A página **Estouros** (`/estouros/`) recebe PDFs e devolve os mesmos PDFs com
estouro (sangria) em volta. A promessa é a mesma da geração (`GERACAO-PDF.md`):
**a arte sai igual ao que entrou**. Só a página cresce.

## Como funciona

1. A página cresce **para fora**. A arte continua nas mesmas coordenadas, com
   os mesmos content streams e as mesmas imagens, byte a byte: nada é
   rasterizado, reamostrado, recomprimido nem convertido de cor.
2. A arte é recortada na caixa que ela já ocupava (a CropBox), para que nada
   escondido fora dela apareça no estouro.
3. A faixa nova é preenchida **por baixo** da arte, conforme o modo:
   - **Espelhar a arte**: a própria página, como Form XObject, refletida em
     cada borda e canto. É vetorial: as imagens são referenciadas, não copiadas.
   - **Esticar a borda**: uma faixa de 1 pt junto à borda, ampliada até cobrir o
     estouro. Bom para fundos lisos e degradês.
   - **Cor sólida**: retângulos só na faixa nova.
   - **Sem preenchimento**: a página só cresce.
4. As caixas saem no padrão de gráfica:
   - `TrimBox` = linha de corte (a arte original);
   - `BleedBox` = arte + estouro;
   - `MediaBox`/`CropBox` = folha inteira (com margem para as marcas de corte,
     quando pedidas).

## Medidas

- Unidades: cm, mm ou polegadas. Igual nos 4 lados, horizontal/vertical ou um
  valor por lado.
- As medidas são **como a página é vista**: com `/Rotate`, o "topo" vai para o
  lado certo do espaço da página.
- `/UserUnit` é respeitado na conversão (1 cm é 1 cm de verdade).
- Opção de medir a partir da **linha de corte** (`TrimBox`) quando o PDF já
  tiver uma, em vez da borda da página.
- Espelhar exige estouro menor que a própria arte. Se for maior, o arquivo
  falha com a mensagem e a sugestão de "esticar a borda" ou "cor sólida".

## Gravação

O `pikepdf` salva com `stream_decode_level=none`, `recompress_flate=False`,
`compress_streams=False` e `fix_metadata_version=False`. Com isso:

- streams comprimidos (imagens e desenho) mantêm os mesmos bytes;
- streams que vieram sem compressão (dados de edição do Illustrator, miniatura)
  continuam sem;
- o XMP (metadados) não é reescrito.

## Testes

`estouros/tests.py` cobre, para os 4 modos:

- todos os streams originais presentes byte a byte no resultado;
- imagens com os mesmos bytes, dimensões, filtro, espaço de cor e bits;
- interior da arte idêntico pixel a pixel (render a 72 dpi, estouro de 1/2 pol);
- caixas TrimBox/BleedBox/MediaBox/CropBox;
- `/Rotate` 0/90/180/270, `/UserUnit`, recursos herdados da árvore de páginas,
  vários content streams, CropBox menor que a MediaBox, TrimBox existente;
- PDF inválido e protegido por senha com mensagem clara.

## Retenção

Os resultados ficam guardados por `ESTOUROS_RETENCAO_DIAS` (padrão 7) para
qualquer conta: são subproduto, e o original está com quem enviou. A limpeza é
a mesma tarefa diária do Celery (`core.tasks.cleanup_expired_assets`).
