(function () {
  const SITE_URL = "https://dripzone.com.br";

  const breadcrumbs = {
    "/pages/catalogo/": "Catalogo",
    "/pages/contato/": "Contato",
    "/pages/sobre/": "Sobre"
  };

  function appendStructuredData(data) {
    const script = document.createElement("script");
    script.type = "application/ld+json";
    script.textContent = JSON.stringify(data);
    document.head.appendChild(script);
  }

  function homeData() {
    return {
      "@context": "https://schema.org",
      "@graph": [
        {
          "@type": "Organization",
          "@id": `${SITE_URL}/#organization`,
          name: "DripZone",
          url: `${SITE_URL}/pages/home/`,
          logo: `${SITE_URL}/assets/images/logo/dripzone-logo.png`,
          sameAs: []
        },
        {
          "@type": "WebSite",
          "@id": `${SITE_URL}/#website`,
          url: `${SITE_URL}/pages/home/`,
          name: "DripZone",
          publisher: { "@id": `${SITE_URL}/#organization` },
          potentialAction: {
            "@type": "SearchAction",
            target: `${SITE_URL}/pages/catalogo/?busca={search_term_string}`,
            "query-input": "required name=search_term_string"
          }
        },
        {
          "@type": "BreadcrumbList",
          itemListElement: [
            {
              "@type": "ListItem",
              position: 1,
              name: "Inicio",
              item: `${SITE_URL}/pages/home/`
            }
          ]
        }
      ]
    };
  }

  function breadcrumbData(name, path) {
    return {
      "@context": "https://schema.org",
      "@type": "BreadcrumbList",
      itemListElement: [
        {
          "@type": "ListItem",
          position: 1,
          name: "Inicio",
          item: `${SITE_URL}/`
        },
        {
          "@type": "ListItem",
          position: 2,
          name,
          item: `${SITE_URL}${path}`
        }
      ]
    };
  }

  const path = window.location.pathname.endsWith("/") ? window.location.pathname : `${window.location.pathname}/`;
  if (path === "/pages/home/" || path === "/") {
    appendStructuredData(homeData());
    return;
  }
  if (breadcrumbs[path]) appendStructuredData(breadcrumbData(breadcrumbs[path], path));
})();
