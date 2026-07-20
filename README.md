# DripZone

Site estático profissional para a marca streetwear DripZone.

## Tecnologias

- HTML5
- CSS3
- JavaScript ES6 puro

Não há React, Next.js, Vue, Angular, Bootstrap, jQuery, backend, banco de dados ou checkout real nesta versão.

## Estrutura

- `index.html`: entrada simples que redireciona para a home real.
- `pages/home/index.html`: home completa.
- `pages/catalogo/index.html`: catálogo dinâmico.
- `pages/produto/index.html`: página de produto dinâmica.
- `pages/sobre/index.html`: página sobre.
- `pages/contato/index.html`: página de contato.
- `pages/*.html`: redirecionamentos de compatibilidade para rotas antigas.
- `data/`: dados estáticos preparados para menu, marcas, categorias, sneakers, coleções, acessórios e produtos.
- `css/variables.css`: tokens de cor, fontes, sombras e medidas.
- `css/style.css`: estilos principais.
- `css/responsive.css`: regras responsivas.
- `css/animations.css`: animações e scroll reveal.
- `js/main.js`: inicialização geral.
- `js/menu.js`: header dinâmico e menu mobile.
- `js/slider.js`: carrossel em JavaScript puro.
- `js/animations.js`: scroll reveal e parallax leve.
- `img/`: logo, hero, categorias e ícones.
- `pages/`: páginas organizadas em subpastas semânticas.
- `products/`: espaço reservado para dados futuros do catálogo.

## Como rodar

Sirva a pasta com qualquer servidor estático simples e abra `/`. A raiz redireciona para `pages/home/`.

Para que os arquivos `data/*.json` sejam carregados pelo menu dinâmico e pelo catálogo em todos os navegadores, prefira servir o projeto com um servidor estático local.

## Dados Dinâmicos

O menu principal lê os arquivos:

- `data/brands.json`
- `data/categories.json`
- `data/sneakers.json`
- `data/collections.json`
- `data/accessories.json`

Os produtos têm fonte única em `data/products.json`. O arquivo `js/products-data.js` é apenas um loader: ele busca esse JSON e expõe `window.DripZoneProducts` para catálogo, página de produto e carrinho.

Atualmente o catálogo está vazio e aguarda a futura fonte de produtos reais.

### Marcas no menu público

A taxonomia em `data/brands.json` pode conter marcas planejadas para futuras importações. O menu público, porém, exibe apenas marcas com produtos reais em `data/products.json`.

A disponibilidade é calculada por product.brandId. DripZone é o nome da loja, não uma marca de produto, por isso não deve aparecer como brand, brandId, modelo, coleção ou fallback de identificação. Marcas como Nike ou Adidas aparecem automaticamente quando houver ao menos um produto com o brandId correspondente. Produtos sem marca identificada devem manter brand e brandId como null até revisão.

Se o site for aberto diretamente por `file://`, o menu usa fallback interno para não quebrar. O catálogo de produtos deve ser testado via servidor estático para permitir o carregamento de `data/products.json`.

## Próximos passos

- Trocar imagens conceituais por fotos reais da marca.
- Criar páginas de produto completas.
- Adicionar filtros no catálogo.
- Integrar carrinho e checkout quando a loja real for evoluir.
