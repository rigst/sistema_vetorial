# Conformidade legal — LGPD e Marco Civil

Como o StölbenVetorial registra o aceite dos termos, por quanto tempo guarda os
registros de acesso e o que fazer para publicar uma versão nova das políticas.

## 1. Registro de aceite

O app `legal` guarda dois modelos.

**`DocumentoLegal`** — uma linha por *versão* de cada documento. Ciclo de vida:
`rascunho` → `publicado` → `arquivado`. Ao publicar, o sistema congela o HTML renderizado
e o `sha256` do texto; a partir daí a versão é imutável.

**`AceiteLegal`** — a prova: qual versão, quem (com identificação congelada), se era
visitante, IP, navegador, data, sessão, origem, o hash do texto **no momento do aceite** e
um JSON de evidência (host, path, método, `Referer`, `X-Forwarded-For` bruto, idioma e as
versões vigentes na hora).

O ponto mais importante do desenho: **o aceite sobrevive à exclusão do usuário.**
`core/cleanup.py:cleanup_visitor_data` apaga o usuário visitante no logout — e o mesmo
módulo, via `cleanup_expired_visitors`, apaga por tempo (`VISITOR_ACCOUNT_TTL_HOURS`) uma
sessão de visitante abandonada sem logout explícito. A prova não pode ir junto — daí
`usuario` ser `SET_NULL` e existir o `usuario_label` congelado.

### Onde o aceite é capturado

- **Acesso visitante:** tela pública `/legal/aceite/` (link "Experimentar sem criar
  conta" no login). O aceite é validado e registrado por `core.views.criar_visitante` —
  o destino configurado em `LEGAL_VISITOR_ACTION` — **antes** de a conta existir; só
  depois do aceite válido a conta de visitante é criada, logada e fica sujeita à
  expiração automática (`core.cleanup.cleanup_expired_visitors`, `VISITOR_ACCOUNT_TTL_HOURS`,
  além da exclusão imediata ao sair).
- **Cadastro:** não existe. As contas permanentes são criadas por administrador, e o
  aceite dessas contas acontece pelo interstitial de re-aceite no primeiro acesso.
- **Login normal**: sem checkbox. Quem já tem conta já aceitou; versão nova é tratada pelo
  middleware.
- **Versão nova** (`legal/middleware.py`): `AceiteObrigatorioMiddleware` redireciona
  qualquer usuário autenticado com aceite pendente para `/legal/reaceite/`, liberando só
  as rotas da allowlist. Ele entra **antes** do `VisitorExpiryMiddleware`.

O checkbox nasce sempre desmarcado (`initial=False`) e é obrigatório no **servidor**
(`required=True`) — burlar o HTML no navegador não passa pela validação do formulário.

### Extrair evidência

No admin, em *Conformidade legal → Aceites*: filtre por documento, versão, origem ou data
e use **"Exportar seleção em CSV"**. O CSV traz o hash gravado no aceite e o hash atual do
documento lado a lado, mais a coluna `integro` — se divergirem, o texto foi alterado
depois do aceite.

O próprio usuário consulta seus aceites em `/legal/meus-aceites/` (LGPD art. 18).
`AceiteLegal` é somente leitura no admin.

## 2. Publicar uma versão nova das políticas

O **banco é a fonte da verdade**; `legal/documentos/<tipo>/<versao>.md` é o espelho em git.

1. No admin, em *Documentos legais*, selecione a versão vigente e rode
   **"Duplicar como nova versão (rascunho)"**.
2. Edite o rascunho em Markdown; *Pré-visualização* mostra o resultado sanitizado.
3. Marque **mudança material** se todos devem aceitar de novo.
4. Selecione o rascunho e rode **"Publicar rascunhos selecionados"**.
5. Espelhe em git:
   ```bash
   ./venv/bin/python manage.py exportar_documentos_legais
   git add legal/documentos && git commit -m "Publica <documento> vX.Y"
   ```

A publicação só existe como **ação da changelist**, nunca como link: ação de admin já vem
como POST com CSRF.

Versão publicada não é editável nem apagável, nem antes do primeiro aceite — no instante
em que vai ao ar já está sendo exibida. Para mudar o texto, publique outra versão.
`importar_documentos_legais` **recusa** sobrescrever versão existente cujo texto tenha
mudado.

## 3. Guarda dos registros de acesso (6 meses)

O art. 15 do Marco Civil da Internet exige 6 meses. Quem cumpre é o nginx.

Este site já grava em `/var/log/nginx/acesso/vetorial.access.log`, e a rotação de 200 dias
está em `/etc/logrotate.d/stolben-acesso`. Para reinstalar ou replicar:

```bash
sudo install -d -o root -g adm -m 0755 /var/log/nginx/acesso
sudo cp deploy/logrotate/stolben-acesso /etc/logrotate.d/stolben-acesso
sudo python3 deploy/nginx_acesso.py --dry-run
sudo python3 deploy/nginx_acesso.py && sudo nginx -t && sudo systemctl reload nginx
```

O subdiretório `acesso/` evita colidir com o `/etc/logrotate.d/nginx` do sistema, que
rotaciona `/var/log/nginx/*.log` a cada 14 dias — o glob não é recursivo.

O `X-Forwarded-For` é lido pelo **último** item, em `legal/utils.py:ip_do_request()`:
atrás do nginx, esse é o IP que ele observou; os anteriores vieram do cliente e são
forjáveis.

## 4. Checklist de deploy

```bash
./venv/bin/python manage.py migrate
./venv/bin/python manage.py importar_documentos_legais --publicar   # só na 1ª vez
./venv/bin/python manage.py collectstatic --noinput                 # unfold traz estáticos
sudo systemctl reload sistema_vetorial_gunicorn
```

`collectstatic` precisa das variáveis de produção: o app usa
`ManifestStaticFilesStorage`, e um estático fora do manifesto derruba a página com 500.

## 5. Política de Segurança de Conteúdo no admin

O `/admin/` recebe uma CSP própria, com `'unsafe-eval'`, porque o tema (django-unfold)
usa Alpine.js, que compila as expressões de `x-data`/`x-init` com `new Function()`. O
`'unsafe-inline'` da política pública **não** cobre `eval`. Ver `config/middleware.py` e
`CONTENT_SECURITY_POLICY_ADMIN` em `config/settings.py`.
