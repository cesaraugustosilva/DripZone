from __future__ import annotations

from dataclasses import dataclass, field
from unicodedata import normalize

from app.utils.slug import make_slug


SAFE_THRESHOLD = 0.85


@dataclass(frozen=True)
class VisualEvidence:
    product_type: str
    predominant_color: str | None = None
    format: str | None = None
    print_detail: str | None = None
    logo: str | None = None
    closure: str | None = None
    length: str | None = None
    bag_type: str | None = None
    has_hood: bool | None = None
    two_piece_set: bool | None = None
    jeans_wash: str | None = None
    contrast_details: str | None = None
    clarity: str = "high"
    text_conflict: str | None = None

    def as_dict(self) -> dict:
        return {key: value for key, value in self.__dict__.items() if value not in {None, ""}}


@dataclass
class NameCurationInput:
    product_id: int
    current_name: str
    brand: str
    category_slug: str
    supplier_code: str
    supplier_name: str
    visual: VisualEvidence


@dataclass
class NameCurationDecision:
    product_id: int
    supplier_code: str
    current_name: str
    suggested_name: str
    confidence: float
    decision: str
    evidence: dict
    warnings: list[str] = field(default_factory=list)
    suggested_slug: str | None = None

    def as_dict(self) -> dict:
        return {
            "product_id": self.product_id,
            "supplier_code": self.supplier_code,
            "current_name": self.current_name,
            "suggested_name": self.suggested_name,
            "confidence": self.confidence,
            "decision": self.decision,
            "evidence": self.evidence,
            "warnings": self.warnings,
            "suggested_slug": self.suggested_slug,
        }


def source_has_multiple_variants(supplier_name: str) -> bool:
    folded = supplier_name.casefold()
    ascii_folded = normalize("NFKD", folded).encode("ascii", "ignore").decode("ascii")
    return (
        "várias cores" in folded
        or "varias cores" in ascii_folded
        or "opções disponíveis" in folded
        or "opcoes disponiveis" in ascii_folded
        or ("op" in ascii_folded and "dispon" in ascii_folded)
        or ("op" in folded and "dispon" in folded)
    )


def visible_descriptors(visual: VisualEvidence, *, allow_color: bool) -> list[str]:
    descriptors: list[str] = []
    features: list[str] = []
    if visual.has_hood:
        features.append("Capuz")
    if visual.closure == "zipper":
        features.append("Zíper")
    if visual.bag_type == "transversal":
        features.append("Alça Transversal")
    if visual.print_detail:
        features.append(visual.print_detail.removeprefix("com ").strip())
    if visual.contrast_details:
        features.append(visual.contrast_details.removeprefix("com ").strip())
    if features:
        descriptors.append("com " + join_pt(features))
    if visual.two_piece_set:
        descriptors.append("Duas Peças")
    if allow_color and visual.predominant_color:
        descriptors.append(visual.predominant_color)
    return descriptors


def join_pt(values: list[str]) -> str:
    if len(values) <= 1:
        return "".join(values)
    if len(values) == 2:
        return " e ".join(values)
    return ", ".join(values[:-1]) + " e " + values[-1]


def build_name(item: NameCurationInput, *, allow_color: bool) -> str:
    visual = item.visual
    brand = item.brand
    if visual.product_type == "sneaker":
        return item.current_name
    if visual.product_type == "long_sleeve_shirt":
        return f"Camiseta Manga Longa {brand}".strip()
    if visual.product_type == "hoodie":
        base = f"Moletom {brand}"
    elif visual.product_type == "jeans":
        base = f"Calça Jeans {brand}"
    elif visual.product_type == "set":
        base = f"Conjunto {brand}"
    elif visual.product_type == "puffer_jacket":
        base = f"Jaqueta {brand} Couyere" if "couyere" in item.current_name.casefold() else f"Jaqueta {brand}"
    elif visual.product_type == "backpack":
        base = f"Mochila {brand}"
    elif visual.product_type == "bag":
        base = f"Bolsa {brand}"
    else:
        return item.current_name
    descriptors = visible_descriptors(visual, allow_color=allow_color)
    if descriptors:
        return f"{base} {' '.join(descriptors)}"
    return base


def unique_slug_candidate(name: str, existing_slugs: set[str]) -> str:
    base = make_slug(name)
    candidate = base
    suffix = 2
    while candidate in existing_slugs:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def curate_name(item: NameCurationInput, *, existing_slugs: set[str] | None = None) -> NameCurationDecision:
    warnings: list[str] = []
    multiple_variants = source_has_multiple_variants(item.supplier_name)
    if multiple_variants:
        warnings.append("multiple_variants_source")
    if item.visual.text_conflict:
        warnings.append("visual_text_conflict")
    low_clarity = item.visual.clarity != "high"
    if low_clarity:
        warnings.append("low_visual_confidence")
    suggested = build_name(item, allow_color=not multiple_variants)
    confidence = 0.9
    if suggested == item.current_name:
        confidence = 0.92 if not item.visual.text_conflict else 0.55
    if multiple_variants and item.visual.predominant_color and item.visual.predominant_color in suggested:
        confidence = min(confidence, 0.75)
    if item.visual.text_conflict:
        confidence = min(confidence, 0.55)
    if low_clarity:
        confidence = min(confidence, 0.6)
    if suggested == item.current_name:
        decision = "keep_current" if confidence >= SAFE_THRESHOLD else "manual_review"
    elif confidence >= SAFE_THRESHOLD and not item.visual.text_conflict and not low_clarity:
        decision = "safe_to_apply"
    else:
        decision = "manual_review"
    return NameCurationDecision(
        product_id=item.product_id,
        supplier_code=item.supplier_code,
        current_name=item.current_name,
        suggested_name=suggested,
        confidence=confidence,
        decision=decision,
        evidence=item.visual.as_dict(),
        warnings=warnings,
        suggested_slug=unique_slug_candidate(suggested, existing_slugs or set()) if decision == "safe_to_apply" else None,
    )
