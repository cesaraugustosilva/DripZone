# DripZone Admin API

Backend local FastAPI para a area administrativa do DripZone.

## Requisitos

- Python 3.14 usado neste ambiente.
- SQLite local preservado.
- PostgreSQL local opcional via Docker Compose na raiz do projeto.
- Execucao local em `http://127.0.0.1:3000`.

## Instalacao

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env
python -m alembic upgrade head
python scripts/create_admin.py
python run.py
```

Tambem e possivel iniciar pela raiz:

```powershell
.\scripts\start-backend.ps1
```

## URLs

- API: `http://127.0.0.1:3000/api`
- Docs: `http://127.0.0.1:3000/docs`
- ReDoc: `http://127.0.0.1:3000/redoc`
- Admin: servido pelo frontend estatico em `/admin/`

## Seguranca

O backend usa cookie de sessao `HttpOnly`, assinatura com `itsdangerous`, CSRF por header `X-CSRF-Token`, CORS restrito a origens locais e senha com hash `bcrypt`.

Em desenvolvimento, configure `CORS_ORIGINS` com origens explicitas do frontend administrativo, separadas por virgula. Com `credentials: "include"`, nao use curinga:

```env
CORS_ORIGINS=http://127.0.0.1:4173,http://localhost:4173,http://127.0.0.1:4199,http://localhost:4199
```

Este backend e local. Nao exponha publicamente sem configurar HTTPS, segredos reais, politica de cookies de producao, backup, observabilidade e protecao perimetral.

## Banco De Dados

O backend le `DATABASE_URL` pelo arquivo local `backend/.env`.

Para PostgreSQL local em Docker, use o formato:

```env
DATABASE_URL=postgresql+psycopg://dripzone:SENHA@127.0.0.1:5432/dripzone
```

O arquivo versionavel `backend/.env.example` usa senha de exemplo. A senha real deve ficar apenas em `backend/.env`, que e ignorado pelo Git.

O suporte a SQLite continua preservado. Para voltar temporariamente ao SQLite, ajuste `DATABASE_URL` para:

```env
DATABASE_URL=sqlite:///./storage/database/dripzone.db
```

Teste a conexao configurada sem criar tabelas ou aplicar migracoes:

```powershell
python scripts/check_database_connection.py
```

## Migracoes

```powershell
python -m alembic upgrade head
python -m alembic downgrade base
```

## Importacoes De Pasta

O modulo de importacoes trabalha nesta etapa somente em modo de pre-visualizacao. A unidade de trabalho e:

```text
uma marca cadastrada + uma URL de pasta/album + uma execucao
```

A API nao cria marcas automaticamente e nao cria produtos reais. O usuario informa `brand_id` ou uma marca existente, e a URL e validada contra `IMPORT_ALLOWED_HOSTS` para hosts exatos e `IMPORT_ALLOWED_DOMAINS` para dominio raiz e subdominios. URLs locais, IPs privados, `localhost`, `file://` e redirecionamentos para hosts nao permitidos sao bloqueados.

Configuracoes:

- `IMPORT_ALLOWED_HOSTS`: hosts exatos permitidos para coleta. `example.com` deve ficar restrito a desenvolvimento/testes.
- `IMPORT_ALLOWED_DOMAINS`: dominios permitidos para coleta com subdominios. Exemplo: `yupoo.com` permite `yupoo.com` e `*.yupoo.com`.
- `IMPORT_MAX_PAGES`: limite de paginas por pasta.
- `IMPORT_MAX_ITEMS`: limite de itens por execucao.
- `IMPORT_REQUEST_TIMEOUT`: timeout por requisicao.
- `IMPORT_REQUEST_DELAY`: intervalo sequencial entre requisicoes.
- `IMPORT_MAX_RETRIES`: tentativas controladas.
- `IMPORT_MAX_RESPONSE_BYTES`: tamanho maximo de resposta HTML.
- `IMPORT_USER_AGENT`: user-agent identificavel.

Endpoints:

