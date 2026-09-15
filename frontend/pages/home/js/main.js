document.addEventListener("DOMContentLoaded", () => {
  const app = window.DripZone || {};
  const searchForm = document.querySelector("[data-header-search-form]");
  const searchInput = document.querySelector("[data-header-search-input]");
  const searchClose = document.querySelector("[data-header-search-close]");
  const getSearchTriggers = () => document.querySelectorAll("[data-header-search-trigger]");
  let activeSearchTrigger = null;

  const buildCatalogBrandHref = (slug, param = "marca") => {
    const params = new URLSearchParams();
    params.set(param, slug);
    return `../catalogo/?${params.toString()}`;
  };

  const initHeroCarousel = () => {
    const carousel = document.querySelector("[data-hero-carousel]");
    if (!carousel) return;

    const track = carousel.querySelector("[data-hero-carousel-track]");
    const viewport = carousel.querySelector(".hero-carousel__viewport");
    const slides = Array.from(carousel.querySelectorAll("[data-hero-carousel-slide]"));
    const previousButton = carousel.querySelector("[data-hero-carousel-prev]");
    const nextButton = carousel.querySelector("[data-hero-carousel-next]");
    const indicators = carousel.querySelector("[data-hero-carousel-indicators]");
    const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const autoplayDelay = 6000;
    const pauseDelay = 2800;
    const swipeThreshold = 42;
    let currentIndex = 0;
    let autoplayTimer = 0;
    let resumeTimer = 0;
    let touchStartX = 0;
    let touchStartY = 0;
    let isTouching = false;
    let physicalIndex = 1;
    let isAnimating = false;
    let transitionFallback = 0;

    if (!track || slides.length <= 0) return;

    const disableCloneFocus = (slide) => {
      slide.setAttribute("aria-hidden", "true");
      slide.querySelectorAll("a, button, input, select, textarea").forEach((element) => {
        element.tabIndex = -1;
      });
    };

    if (slides.length > 1) {
      const firstClone = slides[0].cloneNode(true);
      const lastClone = slides[slides.length - 1].cloneNode(true);

      firstClone.classList.add("hero-carousel__slide--clone");
      lastClone.classList.add("hero-carousel__slide--clone");
      firstClone.removeAttribute("data-hero-carousel-slide");
      lastClone.removeAttribute("data-hero-carousel-slide");
      disableCloneFocus(firstClone);
      disableCloneFocus(lastClone);

      track.prepend(lastClone);
      track.append(firstClone);
    } else {
      physicalIndex = 0;
    }

    const buttons = slides.map((_, index) => {
      const button = document.createElement("button");
      button.className = "hero-carousel__indicator";
      button.type = "button";
      button.setAttribute("aria-label", `Ir para o slide ${index + 1}`);
      button.addEventListener("click", () => {
        let targetPhysicalIndex = index + (slides.length > 1 ? 1 : 0);
        if (slides.length > 1 && currentIndex === slides.length - 1 && index === 0) {
          targetPhysicalIndex = slides.length + 1;
        }
        if (slides.length > 1 && currentIndex === 0 && index === slides.length - 1) {
          targetPhysicalIndex = 0;
        }
        goToSlide(index, targetPhysicalIndex);
        resetAutoplay();
      });
      indicators?.append(button);
      return button;
    });

    const setSlideAccessibility = () => {
      slides.forEach((slide, index) => {
        const isActive = index === currentIndex;
        slide.setAttribute("aria-hidden", String(!isActive));
        slide.querySelectorAll("a, button").forEach((element) => {
          element.tabIndex = isActive ? 0 : -1;
        });
      });

      buttons.forEach((button, index) => {
        button.setAttribute("aria-current", String(index === currentIndex));
      });
    };

    const getSlideWidth = () => viewport?.clientWidth || carousel.clientWidth || 0;

    const applyTrackTransform = () => {
      track.style.transform = `translate3d(${-physicalIndex * getSlideWidth()}px, 0, 0)`;
    };

    const jumpToPhysicalIndex = (index) => {
      const previousTransition = track.style.transition;
      track.style.transition = "none";
      physicalIndex = index;
      applyTrackTransform();
      void track.offsetWidth;
      track.style.transition = previousTransition;
    };

    const setTrackPosition = (index, animate = true) => {
      if (!animate) {
        jumpToPhysicalIndex(index);
        return;
      }

      physicalIndex = index;
      applyTrackTransform();
    };

    const finishLoopJump = () => {
      window.clearTimeout(transitionFallback);
      transitionFallback = 0;

      if (slides.length < 2) {
        isAnimating = false;
        return;
      }

      if (physicalIndex === 0) {
        currentIndex = slides.length - 1;
        setTrackPosition(slides.length, false);
      }

      if (physicalIndex === slides.length + 1) {
        currentIndex = 0;
        setTrackPosition(1, false);
      }

      setSlideAccessibility();
      isAnimating = false;
    };

    const goToSlide = (index, nextPhysicalIndex = null) => {
      if (isAnimating && !motionQuery.matches) return;
      currentIndex = (index + slides.length) % slides.length;
      const targetPhysicalIndex = nextPhysicalIndex ?? currentIndex + (slides.length > 1 ? 1 : 0);

      if (motionQuery.matches || slides.length < 2) {
        setTrackPosition(currentIndex + (slides.length > 1 ? 1 : 0), false);
        setSlideAccessibility();
        return;
      }

      isAnimating = true;
      setTrackPosition(targetPhysicalIndex, true);
      setSlideAccessibility();
      window.clearTimeout(transitionFallback);
      transitionFallback = window.setTimeout(finishLoopJump, 1100);
    };

    const stopAutoplay = () => {
      window.clearTimeout(autoplayTimer);
      autoplayTimer = 0;
    };

    const startAutoplay = () => {
      stopAutoplay();
      if (motionQuery.matches || slides.length < 2) return;
      autoplayTimer = window.setTimeout(() => {
        nextSlide(false);
        startAutoplay();
      }, autoplayDelay);
    };

    const resetAutoplay = () => {
      stopAutoplay();
      window.clearTimeout(resumeTimer);
      if (motionQuery.matches) return;
      resumeTimer = window.setTimeout(startAutoplay, pauseDelay);
    };

    const nextSlide = (shouldResetAutoplay = true) => {
      goToSlide(currentIndex + 1, physicalIndex + 1);
      if (shouldResetAutoplay) resetAutoplay();
    };

    const previousSlide = (shouldResetAutoplay = true) => {
      goToSlide(currentIndex - 1, physicalIndex - 1);
      if (shouldResetAutoplay) resetAutoplay();
    };

    previousButton?.addEventListener("click", previousSlide);
    nextButton?.addEventListener("click", nextSlide);

    track.addEventListener("transitionend", (event) => {
      if (event.target === track && event.propertyName === "transform") {
        finishLoopJump();
      }
    });

    carousel.addEventListener("mouseenter", stopAutoplay);
    carousel.addEventListener("mouseleave", startAutoplay);
    carousel.addEventListener("focusin", stopAutoplay);
    carousel.addEventListener("focusout", resetAutoplay);
    carousel.addEventListener("pointerdown", resetAutoplay);

    carousel.addEventListener("keydown", (event) => {
      if (event.key === "ArrowRight") {
        event.preventDefault();
        nextSlide();
      }

      if (event.key === "ArrowLeft") {
        event.preventDefault();
        previousSlide();
      }
    });

    carousel.addEventListener("touchstart", (event) => {
      const touch = event.changedTouches[0];
      touchStartX = touch.clientX;
      touchStartY = touch.clientY;
      isTouching = true;
      stopAutoplay();
    }, { passive: true });

    carousel.addEventListener("touchend", (event) => {
      if (!isTouching) return;
      const touch = event.changedTouches[0];
      const deltaX = touch.clientX - touchStartX;
      const deltaY = touch.clientY - touchStartY;
      isTouching = false;

      if (Math.abs(deltaX) > Math.abs(deltaY) && Math.abs(deltaX) > swipeThreshold) {
        if (deltaX < 0) {
          nextSlide();
        } else {
          previousSlide();
        }
        return;
      }

      resetAutoplay();
    }, { passive: true });

    motionQuery.addEventListener?.("change", () => {
      carousel.classList.toggle("is-reduced-motion", motionQuery.matches);
      if (motionQuery.matches) {
        stopAutoplay();
        return;
      }
      startAutoplay();
    });

    window.addEventListener("resize", () => {
      setTrackPosition(physicalIndex, false);
    });

    carousel.classList.toggle("is-reduced-motion", motionQuery.matches);
    setTrackPosition(physicalIndex, false);
    setSlideAccessibility();
    startAutoplay();
  };

  const spotlightBrands = {
    bape: {
      id: "bape",
      name: "BAPE",
      slug: "bape",
      image: "../../assets/editorial/brands/bape/bape-hero.png",
      alt: "Editorial BAPE",
      objectPosition: "50% 50%",
      mobileObjectPosition: "50% 50%"
    },
    synaworld: {
      id: "syna-world",
      name: "SynaWorld",
      slug: "syna-world",
      image: "../../assets/editorial/brands/synaworld/synaworld-hero.webp",
      alt: "Editorial SynaWorld",
      objectPosition: "50% 10%",
      mobileObjectPosition: "50% 5%"
    },
    corteiz: {
      id: "corteiz",
      name: "Corteiz",
      slug: "corteiz",
      image: "../../assets/editorial/brands/corteiz/corteiz-hero.webp",
      alt: "Editorial Corteiz",
      objectPosition: "50% 52%",
      mobileObjectPosition: "50% 52%"
    }
  };

  const sportShoeBrands = {
    "on-running": {
      name: "ON RUNNING",
      image: "../../assets/home/sport-shoes/on-running.jfif",
      alt: "On Running em campanha de corrida",
      objectPosition: "50% 72%",
      mobileObjectPosition: "50% 58%"
    },
    nike: {
      name: "NIKE",
      image: "../../assets/home/sport-shoes/nike.jfif",
      alt: "Nike de corrida em ação",
      objectPosition: "50% 52%",
      mobileObjectPosition: "50% 50%"
    },
    fila: {
      name: "FILA",
      image: "../../assets/home/sport-shoes/fila.jfif",
      alt: "FILA de corrida em ação",
      objectPosition: "50% 70%",
      mobileObjectPosition: "50% 58%"
    },
    hoka: {
      name: "HOKA",
      image: "../../assets/home/sport-shoes/hoka.jfif",
      alt: "HOKA de corrida em trilha",
      objectPosition: "50% 73%",
      mobileObjectPosition: "50% 58%"
    },
    puma: {
      name: "PUMA",
      image: "../../assets/home/sport-shoes/puma.jfif",
      alt: "PUMA de corrida em pista",
      objectPosition: "50% 88%",
      mobileObjectPosition: "50% 58%"
    },
    adidas: {
      name: "ADIDAS",
      image: "../../assets/home/sport-shoes/adidas.jfif",
      alt: "Adidas de corrida em ação",
      objectPosition: "50% 60%",
      mobileObjectPosition: "50% 54%"
    }
  };

  const safeText = (value, fallback = "") => window.DripZoneSecurity?.text(value, fallback) ?? String(value ?? fallback);
  const productHref = (product) => window.DripZoneSecurity?.productHref(product.id, "../produto/") || "../produto/";
  const isPurchasable = (product) => window.DripZoneSecurity?.isPurchasable(product) || false;
  const displayProductPrice = (product) => isPurchasable(product)
    ? (window.DripZoneUtils?.formatPrice?.(product.price) || String(product.price))
    : "Preço sob consulta";

  const createSpotlightProductCard = (product) => {
    const card = document.createElement("a");
    const productName = safeText(product.name, "Produto");
    card.className = "product-card catalog-product streetwear-spotlight__product";
    card.href = productHref(product);
    card.setAttribute("aria-label", `Ver produto ${productName}`);

    const media = document.createElement("div");
    media.className = "product-card__media";
    const image = document.createElement("img");
    image.loading = "lazy";
    window.DripZoneSecurity?.setSafeImage(image, product.image, productName);
    if (!image.src) {
      image.src = "../../assets/images/logo/dripzone-logo.png";
      image.alt = productName;
    }

    const badges = document.createElement("span");
    badges.className = "badge-stack";
    (Array.isArray(product.badges) ? product.badges : []).filter(Boolean).slice(0, 2).forEach((badge) => {
      const badgeElement = document.createElement("span");
      badgeElement.className = "product-badge";
      badgeElement.textContent = safeText(badge);
      badges.append(badgeElement);
    });
    media.append(image, badges);

    const body = document.createElement("div");
    body.className = "product-card__body";
    const category = document.createElement("p");
    category.className = "product-card__category";
    category.textContent = safeText(product.category, product.brand || "");
    const title = document.createElement("h3");
    title.textContent = productName;
    const footer = document.createElement("div");
    footer.className = "product-card__footer";
    const price = document.createElement("span");
    price.className = "price";
    price.textContent = displayProductPrice(product);
    const cta = document.createElement("span");
    cta.className = "product-card__cta";
    cta.textContent = "Ver peça";
    footer.append(price, cta);
    body.append(category, title, footer);
    card.append(media, body);
    return card;
  };

  const initStreetwearSpotlight = async () => {
    const section = document.querySelector("[data-streetwear-spotlight]");
    if (!section) return;

    const tabs = Array.from(section.querySelectorAll("[data-spotlight-tab]"));
    const panel = section.querySelector("[data-spotlight-panel]");
    const banner = section.querySelector("[data-spotlight-banner]");
    const image = section.querySelector("[data-spotlight-image]");
    const count = section.querySelector("[data-spotlight-count]");
    const productsGrid = section.querySelector("[data-spotlight-products]");
    const empty = section.querySelector("[data-spotlight-empty]");
    const emptyDetail = section.querySelector("[data-spotlight-empty-detail]");
    const allLink = section.querySelector("[data-spotlight-all]");
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    Object.values(spotlightBrands).forEach((brand) => {
      const preload = new Image();
      preload.src = brand.image;
    });

    await (window.DripZoneProductsReady || Promise.resolve());
    const products = Array.isArray(window.DripZoneProducts) ? window.DripZoneProducts : [];

    const productsByBrand = Object.fromEntries(
      Object.entries(spotlightBrands).map(([key, brand]) => [
        key,
        products
          .filter((product) => product.brandId === brand.id)
          .filter((product) => product.image)
          .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime())
          .slice(0, 6)
      ])
    );

    const setActiveBrand = (key, focusTab = false) => {
      const brand = spotlightBrands[key] || spotlightBrands.corteiz;
      const brandProducts = productsByBrand[key] || [];

      tabs.forEach((tab) => {
        const isActive = tab.dataset.spotlightTab === key;
        tab.classList.toggle("is-active", isActive);
        tab.setAttribute("aria-selected", String(isActive));
        tab.tabIndex = isActive ? 0 : -1;
        if (isActive && focusTab) tab.focus();
      });

      panel?.setAttribute("aria-labelledby", `spotlight-tab-${key}`);
      if (banner && !prefersReducedMotion) banner.classList.add("is-switching");

      window.setTimeout(() => {
        if (image) {
          image.src = brand.image;
          image.alt = brand.alt;
          image.dataset.spotlightBrand = key;
          image.style.setProperty("--spotlight-object-position", brand.objectPosition);
          image.style.setProperty("--spotlight-object-position-mobile", brand.mobileObjectPosition || brand.objectPosition);
        }
        if (count) {
          count.textContent = brandProducts.length
            ? `${brandProducts.length} ${brandProducts.length === 1 ? "produto publicado" : "produtos publicados"}`
            : "Seleção em atualização.";
        }
        productsGrid?.replaceChildren(...brandProducts.map(createSpotlightProductCard));

        const hasProducts = brandProducts.length > 0;
        if (empty) empty.hidden = hasProducts;
        if (emptyDetail) emptyDetail.textContent = `${brand.name} ainda não possui produtos publicados na vitrine.`;
        if (allLink) {
          allLink.href = buildCatalogBrandHref(brand.slug);
          allLink.hidden = !hasProducts;
          allLink.setAttribute("aria-label", `Ver todos os produtos ${brand.name}`);
        }
        window.setTimeout(() => banner?.classList.remove("is-switching"), prefersReducedMotion ? 0 : 80);
      }, prefersReducedMotion ? 0 : 160);
    };

    tabs.forEach((tab, index) => {
      tab.addEventListener("click", () => setActiveBrand(tab.dataset.spotlightTab || "corteiz"));
      tab.addEventListener("keydown", (event) => {
        const direction = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
        if (!direction) return;
        event.preventDefault();
        const nextIndex = (index + direction + tabs.length) % tabs.length;
        setActiveBrand(tabs[nextIndex].dataset.spotlightTab || "corteiz", true);
      });
    });

    setActiveBrand("corteiz");
  };

  const initSportShoesSpotlight = () => {
    const section = document.querySelector("[data-sport-shoes-spotlight]");
    if (!section) return;

    const tabs = Array.from(section.querySelectorAll("[data-sport-shoes-tab]"));
    const panel = section.querySelector("[data-sport-shoes-panel]");
    const banner = section.querySelector("[data-sport-shoes-banner]");
    const image = section.querySelector("[data-sport-shoes-image]");
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    Object.values(sportShoeBrands).forEach((brand) => {
      const preload = new Image();
      preload.src = brand.image;
    });

    const setActiveSportShoeBrand = (key, focusTab = false, revealTab = false) => {
      const brand = sportShoeBrands[key] || sportShoeBrands["on-running"];

      tabs.forEach((tab) => {
        const isActive = tab.dataset.sportShoesTab === key;
        tab.classList.toggle("is-active", isActive);
        tab.setAttribute("aria-selected", String(isActive));
        tab.tabIndex = isActive ? 0 : -1;
        if (!isActive) return;
        if (focusTab) tab.focus();
        if (revealTab && typeof tab.scrollIntoView === "function") {
          tab.scrollIntoView({
            behavior: prefersReducedMotion ? "auto" : "smooth",
            block: "nearest",
            inline: "center"
          });
        }
      });

      panel?.setAttribute("aria-labelledby", `sport-shoes-tab-${key}`);
      if (banner && !prefersReducedMotion) banner.classList.add("is-switching");

      window.setTimeout(() => {
        if (image) {
          image.src = brand.image;
          image.alt = brand.alt;
          image.dataset.sportShoesBrand = key;
          image.style.setProperty("--spotlight-object-position", brand.objectPosition);
          image.style.setProperty("--spotlight-object-position-mobile", brand.mobileObjectPosition || brand.objectPosition);
        }
        window.setTimeout(() => banner?.classList.remove("is-switching"), prefersReducedMotion ? 0 : 80);
      }, prefersReducedMotion ? 0 : 160);
    };

    tabs.forEach((tab, index) => {
      tab.addEventListener("click", () => setActiveSportShoeBrand(tab.dataset.sportShoesTab || "on-running", false, true));
      tab.addEventListener("keydown", (event) => {
        const direction = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
        if (!direction) return;
        event.preventDefault();
        const nextIndex = (index + direction + tabs.length) % tabs.length;
        setActiveSportShoeBrand(tabs[nextIndex].dataset.sportShoesTab || "on-running", true, true);
      });
    });

    setActiveSportShoeBrand("on-running");
  };

  const createFeaturedBrand = (brand) => {
    const name = String(brand.name || "").trim();
    const slug = String(brand.slug || "").trim();
    const logo = String(brand.logo || "").trim();
    const isEnabled = brand.enabled !== false;
    const item = document.createElement(isEnabled ? "a" : "span");

    item.className = "featured-brand";
    item.dataset.brand = slug;
    if (isEnabled) {
      item.href = buildCatalogBrandHref(slug, brand.catalogParam || "marca");
      item.setAttribute("aria-label", `Ver produtos ${name}`);
    } else {
      item.classList.add("featured-brand--disabled");
      item.setAttribute("role", "img");
      item.setAttribute("aria-label", name);
    }

    const fallback = document.createElement("span");
    fallback.className = "featured-brand__fallback";
    fallback.textContent = name;

    if (logo) {
      const image = document.createElement("img");
      image.className = "featured-brand__logo";
      image.loading = "lazy";
      image.alt = name;
      image.dataset.featuredBrandLogo = slug;
      image.addEventListener("error", () => {
        image.remove();
        item.append(fallback);
      }, { once: true });
      image.src = `../../${logo.replace(/^\/+/, "")}`;
      item.append(image);
      return item;
    }

    item.append(fallback);
    return item;
  };

  const initFeaturedBrands = async () => {
    const section = document.querySelector("[data-featured-brands]");
    const track = document.querySelector("[data-featured-brands-track]");
    const status = document.querySelector("[data-featured-brands-status]");
    if (!section || !track) return;

    const dataPath = "../../data/featured-brands.json";

    try {
      const response = await fetch(dataPath, { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      const catalogParam = data.catalogParam || "marca";
      const brands = (Array.isArray(data.brands) ? data.brands : [])
        .filter((brand) => brand?.featured !== false && brand?.name && /^[a-z0-9-]+$/.test(String(brand.slug || "")))
        .map((brand) => ({ ...brand, catalogParam }));

      if (!brands.length) throw new Error("empty_featured_brands");

      const primaryGroup = document.createElement("div");
      primaryGroup.className = "featured-brands__group";
      brands.forEach((brand) => primaryGroup.append(createFeaturedBrand(brand)));

      const duplicateGroup = primaryGroup.cloneNode(true);
      duplicateGroup.setAttribute("aria-hidden", "true");
      duplicateGroup.querySelectorAll("a").forEach((link) => link.tabIndex = -1);

      track.replaceChildren(primaryGroup, duplicateGroup);
    } catch {
      if (status) {
        status.textContent = "Logos indisponíveis no momento.";
        status.hidden = false;
      }
    }

    ["pointerdown", "touchstart", "wheel"].forEach((eventName) => {
      section.addEventListener(eventName, () => {
        section.classList.add("is-user-paused");
        window.clearTimeout(section.featuredBrandsPauseTimer);
        section.featuredBrandsPauseTimer = window.setTimeout(() => {
          section.classList.remove("is-user-paused");
        }, 1800);
      }, { passive: true });
    });
  };

  const initCategoryCarousel = () => {
    const carousel = document.querySelector("[data-category-carousel]");
    if (!carousel) return;

    const viewport = carousel.querySelector("[data-category-carousel-viewport]");
    const track = carousel.querySelector(".home-categories__track");
    const previousButton = carousel.querySelector("[data-category-carousel-prev]");
    const nextButton = carousel.querySelector("[data-category-carousel-next]");
    if (!viewport || !track) return;

    const cards = Array.from(track.querySelectorAll(".home-category-card"));
    if (!cards.length) return;

    let activeIndex = 0;
    let touchStartX = 0;
    let touchStartY = 0;
    let isTouching = false;
    const swipeThreshold = 48;
    const positionClasses = ["is-active", "is-prev", "is-next", "is-prev-2", "is-next-2", "is-prev-3", "is-next-3", "is-distant"];

    const wrapIndex = (index) => (index + cards.length) % cards.length;

    const getCircularOffset = (index) => {
      const forward = (index - activeIndex + cards.length) % cards.length;
      return forward > cards.length / 2 ? forward - cards.length : forward;
    };

    const getPosition = (offset) => {
      const distance = Math.abs(offset);
      const direction = Math.sign(offset);
      const galleryWidth = viewport.getBoundingClientRect().width || viewport.clientWidth || window.innerWidth;
      const viewportWidth = galleryWidth;
      const isMobile = viewportWidth <= 768;
      const isTablet = viewportWidth > 768 && viewportWidth < 1024;
      const mobileSizingWidth = Math.max(0, galleryWidth - (window.innerWidth <= 640 ? 28 : 40));
      const mobileCardWidth = Math.min(205, Math.max(165, mobileSizingWidth * 0.5));
      const offsets = isMobile
        ? [0, mobileCardWidth * 0.74, mobileCardWidth * 1.28, mobileCardWidth * 1.76]
        : isTablet
          ? [0, Math.min(320, Math.max(240, viewportWidth * 0.31)), Math.min(560, Math.max(430, viewportWidth * 0.55)), Math.min(760, Math.max(590, viewportWidth * 0.76))]
          : [0, 300, 540, 740];
      const styles = isMobile
        ? [
          { scale: 1, y: 0, opacity: 1, z: 5 },
          { scale: 0.82, y: 12, opacity: 0.94, z: 4 },
          { scale: 0.7, y: 22, opacity: 0.76, z: 3 },
          { scale: 0.64, y: 28, opacity: 0.48, z: 2 }
        ]
        : [
          { scale: 1, y: 0, opacity: 1, z: 5 },
          { scale: 0.9, y: 18, opacity: 0.95, z: 4 },
          { scale: 0.84, y: 28, opacity: 0.88, z: 3 },
          { scale: 0.78, y: 34, opacity: 0.78, z: 2 }
        ];
      const style = styles[Math.min(distance, 3)] || { scale: 0.72, y: 38, opacity: 0, z: 1 };

      return {
        width: isMobile ? `${mobileCardWidth}px` : "",
        x: `${direction * (offsets[distance] || 0)}px`,
        y: `${style.y}px`,
        scale: String(style.scale),
        opacity: String(distance > 3 ? 0 : style.opacity),
        z: String(distance > 3 ? 1 : style.z)
      };
    };

    const setActive = (index) => {
      activeIndex = wrapIndex(index);
      carousel.dataset.activeIndex = String(activeIndex);

      cards.forEach((card, index) => {
        const offset = getCircularOffset(index);
        const isActive = offset === 0;
        const position = getPosition(offset);
        card.classList.remove(...positionClasses);
        card.classList.add(
          offset === 0 ? "is-active"
            : offset === -1 ? "is-prev"
              : offset === 1 ? "is-next"
                : offset === -2 ? "is-prev-2"
                  : offset === 2 ? "is-next-2"
                    : offset === -3 ? "is-prev-3"
                      : offset === 3 ? "is-next-3"
                        : "is-distant"
        );
        card.style.setProperty("--category-x", position.x);
        card.style.setProperty("--category-y", position.y);
        card.style.setProperty("--category-scale", position.scale);
        card.style.setProperty("--category-opacity", position.opacity);
        card.style.setProperty("--category-z", position.z);
        if (position.width) {
          card.style.setProperty("--category-card-width", position.width);
        } else {
          card.style.removeProperty("--category-card-width");
        }
        card.setAttribute("aria-current", String(isActive));
        card.setAttribute("aria-selected", String(isActive));
      });
    };

    const moveBy = (direction) => {
      setActive(activeIndex + direction);
      cards[activeIndex]?.focus({ preventScroll: true });
    };

    previousButton?.addEventListener("click", () => moveBy(-1));
    nextButton?.addEventListener("click", () => moveBy(1));

    viewport.addEventListener("keydown", (event) => {
      const keyDirections = {
        ArrowLeft: -1,
        ArrowRight: 1
      };
      const direction = keyDirections[event.key];
      if (!direction) return;

      event.preventDefault();
      moveBy(direction);
    });

    cards.forEach((card, index) => {
      const label = card.querySelector("img")?.alt || card.getAttribute("aria-label")?.replace(/^Ver\s+/i, "") || `Categoria ${index + 1}`;
      card.dataset.categoryLabel = label;
      card.dataset.categoryIndex = String(index);
      card.setAttribute("role", "option");
      card.addEventListener("focus", () => setActive(index));
      card.addEventListener("click", (event) => {
        if (index !== activeIndex) {
          event.preventDefault();
          setActive(index);
        }
      });
    });

    viewport.addEventListener("touchstart", (event) => {
      const touch = event.changedTouches[0];
      touchStartX = touch.clientX;
      touchStartY = touch.clientY;
      isTouching = true;
    }, { passive: true });

    viewport.addEventListener("touchend", (event) => {
      if (!isTouching) return;
      const touch = event.changedTouches[0];
      const deltaX = touch.clientX - touchStartX;
      const deltaY = touch.clientY - touchStartY;
      isTouching = false;

      if (Math.abs(deltaX) <= Math.abs(deltaY) || Math.abs(deltaX) < swipeThreshold) return;
      moveBy(deltaX < 0 ? 1 : -1);
    }, { passive: true });

    viewport.setAttribute("role", "listbox");
    setActive(0);
    window.addEventListener("resize", () => setActive(activeIndex));
  };

  const setSearchExpanded = (isExpanded) => {
    getSearchTriggers().forEach((trigger) => {
      trigger.setAttribute("aria-expanded", String(isExpanded));
    });
  };

  const openHeaderSearch = (trigger) => {
    if (!searchForm || !searchInput) return;
    activeSearchTrigger = trigger || activeSearchTrigger;
    searchForm.hidden = false;
    searchForm.classList.add("is-open");
    setSearchExpanded(true);
    searchInput.focus({ preventScroll: true });
    window.requestAnimationFrame(() => searchInput.focus());
  };

  const closeHeaderSearch = () => {
    if (!searchForm) return;
    searchForm.classList.remove("is-open");
    if (!searchForm.classList.contains("nav-search")) {
      searchForm.hidden = true;
    }
    setSearchExpanded(false);
    activeSearchTrigger?.focus();
  };

  document.addEventListener("click", (event) => {
    const trigger = event.target.closest?.("[data-header-search-trigger]");
    if (!trigger) return;

    const isOpen = searchForm?.classList.contains("is-open");
    if (isOpen) {
      closeHeaderSearch();
      return;
    }

    openHeaderSearch(trigger);
  });

  searchClose?.addEventListener("click", closeHeaderSearch);

  searchForm?.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      closeHeaderSearch();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && searchForm?.classList.contains("is-open")) {
      event.preventDefault();
      closeHeaderSearch();
    }
  });

  searchForm?.addEventListener("submit", (event) => {
    event.preventDefault();
    const term = searchInput?.value.trim() || "";
    if (!term) {
      searchInput?.focus();
      return;
    }

    const params = new URLSearchParams();
    params.set("q", term);
    const catalogUrl = window.DripZoneUtils?.route ? window.DripZoneUtils.route("pages/catalogo/") : "pages/catalogo/";
    window.location.href = `${catalogUrl}?${params.toString()}`;
  });

  app.initMenu?.();
  initHeroCarousel();
  initFeaturedBrands();
  initCategoryCarousel();
  initSportShoesSpotlight();
  initStreetwearSpotlight();
  app.initScrollReveal?.();
  app.initParallax?.();
  app.initImageLoading?.();
  app.initRippleButtons?.();
});
