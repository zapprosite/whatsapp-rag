from refinar_llm import _coerce_lista_cenarios, _coerce_score_avaliacao


def test_refinar_llm_accepts_list_scenarios_from_judge():
    parsed = _coerce_lista_cenarios('[{"lead": "Meu ar não gela", "service": "manutencao"}]')

    assert parsed.cenarios[0].msg == "Meu ar não gela"
    assert parsed.cenarios[0].servico == "manutencao"


def test_refinar_llm_accepts_rubric_score_from_judge():
    parsed = _coerce_score_avaliacao(
        '{"conversao": 8, "tom": 9, "qualificacao": 7, "falhas": ["faltou foto"], "resposta_ideal": "Me manda uma foto?", "resposta_natural_ptbr": 9}'
    )

    assert 7.0 <= parsed.score <= 9.0
    assert parsed.falhas == ["faltou foto"]
    assert parsed.ideal == "Me manda uma foto?"