```http
POST /api/imports/preview
GET /api/imports
GET /api/imports/{import_id}
GET /api/imports/{import_id}/items
GET /api/imports/{import_id}/items/{item_id}
PATCH /api/imports/{import_id}/items/{item_id}
GET /api/imports/{import_id}/items/{item_id}/images
PATCH /api/imports/{import_id}/items/{item_id}/images/{image_id}
POST /api/imports/{import_id}/items/{item_id}/images/reorder
GET /api/imports/{import_id}/items/{item_id}/images/{image_id}/ingestion-readiness
POST /api/imports/{import_id}/items/{item_id}/images/{image_id}/ingest
POST /api/imports/{import_id}/items/{item_id}/images/ingest-selected
GET /api/imports/{import_id}/items/{item_id}/publication-readiness
POST /api/imports/{import_id}/items/{item_id}/approve
POST /api/imports/{import_id}/items/{item_id}/unapprove
POST /api/imports/{import_id}/items/{item_id}/publish
POST /api/imports/{import_id}/cancel
DELETE /api/imports/{import_id}
```

Estados de importacao: `draft`, `scanning`, `preview_ready`, `failed`, `cancelled`.

Estados de itens: `pending`, `duplicate`, `needs_review`, `invalid`, `reviewed`, `approved`, `publishing`, `published`, `publish_failed`.

Estados de imagens: `active`, `ignored`, `duplicate`, `invalid`.

Estados de ingestao de imagens: `not_requested`, `downloading`, `validating`, `stored`, `failed`, `skipped`.

O scanner usa somente textos e estrutura HTML: titulo, links, slug, URL, alt/title de imagens e metadados basicos. Ele sugere categoria, modelo, cor e nome por regras textuais locais, agrupa imagens por evidencia textual, descarta imagens decorativas comuns e grava confiancas separadas para classificacao, modelo, cor, imagens e resultado geral. Duplicidade basica considera a mesma marca com a mesma URL normalizada e itens repetidos na mesma execucao.

`GET /api/imports/{import_id}/items` aceita filtros de leitura por status, categoria sugerida, modelo sugerido, cor sugerida, confianca minima, revisao pendente e busca textual. Esses filtros nao alteram itens.

`ImportImage` e a fonte principal das imagens durante revisao. Cada imagem pertence a um `ImportItem`, possui ordem iniciando em zero, status, selecao, capa opcional, alt text, dimensoes quando vierem do HTML, avisos e metadados auxiliares em `image_metadata`. Os campos legados `image_urls`, `cover_image_url` e `image_count` em `ImportItem` continuam como resumos derivados e sao sincronizados na mesma transacao.

A revisao manual permite editar somente dados sugeridos do item, selecionar/desmarcar imagens, definir capa, ignorar/restaurar e reordenar. O status `reviewed` registra apenas que os dados foram revisados manualmente; nao significa aprovado, publicado ou pronto para criacao de produto. Nao ha upload manual, recorte, reconhecimento visual, preco, estoque ou publicacao automatica nesta etapa.

As rotas mutaveis exigem autenticacao, autorizacao, CSRF, pertencimento do item/imagem a importacao e importacao em estado editavel. A concorrencia otimista usa o `updated_at` conhecido pelo frontend e responde `409` quando o item foi alterado por outra sessao. Alteracoes de imagem sincronizam capa, selecao, ordem e resumos em uma unica transacao.

Estados de publicacao de itens: `approved`, `publishing`, `published`, `publish_failed`.

Aprovacao e publicacao sao acoes separadas. Aprovar um item exige dados revisados e registra `approved_by_id`/`approved_at`, mas nao cria produto. Cancelar aprovacao so e permitido antes da publicacao. A publicacao individual e idempotente, usa lock transacional quando suportado pelo banco, valida duplicidade e registra auditoria de inicio, sucesso, falha ou chamada repetida.

Produtos criados por importacao devem nascer como rascunho administrativo: `status=draft`, `visibility=hidden`, `availability=unavailable`, `track_inventory=false`, sem SKU, sem estoque inventado, sem variantes e sem preco comercial inventado. O campo tecnico `price` do modelo permanece `0.00` somente porque o schema atual exige valor numerico tambem para rascunho.

`ProductImage` exige arquivo local (`filename`, `storage_path`, `mime_type`, `size_bytes`, `width`, `height`). Por isso, imagens externas selecionadas precisam ser ingeridas explicitamente antes da publicacao. A ingestao baixa somente uma imagem solicitada ou as imagens selecionadas de um item, nunca a importacao inteira. O arquivo e recebido por streaming, limitado por `IMPORT_IMAGE_MAX_BYTES`, validado por DNS/IP/SSRF, redirect, MIME permitido, assinatura real via Pillow, dimensoes e limite de pixels. SVG, GIF, BMP, TIFF, ICO, AVIF, PDF, `file://`, `data:` e origens privadas sao bloqueados nesta fase.

