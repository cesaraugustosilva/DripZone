# Estrutura Do Projeto

O DripZone esta organizado para separar claramente a interface estatica da API local.

## Raiz

- `.gitignore`: regras de versionamento.
- `README.md`: guia rapido do projeto.
- `PROJECT_STRUCTURE.md`: este mapa de estrutura.
- `frontend/`: todo o frontend publico e administrativo.
- `backend/`: API local FastAPI.
- `scripts/`: comandos PowerShell de inicializacao.
- `backups/`: backups historicos.

## Frontend

- `frontend/index.html`: redireciona para `/pages/home/`.
- `frontend/pages/home/index.html`: home publica.
- `frontend/pages/catalogo/index.html`: catalogo publico.
- `frontend/pages/produto/index.html`: pagina dinamica de produto.
- `frontend/pages/sobre/index.html`: pagina sobre.
- `frontend/pages/contato/index.html`: pagina de contato.
- `frontend/pages/*.html`: redirecionamentos de compatibilidade.
- `frontend/products/`: espaco reservado existente para arquivos futuros do catalogo.
- CSS/JS publicos ficam em `css/` e `js/` dentro da pasta de cada pagina em `frontend/pages/...`.
- `frontend/assets/images/`: imagens publicas.
- `frontend/data/`: JSONs estaticos da loja publica.

## Admin

- `frontend/admin/index.html`: dashboard administrativo.
- `frontend/admin/login/index.html`: login.
- `frontend/admin/produtos/index.html`: lista de produtos.
- `frontend/admin/produtos/novo/index.html`: criacao de produto.
- `frontend/admin/produtos/editar/index.html`: edicao de produto.
- `frontend/admin/importacoes/index.html`: pre-visualizacao de importacao por uma pasta.
- `frontend/admin/marcas/index.html`: marcas.
- `frontend/admin/categorias/index.html`: categorias.
- `frontend/admin/colecoes/index.html`: colecoes.
- `frontend/admin/configuracoes/index.html`: configuracoes.
- CSS/JS do admin ficam em `css/` e `js/` dentro da pasta de cada rota administrativa.

## Backend

- `backend/app/`: aplicacao FastAPI.
- `backend/app/api/routes/imports.py`: API administrativa de pre-visualizacao de importacoes.
- `backend/app/services/imports.py`: validacao de URL, escopo, scanner sequencial e classificacao textual.
- `backend/app/services/import_review.py`: revisao manual de itens e imagens de importacao, sincronizacao dos resumos e concorrencia otimista.
- `backend/app/services/import_image_ingestion.py`: ingestao segura e explicita de imagens externas para storage local.
- `backend/app/services/import_publish.py`: prontidao, aprovacao e publicacao individual controlada de itens revisados.
- `backend/app/services/import_rules.py`: regras locais de categoria, modelo, cor e agrupamento textual.
- `backend/app/schemas/imports.py`: contratos da API de importacoes.
- `backend/alembic/`: migracoes.
- `backend/tests/fixtures/imports/`: HTML ficticio usado pelos testes do importador, sem imagens reais.
- `backend/scripts/`: utilitarios locais do backend, incluindo verificacao de prontidao de ingestao.
- `backend/tests/`: testes automatizados.
- `backend/storage/`: banco local e uploads ignorados pelo Git.
- `backend/requirements.txt`: dependencias Python.
- `backend/run.py`: entrada local do servidor.

## Servidores Locais

- Frontend: raiz estatica em `frontend/`, porta padrao `4173`.
- Backend: raiz de execucao em `backend/`, porta padrao `3000`.

Essa escolha preserva as URLs publicas e administrativas sem prefixo extra de pasta.
