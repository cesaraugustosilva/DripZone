from __future__ import annotations

from app.services.product_name_curation import NameCurationInput, VisualEvidence, curate_name


def item(**overrides):
    data = {
        "product_id": 1,
        "current_name": "Adidas Hoodie",
        "brand": "Adidas",
        "category_slug": "moletons",
        "supplier_code": "1",
        "supplier_name": "Adidas Hoodie",
        "visual": VisualEvidence(product_type="hoodie", has_hood=True, predominant_color="Preto"),
    }
    data.update(overrides)
    return NameCurationInput(**data)


def test_generic_name_is_kept_when_already_specific():
    result = curate_name(item(current_name="Air Jordan 4", brand="Jordan", supplier_name="Air Jordan 4", visual=VisualEvidence(product_type="sneaker", predominant_color="Vermelho")))
    assert result.suggested_name == "Air Jordan 4"
    assert result.decision == "keep_current"


def test_visible_color_is_used_only_without_multiple_variants():
    result = curate_name(item())
    assert result.suggested_name == "Moletom Adidas com Capuz Preto"
    assert result.decision == "safe_to_apply"


def test_multiple_colors_blocks_color_specific_name():
    result = curate_name(item(supplier_name="Adidas Hoodie\n24 opções disponíveis"))
    assert result.suggested_name == "Moletom Adidas com Capuz"
    assert "Preto" not in result.suggested_name
    assert "multiple_variants_source" in result.warnings


def test_crossbody_bag_name():
    result = curate_name(item(current_name="Bolsa Adidas", brand="Adidas", category_slug="acessorios", supplier_name="Adidas Bag", visual=VisualEvidence(product_type="bag", bag_type="transversal", predominant_color="Preta")))
    assert result.suggested_name == "Bolsa Adidas com Alça Transversal Preta"


def test_hoodie_with_zipper_name():
    result = curate_name(item(visual=VisualEvidence(product_type="hoodie", has_hood=True, closure="zipper", predominant_color="Preto")))
    assert result.suggested_name == "Moletom Adidas com Capuz e Zíper Preto"


def test_set_name():
    result = curate_name(item(current_name="Conjunto 6PM", brand="6PM", category_slug="conjuntos", supplier_name="6PM Set", visual=VisualEvidence(product_type="set", has_hood=True, closure="zipper", two_piece_set=True)))
    assert result.suggested_name == "Conjunto 6PM com Capuz e Zíper Duas Peças"


def test_jeans_name():
    result = curate_name(item(current_name="Calça Jeans Amiri", brand="Amiri", category_slug="calcas", supplier_name="Amiri Jeans", visual=VisualEvidence(product_type="jeans", print_detail="com Rasgos e Estampa", predominant_color="Preta")))
    assert result.suggested_name == "Calça Jeans Amiri com Rasgos e Estampa Preta"


def test_low_confidence_goes_to_manual_review():
    result = curate_name(item(visual=VisualEvidence(product_type="hoodie", has_hood=True, clarity="low")))
    assert result.decision == "manual_review"
    assert "low_visual_confidence" in result.warnings


def test_does_not_invent_material():
    result = curate_name(item(visual=VisualEvidence(product_type="puffer_jacket", has_hood=True, predominant_color="Cinza")))
    assert "Nylon" not in result.suggested_name
    assert "Couro" not in result.suggested_name


def test_unique_slug_candidate():
    result = curate_name(item(), existing_slugs={"moletom-adidas-com-capuz-preto"})
    assert result.suggested_slug == "moletom-adidas-com-capuz-preto-2"


def test_dry_run_result_has_no_persistence_instruction():
    result = curate_name(item())
    payload = result.as_dict()
    assert payload["decision"] == "safe_to_apply"
    assert "update_sql" not in payload