Os arquivos ingeridos ficam em `storage/uploads/imports/{import_id}/{item_id}/{sha256}.{ext}` com nome derivado do hash, sem usar nome remoto. `content_sha256` permite idempotencia e deduplicacao dentro do item. Se uma imagem ja estiver `stored` e o arquivo existir com o mesmo hash, a API nao baixa novamente. Erros persistem como codigos seguros em `ingestion_error`, sem registrar stack trace, cookies, headers completos ou corpo remoto.

Na publicacao individual, `ImportImage.local_*` e usado para criar `ProductImage`. O arquivo ingerido e copiado para `storage/uploads/products/{product_public_id}` para evitar produto apontando para area temporaria do importador. A publicacao nao baixa novamente, nao inventa SKU, preco comercial, estoque ou variantes.

Nao ha publicacao automatica ao concluir scanner, salvar revisao ou aprovar. Nao ha publicacao em lote nesta fase.

Script local:

```powershell
python scripts/preview_import_folder.py --brand "Nike" --url "https://example.com/folder"
python scripts/check_import_image_ingestion.py --import-id 1 --item-id 1 --image-id 1
```

O script de preview mostra o escopo e pede confirmacao antes de fazer requisicoes. O script de ingestao acima e somente prontidao por padrao. Nao informe senhas ou segredos por argumento.

## Catalogo Local Por Terminal

A nova arquitetura de catalogo local importa uma pasta/album Yupoo para arquivos em `backend/catalog`, sem criar `ImportRecord`, `ImportItem`, `ImportImage`, produtos no banco ou publicacoes.

Exemplo interativo:

```powershell
python scripts/import_catalog.py
```

Exemplo com argumentos em uma linha no PowerShell:

```powershell
python scripts/import_catalog.py --brand "Nike" --url "https://example.com/folder" --catalog-path "catalog" --dry-run --max-products 5 --skip-ai
```

Opcoes iniciais: `--brand`, `--url`, `--catalog-path`, `--dry-run`, `--force`, `--skip-ai`, `--max-products`, `--concurrency` e `--verbose`. Nesta primeira versao, `--skip-ai` usa o fallback deterministico e `--concurrency` fica reservado.

Estrutura gerada:

```text
backend/catalog/
  _runs/{run_id}.json
  _runs/{run_id}.log
  {marca_slug}/_metadata.json
  {marca_slug}/{categoria_slug}/{nome_slug}-{source_id_curto}/product.json
  {marca_slug}/{categoria_slug}/{nome_slug}-{source_id_curto}/cover.{ext}
```

Categorias usadas pelo catalogo local: `camisetas`, `calcas`, `moletons`, `jaquetas`, `shorts`, `conjuntos`, `acessorios`, `calcados` e `desconhecidos`. A categoria real `Tenis` do projeto e normalizada para `calcados` nesta biblioteca local.

## Migracao SQLite Para PostgreSQL

O script `scripts/migrate_sqlite_to_postgres.py` transfere dados reais do SQLite local para o PostgreSQL configurado em `backend/.env`.

Requisitos:

- PostgreSQL acessivel e com a revision Alembic `20260724_0002`.
- Schema PostgreSQL ja criado por `python -m alembic upgrade head`.
- Backup recente do SQLite preservado em `backups/database/`.
- Destino PostgreSQL vazio nas tabelas de aplicacao.

Dry run obrigatorio:

```powershell
python scripts/migrate_sqlite_to_postgres.py --source storage/database/dripzone.db --dry-run
```

Execucao real:

```powershell
python scripts/migrate_sqlite_to_postgres.py --source storage/database/dripzone.db --execute
```

Sem `--dry-run` ou `--execute`, o script mostra ajuda e encerra sem alterar dados.

O dry run abre os dois bancos, valida a revision Alembic, compara tabelas e colunas esperadas, conta registros, executa `PRAGMA foreign_key_check`, procura orfaos, simula conversoes e mostra a ordem planejada. Ele nao escreve no PostgreSQL.

