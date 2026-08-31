"""Utilidades compartilhadas pela suíte de testes."""

import secrets

# Sorteada uma vez por processo de teste, em vez de literal no código-fonte —
# o SonarCloud aponta senha hardcoded mesmo em teste, e não há motivo real
# para o valor ser fixo: nenhum teste depende do conteúdo, só de existir.
SENHA_TESTE = secrets.token_urlsafe(16)
