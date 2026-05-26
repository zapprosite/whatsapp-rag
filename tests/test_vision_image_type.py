from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

from agent_graph.services.vision import VisionService, _fallback_structured


def run(coro):
    return asyncio.run(coro)


class TestVisionStructuredFallback:
    def test_fallback_returns_ambiente_generico(self):
        result = _fallback_structured("teste")
        assert result["image_type"] == "ambiente_generico"
        assert result["confidence"] == 0.0
        assert result["hvac_relevant"] is False

    def test_fallback_preserves_observations(self):
        result = _fallback_structured("foto de parede")
        assert result["observations"] == "foto de parede"


class TestAnalyzeImageStructured:
    def test_parses_valid_json_response(self):
        service = VisionService()
        valid_json = json.dumps({
            "image_type": "local_interno_instalacao",
            "confidence": 0.92,
            "observations": "parede com reboco branco, ambiente interno",
            "hvac_relevant": True,
            "installation_context": {
                "has_internal_wall": True,
                "has_external_place": False,
                "has_visible_electrical_point": False,
                "has_visible_drain_option": False,
                "access_difficulty_visible": "simple",
            },
            "equipment_context": {"brand": None, "model": None, "btus": None, "equipment_type": None},
        })

        async def _run():
            with patch.object(service, "_fetch_image_b64", return_value="fakebase64"):
                with patch.object(service, "_analyze_local_qwen", return_value=valid_json):
                    return await service.analyze_image_structured("http://fake.url/img.jpg")

        result = run(_run())
        assert result["image_type"] == "local_interno_instalacao"
        assert result["confidence"] == 0.92
        assert result["hvac_relevant"] is True

    def test_fallback_on_invalid_json(self):
        service = VisionService()

        async def _run():
            with patch.object(service, "_fetch_image_b64", return_value="fakebase64"):
                with patch.object(service, "_analyze_local_qwen", return_value="Não é JSON"):
                    return await service.analyze_image_structured("http://fake.url/img.jpg")

        result = run(_run())
        assert result["image_type"] == "ambiente_generico"
        assert result["confidence"] == 0.0

    def test_fallback_on_fetch_error(self):
        service = VisionService()

        async def _run():
            with patch.object(service, "_fetch_image_b64", side_effect=RuntimeError("sem imagem")):
                return await service.analyze_image_structured("http://fake.url/img.jpg", caption="foto")

        result = run(_run())
        assert result["image_type"] == "ambiente_generico"

    def test_strips_markdown_fences(self):
        service = VisionService()
        wrapped = (
            "```json\n"
            '{"image_type": "etiqueta_tecnica", "confidence": 0.8, "observations": "placa",'
            ' "hvac_relevant": true, "installation_context": {},'
            ' "equipment_context": {"brand": "LG", "btus": 12000, "model": null, "equipment_type": null}}\n'
            "```"
        )

        async def _run():
            with patch.object(service, "_fetch_image_b64", return_value="b64"):
                with patch.object(service, "_analyze_local_qwen", return_value=wrapped):
                    return await service.analyze_image_structured("http://x.com/img.jpg")

        result = run(_run())
        assert result["image_type"] == "etiqueta_tecnica"
        assert result["equipment_context"]["brand"] == "LG"
