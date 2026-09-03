# StölbenVetorial

[![CI](https://github.com/rigst/sistema_vetorial/actions/workflows/ci.yml/badge.svg)](https://github.com/rigst/sistema_vetorial/actions/workflows/ci.yml)
[![Quality Gate](https://sonarcloud.io/api/project_badges/measure?project=rigst_sistema_vetorial&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=rigst_sistema_vetorial)
[![Licença: AGPL v3](https://img.shields.io/badge/licen%C3%A7a-AGPL--3.0-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![Django 6](https://img.shields.io/badge/django-6.0-092E20.svg)](https://www.djangoproject.com/)

Sistema Django para edição visual de templates em PDF e geração de arquivos por lote a partir de Excel.

## Principais recursos

- login com acesso visitante temporário;
- exclusão automática dos dados do visitante ao sair, ou por tempo (`VISITOR_ACCOUNT_TTL_HOURS`);
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
python manage.py cleanup_expired_visitors
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

## Deploy contínuo

O merge de um PR em `main` que passar no CI é implantado sozinho em produção via
`.github/workflows/deploy.yml` + `deploy/cd-deploy.sh` — o workflow
reutilizável `deploy-django.yml` do `rigst/ci` dispara o script por SSH.
A branch `main` tem proteção ativa (checks obrigatórios, sem push direto nem
pra admin); mudanças sempre entram por PR, sem exigir aprovação de terceiros.
Procedimento completo, geração de chave e rollback manual: RUNBOOK.md do
`rigst/ci`, seção 7.

## Conformidade legal (LGPD / Marco Civil)

O app `legal` versiona os Termos de Uso e a Política de Privacidade e registra cada aceite
com data, hora, IP, navegador e o `sha256` do texto exato aceito. Contas criadas por
administrador aceitam pelo interstitial de re-aceite no primeiro acesso; o acesso
visitante (autoatendido, na tela de login) aceita antes mesmo de a conta existir, na
tela `/legal/aceite/`.

Os registros de acesso do nginx são mantidos por **6 meses**, como exige o art. 15 do
Marco Civil (`deploy/logrotate/stolben-acesso` e `deploy/nginx_acesso.py`).

O procedimento completo está em [docs/CONFORMIDADE.md](docs/CONFORMIDADE.md).

```bash
./venv/bin/python manage.py importar_documentos_legais --publicar  # seed inicial
./venv/bin/python manage.py exportar_documentos_legais             # espelho em git
```

## Licença

[AGPL-3.0](LICENSE) — Copyright (C) 2026 Rodrigo Caballero Stölben. Código-fonte:
[github.com/rigst/sistema_vetorial](https://github.com/rigst/sistema_vetorial).

O uso do serviço hospedado em vetorial.stolben.com é regido também pelos Termos de Uso
e pela Política de Privacidade publicados no próprio serviço. Fontes tipográficas
enviadas pelos usuários permanecem sob a licença de seus respectivos titulares.

As bibliotecas de terceiros (e as fontes vendorizadas em `fonts/vendor/`) permanecem
sob suas próprias licenças; o inventário está em
[docs/LICENCAS-TERCEIROS.md](docs/LICENCAS-TERCEIROS.md), regenerável com:

```bash
./venv/bin/python scripts/licencas_terceiros.py
```

A pré-visualização de PDF chama o **`pdftoppm`** do poppler-utils (GPL-2.0) como
processo externo, sem linkagem com este código e sem distribuir o binário — a
reciprocidade da GPL não alcança o projeto. Fontes enviadas por usuários permanecem
sob a licença de seus titulares, conforme os Termos de Uso.
