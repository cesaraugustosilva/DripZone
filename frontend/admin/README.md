# Admin DripZone

Area administrativa estatica conectada ao backend local FastAPI do DripZone.

## Estado Atual

- Acesse em `/admin/`.
- API local padrao: `http://127.0.0.1:3000/api` ou `http://localhost:3000/api`, conforme o host do frontend.
- A URL da API fica centralizada em `frontend/admin/js/config.js`.
- O login usa sessao real por cookie `HttpOnly`.
- Operacoes mutaveis usam CSRF via `X-CSRF-Token`.
- O painel depende do servidor FastAPI para autenticacao e dados administrativos.
- Preferencias visuais do navegador podem continuar no `localStorage`; sessao e senha nunca sao salvas ali.

## Rotas

- `/admin/`
- `/admin/login/`
- `/admin/produtos/`
- `/admin/produtos/novo/`
- `/admin/produtos/editar/?id=produto-inexistente`
- `/admin/importacoes/`
- `/admin/marcas/`
- `/admin/categorias/`
- `/admin/colecoes/`
- `/admin/configuracoes/`

## Assets

- Cada rota administrativa mantem seus arquivos CSS e JavaScript em subpastas locais ao lado do respectivo `index.html`.
- Exemplo: `/admin/login/` carrega `./css/admin.css`, `./css/responsive.css` e `./js/auth.js` da propria pasta `frontend/admin/login/`.

## API

Endpoints principais:

- `GET /api/products`
- `POST /api/products`
- `GET /api/products/:id`
- `PUT /api/products/:id`
- `DELETE /api/products/:id`
- `GET /api/brands`
- `POST /api/brands`
- `GET /api/categories`
- `POST /api/categories`
- `GET /api/collections`
- `POST /api/collections`
- `GET /api/settings`
- `PUT /api/settings`

## Limitacoes Locais

- O backend e local e usa PostgreSQL via Docker.
- Uploads sao locais em `backend/storage/uploads`.
- A loja publica continua independente do backend ate exportacao manual.
