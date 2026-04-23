# Sistema Vetorial

Base inicial em Django para um aplicativo web de edição de templates sobre PDF vetorial e geração de PDFs finais em lote a partir de Excel.

## Stack inicial

- Django
- SQLite no bootstrap
- Celery + Redis configurados para a próxima etapa
- openpyxl para leitura do Excel
- ReportLab para camada vetorial de texto
- pikepdf para composição sobre o PDF base
- retenção automática de 7 dias para arquivos enviados e gerados

## Estrutura atual

- `core`: home autenticada e componentes base
- `fonts`: cadastro de fontes por usuário
- `editor`: templates e campos editáveis
- `jobs`: jobs de geração e itens por linha
- `templates/`: layout inicial e tela de login

## Como rodar

```bash
cd /home/rodrigo/Projetos/sistema_vetorial
source .venv/bin/activate
cp .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Processamento assíncrono

Suba o Redis:

```bash
docker compose up -d redis
```

Suba o worker Celery:

```bash
celery -A config worker -l info
```

Suba o agendador Celery Beat:

```bash
celery -A config beat -l info
```

## Retenção de arquivos

- arquivos enviados e gerados são mantidos por 7 dias;
- após esse prazo, jobs, templates e fontes antigas são removidos automaticamente junto com seus arquivos físicos;
- o storage é privado e os arquivos não possuem URL pública direta;
- em produção, execute `celery worker` e `celery beat` para a limpeza diária automática;
- como fallback operacional, você pode rodar manualmente:

```bash
python manage.py cleanup_expired_files
```

## Próximos passos

1. Refinar o editor visual com snapping e guias.
2. Ampliar o preview com dados reais e validações tipográficas.
3. Operar Celery e Beat em produção para processamento e limpeza automática.
4. Fortalecer observabilidade e testes de interface.
