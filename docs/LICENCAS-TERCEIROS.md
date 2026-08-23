# Licenças de terceiros — StölbenVetorial

Gerado por `scripts/licencas_terceiros.py` em 2026-08-23 a partir dos pacotes instalados no venv de produção.
Para regenerar: `./venv/bin/python scripts/licencas_terceiros.py`.

O código deste projeto é licenciado sob **AGPL-3.0-or-later** (ver `LICENSE`). As bibliotecas abaixo permanecem sob suas licenças originais.

## Dependências diretas

| Pacote | Versão | Licença |
|---|---|---|
| celery | 5.6.3 | BSD-3-Clause |
| Django | 6.0.8 | BSD-3-Clause |
| django-unfold | 0.101.0 | MIT |
| fonttools | 4.62.1 | MIT |
| Markdown | 3.10.2 | BSD-3-Clause |
| nh3 | 0.3.6 | MIT |
| openpyxl | 3.1.5 | MIT License |
| pikepdf | 10.5.1 | MPL-2.0 |
| pillow | 12.3.0 | MIT-CMU |
| redis | 7.4.0 | MIT |
| reportlab | 4.4.10 | BSD License |

## Dependências transitivas

| Pacote | Versão | Licença |
|---|---|---|
| amqp | 5.3.1 | BSD License |
| asgiref | 3.11.1 | BSD License |
| billiard | 4.2.4 | BSD License |
| charset-normalizer | 3.4.7 | MIT |
| click | 8.3.3 | BSD-3-Clause |
| click-didyoumean | 0.3.1 | MIT License |
| click-plugins | 1.1.1.2 | BSD License |
| click-repl | 0.3.0 | MIT |
| Deprecated | 1.3.1 | MIT License |
| et_xmlfile | 2.0.0 | MIT License |
| gunicorn | 25.3.0 | MIT |
| kombu | 5.6.2 | BSD-3-Clause |
| lxml | 6.1.0 | BSD-3-Clause |
| packaging | 26.1 | Apache-2.0 OR BSD-2-Clause |
| prompt_toolkit | 3.0.52 | BSD License |
| psycopg | 3.3.3 | LGPL-3.0-only |
| psycopg-binary | 3.3.3 | LGPL-3.0-only |
| python-dateutil | 2.9.0.post0 | BSD License / Apache Software License |
| six | 1.17.0 | MIT License |
| sqlparse | 0.6.0 | BSD License |
| typing_extensions | 4.15.0 | PSF-2.0 |
| tzdata | 2026.1 | Apache-2.0 |
| tzlocal | 5.3.1 | MIT License |
| vine | 5.1.0 | BSD License |
| wcwidth | 0.6.0 | MIT |
| wrapt | 2.1.2 | BSD-2-Clause |

## Programas externos

Invocados por `subprocess` como processos separados — não são linkados ao código deste projeto.

| Programa | Versão | Licença | Observação |
|---|---|---|---|
| poppler-utils (`pdftoppm`) | 24.02.0 | GPL-2.0 | Pré-visualização de PDF, chamado em `editor/services.py` |

## Fontes vendorizadas

Arquivos de fonte embutidos no repositório como builtins do editor (`fonts/vendor/`), fora do inventário de pacotes Python acima.

| Fonte | Licença | Observação |
|---|---|---|
| Inter | SIL OFL 1.1 | `fonts/vendor/inter/` — texto completo em `LICENSE.txt` no mesmo diretório |
| Wix Madefor Display | SIL OFL 1.1 | `fonts/vendor/wix-madefor-display/` — texto completo em `OFL.txt` no mesmo diretório |

## Componentes com licença recíproca (copyleft)

Listados para conferência ao redistribuir o código ou ao combinar com componentes fechados. O uso como biblioteca, sem modificação e sem distribuição do binário, não propaga obrigações de abertura.

| Pacote | Versão | Licença |
|---|---|---|
| pikepdf | 10.5.1 | MPL-2.0 |
| psycopg | 3.3.3 | LGPL-3.0-only |
| psycopg-binary | 3.3.3 | LGPL-3.0-only |

## Notas de manutenção

- **Redis**: o servidor em uso é a série 7.0 (BSD-3-Clause). As versões 7.4 a 7.9 passaram a ser RSALv2/SSPL, que não são licenças livres segundo a OSI. Ao atualizar o servidor, reveja esta seção e a página de licenças do site.
- Os programas externos acima rodam como processos separados, invocados por linha de comando. Não há linkagem com o código deste projeto, e o serviço não distribui os binários — por isso as obrigações de reciprocidade da GPL não se estendem a este código.
- A SIL OFL 1.1 permite embutir e redistribuir a fonte junto com software sob qualquer licença, inclusive AGPL — a única restrição relevante aqui é não vender a fonte isoladamente, o que este projeto não faz.