A execucao real usa uma unica transacao no PostgreSQL. Em falha, a transacao e revertida integralmente. O script nao executa `DROP`, `TRUNCATE`, `DELETE`, `stamp`, `downgrade`, merge, upsert ou overwrite.

IDs, foreign keys, datas, valores monetarios, JSON, flags booleanas e hashes de senha sao preservados quando possivel. Hashes nao sao exibidos nos logs. Como IDs sao inseridos explicitamente, as sequences PostgreSQL sao ajustadas ao maior ID existente em cada tabela com registros.

Se qualquer tabela de aplicacao do PostgreSQL ja possuir dados, o script interrompe para evitar duplicidade. Para validar apos a migracao:

```powershell
python scripts/check_database_connection.py
python -m pytest
```

Mantenha o SQLite original e o backup preservados ate a migracao ser revisada.

## Primeiro Administrador

Crie com:

```powershell
python scripts/create_admin.py --name "Administrador DripZone" --email "admin@exemplo.com" --role owner
```

O script solicita a senha de forma oculta:

```text
Senha:
Confirme a senha:
```

Parametros:

- `--name`: nome exibido no painel.
- `--email`: e-mail usado no login.
- `--role`: `owner`, `admin` ou `editor`.

Use `owner` para o primeiro administrador. A senha deve ter pelo menos 12 caracteres, com letra maiuscula, letra minuscula, numero e caractere especial.

Nao passe senha na linha de comando, nao grave senha no README, nao versionar `.env` e nao compartilhe hashes. Se o e-mail ja existir, o script interrompe com erro e nao altera o administrador existente.

Depois de criar o administrador, inicie o backend e acesse o painel pelo frontend local:

```powershell
.\scripts\start-backend.ps1
.\scripts\start-frontend.ps1
```

Painel: `http://127.0.0.1:4173/admin/login/`.

Nao ha usuario ou senha padrao no codigo.

## Redefinir Senha De Administrador

Use o script abaixo para redefinir localmente a senha de um administrador existente:

```powershell
python scripts/reset_admin_password.py --email "admin@exemplo.com"
```

O script valida o e-mail com a mesma regra usada pela API, localiza exatamente um administrador, mostra dados seguros e pede confirmacao antes de alterar o banco:

```text
Nova senha:
Confirme a nova senha:
Confirmar redefinicao? [s/N]:
```

A senha deve ter pelo menos 12 caracteres, com letra maiuscula, letra minuscula, numero e caractere especial. Ela nao pode ser igual ao e-mail, ao nome do administrador ou a senha atual.

O script atualiza `password_hash`, `session_version` e `updated_at`, usando a funcao oficial de hash `bcrypt` da aplicacao. ID, nome, e-mail, role, status, `created_at` e `last_login_at` sao preservados.

Se o e-mail nao existir, se o formato for invalido, se a senha for fraca, se a confirmacao divergir ou se a resposta de confirmacao nao for `s` ou `sim`, o script faz rollback e encerra sem alterar o administrador.

A redefinicao da senha incrementa `session_version` e invalida sessoes ja emitidas para esse administrador. As sessoes atuais sao cookies assinados que carregam o ID do usuario, a versao de sessao e o token CSRF; nao ha tabela de sessoes nesta arquitetura local.

Para validar depois da redefinicao:

```powershell
python scripts/check_database_connection.py
python run.py
```

Em seguida, acesse `http://127.0.0.1:4173/admin/login/` pelo frontend local e faca login com a nova senha.

Nunca passe senha por argumento, arquivo ou README. Mantenha `.env` e `backend/.env` ignorados pelo Git e nao compartilhe hashes.

## Recursos Locais

O utilitario abaixo le os JSONs publicos em `frontend/data/`, sem produtos mockados, e pode fazer dry-run:

```powershell
python scripts/import_existing_resources.py --dry-run
python scripts/import_existing_resources.py
```

Ele nao cria dados ficticios e nao executa automaticamente.

## Exportacao Para A Loja Publica

`POST /api/products/export` exporta produtos publicados e visiveis para `frontend/data/products.json` de forma manual. O servico gera backup do JSON anterior e escreve de forma atomica.

## Arquivos Locais Nao Versionados

Nao versionar `.env`, banco SQLite, uploads, `.venv`, caches, relatorios de cobertura e backups locais.
