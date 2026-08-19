# Frontend DripZone

Esta pasta contem toda a camada estatica do DripZone: loja publica, painel admin, assets e JSONs publicos.

## Conteudo

- `index.html`: redirecionamento para `/pages/home/`.
- `pages/`: paginas publicas.
- `admin/`: area administrativa.
- `assets/`: CSS, JavaScript e imagens.
- `data/`: JSONs consumidos pelo menu, catalogo e pagina de produto.
- `manifest.json`, `robots.txt`, `sitemap.xml`: arquivos publicos da raiz estatica.

## Execucao

Na raiz do projeto:

```powershell
.\scripts\start-frontend.ps1
```

Acesse `http://127.0.0.1:4173/`.

## Observacoes

A raiz servida deve ser `frontend/`. Assim, `/pages/home/`, `/admin/`, `/assets/...` e `/data/...` continuam funcionando sem mudanca de URL.
