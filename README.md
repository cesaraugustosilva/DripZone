# DripZone

Projeto local do ecommerce DripZone, separado em frontend estatico e backend administrativo.

## Estrutura

- `frontend/`: loja publica, painel admin, assets estaticos e JSONs consumidos pelo site.
- `frontend/pages/`: rotas publicas preservadas em `/pages/...`.
- `frontend/admin/`: rotas administrativas preservadas em `/admin/...`.
- `frontend/assets/images/`: imagens do frontend. CSS e JavaScript ficam junto de cada pagina.
- `frontend/data/`: JSONs publicos do menu, catalogo e taxonomia.
- `backend/`: API local FastAPI, banco SQLite, migracoes, scripts e testes.
- `scripts/`: inicializadores locais do frontend, backend e ambiente completo.
- `backups/`: backups historicos criados antes de reorganizacoes ou remocoes.

Consulte `PROJECT_STRUCTURE.md` para o mapa completo.

## Como rodar

Frontend:

```powershell
.\scripts\start-frontend.ps1
```

Abra `http://127.0.0.1:4173/`.

Backend:

```powershell
.\scripts\start-backend.ps1
```

API em `http://127.0.0.1:3000/api`.

Ambos:

```powershell
.\scripts\start-development.ps1
```

## PostgreSQL Local

Foi criada uma infraestrutura inicial de PostgreSQL local com Docker Compose, sem alterar a conexao atual do backend.

- Imagem Docker: `postgres:17`.
- Container: `dripzone-postgres`.
- Volume persistente: `dripzone_postgres_data`.
- Porta padrao: `5432`, configuravel por `POSTGRES_PORT`.
- Variaveis: `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_PORT`.
- Healthcheck: `pg_isready` dentro do container.

Copie `.env.example` para `.env` quando precisar recriar o arquivo local. O `.env` da raiz e ignorado pelo Git e deve conter a senha real apenas no ambiente local.

Iniciar somente o PostgreSQL:

```powershell
docker compose up -d postgres
```

Verificar o estado:

```powershell
docker compose ps
```

Visualizar logs:

```powershell
docker compose logs -f postgres
```

Acessar pelo terminal:

```powershell
docker compose exec postgres psql -U dripzone -d dripzone
```

Esse comando considera os valores padrao do exemplo. Se `POSTGRES_USER` ou `POSTGRES_DB` forem alterados no `.env`, use os valores correspondentes.

Parar:

```powershell
docker compose stop postgres
```

Remover apenas o container, preservando o volume:

```powershell
docker compose down
```

Apagar completamente o banco local:

```powershell
docker compose down -v
```

Atenção: `docker compose down -v` remove o volume `dripzone_postgres_data` e apaga todos os dados locais do PostgreSQL.

## Producao local com containers

A infraestrutura de producao local fica em `compose.prod.yaml` e usa:

- Caddy como proxy reverso e servidor do frontend/admin;
- backend FastAPI em imagem propria, sem `--reload` e com usuario nao root;
- PostgreSQL em rede interna, sem porta publicada no host;
- volume persistente para uploads;
- `frontend/data/products.json` compartilhado para exportacao atomica do catalogo publico.

Documentacao operacional: `docs/production.md`.

Validacao basica:

```powershell
docker compose --env-file .env -f compose.prod.yaml config
docker compose --env-file .env -f compose.prod.yaml up -d --build
curl.exe -i http://127.0.0.1:8080/
curl.exe -i http://127.0.0.1:8080/api/status
curl.exe -i http://127.0.0.1:8080/data/products.json
```

Para dominio real, configure `DRIPZONE_SITE_ADDRESS`, `CORS_ORIGINS` e HTTPS conforme `deploy/caddy/Caddyfile.https.example`. Nao habilite HSTS antes de validar HTTPS em producao.

## Rotas preservadas

- Publicas: `/`, `/pages/home/`, `/pages/catalogo/`, `/pages/produto/`, `/pages/sobre/`, `/pages/contato/`.
- Admin: `/admin/`, `/admin/login/`, `/admin/produtos/`, `/admin/produtos/novo/`, `/admin/produtos/editar/`, `/admin/importacoes/`, `/admin/marcas/`, `/admin/categorias/`, `/admin/colecoes/`, `/admin/configuracoes/`.

## Dados

Os dados publicos ficam em `frontend/data/`. O catalogo publico le `frontend/data/products.json` pela URL `/data/products.json`.

