# StölbenVetorial

Sistema Django para edição visual de templates em PDF e geração de arquivos por lote a partir de Excel.

## Principais recursos

- login com acesso visitante temporário;
- exclusão automática dos dados do visitante ao sair;
- templates com fundo em PDF de uma página ou imagem (PNG/JPG/WebP, convertida para PDF);
- editor visual baseado em Fabric.js: arraste, redimensione, gire, multi-seleção, snap com guias, zoom, undo/redo, atalhos de teclado e edição de texto com duplo clique;
- pré-visualização fiel: as fontes do usuário são carregadas no navegador e a métrica de texto do editor é replicada na geração do PDF;
- saída vetorial fiel: o fundo é copiado sem recompressão e o texto vira curva, sem fonte embutida (ver `docs/GERACAO-PDF.md`);
- geração direto da bancada: envie o Excel, gere uma amostra de 3 linhas ou o lote completo e acompanhe o progresso sem sair do editor;
- teste com dados reais no editor: envio de um Excel de amostra e navegação linha a linha;
- campos configurados por nome, coluna numérica do Excel, fonte, cor, rotação, contorno e opções avançadas;
- fontes ativas e inativas por usuário;
- jobs com retenção automática de 7 dias;
- storage privado com acesso restrito ao dono dos arquivos.

## Módulos

- `core`: autenticação, dashboard, manual e limpeza.
- `editor`: templates, preview do PDF e editor visual.
- `fonts`: cadastro e inativação de fontes.
- `jobs`: processamento de planilhas e geração de arquivos.
- `legal`: termos, política de privacidade e registro de aceite.

## Como rodar

```bash
cd /home/rodrigo/Projetos/sistema_vetorial
source .venv/bin/activate
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Processamento e limpeza

```bash
docker compose up -d redis
celery -A config worker -l info
celery -A config beat -l info
```

Fallback manual:

```bash
python manage.py cleanup_expired_files
```

## Testes

```bash
.venv/bin/python manage.py test
```

Ponta a ponta (Playwright + Chromium), em banco, mídia e fila descartáveis:

```bash
cd e2e && npm install && npx playwright install chromium
./e2e/run.sh
```

O `run.sh` migra um SQLite temporário, popula um projeto de exemplo, sobe um
worker Celery e o runserver, roda a suíte e derruba tudo. Nada toca o banco, a
mídia ou a fila de produção. Screenshots e relatório ficam em `e2e/.tmp/`.

## Conformidade legal (LGPD / Marco Civil)

O app `legal` versiona os Termos de Uso e a Política de Privacidade e registra cada aceite
com data, hora, IP, navegador e o `sha256` do texto exato aceito. Como aqui as contas são
criadas por administrador e o acesso visitante está desativado, o aceite acontece pelo
interstitial de re-aceite no primeiro acesso.

Os registros de acesso do nginx são mantidos por **6 meses**, como exige o art. 15 do
Marco Civil (`deploy/logrotate/stolben-acesso` e `deploy/nginx_acesso.py`).

O procedimento completo está em [docs/CONFORMIDADE.md](docs/CONFORMIDADE.md).

```bash
./venv/bin/python manage.py importar_documentos_legais --publicar  # seed inicial
./venv/bin/python manage.py exportar_documentos_legais             # espelho em git
```

## Licença

Software **proprietário** — todos os direitos reservados (ver [LICENSE](LICENSE)).
O código não é aberto nem redistribuível; o uso do serviço é regido pelos Termos de
Uso publicados em vetorial.stolben.com.

As bibliotecas de terceiros permanecem sob suas próprias licenças; o inventário está
em [docs/LICENCAS-TERCEIROS.md](docs/LICENCAS-TERCEIROS.md), regenerável com:

```bash
./venv/bin/python scripts/licencas_terceiros.py
```

A pré-visualização de PDF chama o **`pdftoppm`** do poppler-utils (GPL-2.0) como
processo externo, sem linkagem com este código e sem distribuir o binário — a
reciprocidade da GPL não alcança o projeto. Fontes enviadas por usuários permanecem
sob a licença de seus titulares, conforme os Termos de Uso.
