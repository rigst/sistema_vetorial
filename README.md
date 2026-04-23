# Sistema Vetorial

Base inicial em Django para um aplicativo web de edição de templates sobre PDF vetorial e geração de PDFs finais em lote a partir de Excel.

## Stack inicial

- Django
- SQLite no bootstrap
- Celery + Redis configurados para a próxima etapa
- openpyxl para leitura do Excel
- ReportLab para camada vetorial de texto
- pikepdf para composição sobre o PDF base

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
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Próximos passos

1. Implementar CRUD web de templates e fontes.
2. Construir o editor visual com preview do PDF e campos arrastáveis.
3. Ler o Excel, mapear colunas pelo cabeçalho e gerar amostra com 3 linhas.
4. Executar a geração completa por Celery e consolidar ZIP final.