O catalogo esta vazio e nao ha produtos mockados, ficticios ou demonstrativos. O backend pode exportar produtos publicados para esse JSON manualmente.

## Importacoes

O modulo de importacoes foi preservado e reformulado como pre-visualizacao controlada. Cada execucao representa exatamente uma marca cadastrada e uma URL de pasta/album permitida. A analise:

- exige marca existente;
- exige URL HTTP/HTTPS em host permitido por `IMPORT_ALLOWED_HOSTS`;
- fica limitada a pasta inicial e ignora links fora do escopo;
- percorre paginas sequencialmente ate os limites `IMPORT_MAX_PAGES` e `IMPORT_MAX_ITEMS`;
- sugere categoria, modelo, cor, nome e agrupamento de imagens por regras textuais locais;
- registra evidencias e confiancas separadas para classificacao, modelo, cor, imagens e confianca geral;
- salva imagens encontradas como `ImportImage`, uma linha por imagem, sem download;
- permite revisar manualmente dados sugeridos, selecao de imagens, capa e ordem;
- registra itens em pre-visualizacao;
- nao cria produtos, variantes, precos, estoque ou categorias.

Rotas principais:

- `POST /api/imports/preview`
- `GET /api/imports`
- `GET /api/imports/{id}`
- `GET /api/imports/{id}/items`
- `GET /api/imports/{id}/items/{item_id}`
- `PATCH /api/imports/{id}/items/{item_id}`
- `GET /api/imports/{id}/items/{item_id}/images`
- `PATCH /api/imports/{id}/items/{item_id}/images/{image_id}`
- `POST /api/imports/{id}/items/{item_id}/images/reorder`
- `GET /api/imports/{id}/items/{item_id}/images/{image_id}/ingestion-readiness`
- `POST /api/imports/{id}/items/{item_id}/images/{image_id}/ingest`
- `POST /api/imports/{id}/items/{item_id}/images/ingest-selected`
- `GET /api/imports/{id}/items/{item_id}/publication-readiness`
- `POST /api/imports/{id}/items/{item_id}/approve`
- `POST /api/imports/{id}/items/{item_id}/unapprove`
- `POST /api/imports/{id}/items/{item_id}/publish`

A listagem de itens aceita filtros de leitura por status, categoria sugerida, modelo sugerido, cor sugerida, confianca minima, revisao pendente e busca textual. Esses filtros apenas consultam a pre-visualizacao.

Durante a revisao, `ImportImage` e a fonte principal das imagens. `ImportItem.image_urls`, `ImportItem.cover_image_url` e `ImportItem.image_count` permanecem como resumos derivados para compatibilidade. O status `reviewed` significa apenas revisao manual salva; nao aprova, nao publica e nao cria produto. A API usa concorrencia otimista por `updated_at` e rejeita salvamentos sobre item alterado em outra sessao.

A publicacao do importador possui tres etapas separadas: `reviewed` indica revisao manual, `approved` indica aprovacao explicita para publicacao, e `published` indica associacao com produto criado. A aprovacao nao cria produto. A publicacao individual usa transacao, idempotencia, auditoria e checagem de duplicidade. Produtos criados pelo fluxo devem nascer como rascunho administrativo (`draft`/`hidden`), sem preco, estoque, SKU ou variante inventados.

Antes da publicacao, imagens externas selecionadas podem ser ingeridas explicitamente para `storage/uploads/imports/{import_id}/{item_id}`. A ingestao e individual ou limitada as imagens selecionadas de um item; nao existe ingestao da importacao inteira. O backend valida URL, DNS, IP, redirects, limite de bytes, MIME, assinatura real, dimensoes e hash SHA-256, bloqueando SVG/GIF/BMP/TIFF/ICO/AVIF/PDF e origens privadas. A publicacao usa somente arquivos ja ingeridos, copiando-os para `storage/uploads/products/{product_public_id}` antes de criar `ProductImage`. Nao ha publicacao automatica nem publicacao em lote.

Script local:

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\preview_import_folder.py --brand "Nike" --url "https://example.com/folder"
.\.venv\Scripts\python.exe scripts\check_import_image_ingestion.py --import-id 1 --item-id 1 --image-id 1
```

## Verificacoes

Use os comandos abaixo para validar a estrutura local:

```powershell
node --check frontend\pages\catalogo\js\menu.js
node --check frontend\pages\catalogo\js\catalog.js
cd backend
.\.venv\Scripts\python.exe -m compileall app scripts tests
.\.venv\Scripts\pytest.exe
.\.venv\Scripts\python.exe -m alembic current
```
