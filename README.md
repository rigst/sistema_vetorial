# StölbenVetorial

Sistema Django para edição visual de templates em PDF e geração de arquivos por lote a partir de Excel.

## Principais recursos

- login com acesso visitante temporário;
- exclusão automática dos dados do visitante ao sair;
- templates com fundo em PDF de uma página ou imagem (PNG/JPG/WebP, convertida para PDF);
- editor visual baseado em Fabric.js: arraste, redimensione, gire, multi-seleção, snap com guias, zoom, undo/redo, atalhos de teclado e edição de texto com duplo clique;
- pré-visualização fiel: as fontes do usuário são carregadas no navegador e a métrica de texto do editor é replicada na geração do PDF;
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
