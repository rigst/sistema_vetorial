# Wix Madefor Display

Fonte oficial: `google/fonts`, diretório `ofl/wixmadefordisplay`.

- arquivo de origem: `WixMadeforDisplay[wght].ttf`
- SHA-256 do arquivo variável baixado: `5cab84cd1f7231a866e59ee34245c9ca95cf23984d6b7d79132b3ffac2ef821f`
- eixo publicado: `wght`, de 400 a 800
- licença: SIL Open Font License 1.1 (`OFL.txt`)

O gerador de PDF trabalha com contornos estáticos. As variações Regular (400),
Medium (500), SemiBold (600), Bold (700) e ExtraBold (800) foram geradas com:

```bash
python -m fontTools.varLib.instancer \
  'WixMadeforDisplay[wght].ttf' wght=PESO \
  --update-name-table --no-recalc-timestamp \
  -o WixMadeforDisplay-VARIACAO.ttf
```
