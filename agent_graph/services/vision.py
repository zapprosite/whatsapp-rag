from __future__ import annotations

import json
import os
import base64
import logging
import httpx
from typing import Any

logger = logging.getLogger(__name__)

_TIMEOUT_FETCH = 8.0
_TIMEOUT_INFER = 45.0

_HVAC_VISION_PROMPT = (
    "Você é um técnico de refrigeração e climatização HVAC da Refrimix Tecnologia.\n"
    "Analise a imagem fornecida com atenção técnica absoluta. Identifique com precisão:\n"
    "1. Se for uma etiqueta/placa de identificação técnica do fabricante (etiqueta de ar condicionado, evaporadora, condensadora, compressor, etc.):\n"
    "   - Extraia a MARCA/FABRICANTE exata (ex: Midea, LG, Springer Carrier, Daikin, Elgin, Samsung, Gree, Fujitsu, Consul, Electrolux).\n"
    "   - Extraia o MODELO exato.\n"
    "   - Extraia a CAPACIDADE (BTUs ou kW).\n"
    "   - Extraia o NÚMERO DE SÉRIE se estiver visível.\n"
    "   - Extraia o gás refrigerante e tensão/voltagem.\n"
    "2. Se for um equipamento instalado ou com problema:\n"
    "   - Descreva o equipamento mostrado, marca e tipo (Split, Janela, Cassete, Piso-Teto).\n"
    "   - Descreva o problema, dano ou anomalia visível.\n"
    "   - Apresente possíveis causas técnicas.\n"
    "Seja extremamente preciso, direto e profissional. Responda em português brasileiro."
)

_HVAC_VISION_STRUCTURED_PROMPT = """\
Você é um técnico de refrigeração e climatização HVAC da Refrimix Tecnologia.

Classifique a imagem pelo TIPO DE FOTO:

1. local_interno_instalacao — parede, quarto, sala, escritório ou ambiente interno onde vai ficar a evaporadora/unidade interna.
2. local_externo_instalacao — área externa, varanda, fachada, quintal, sacada, laje, telhado ou local da condensadora/unidade externa.
3. equipamento_ar_condicionado — aparelho split, janela, cassete, piso-teto, condensadora ou evaporadora já instalada.
4. etiqueta_tecnica — etiqueta/placa com marca, modelo, BTUs, tensão ou gás.
5. quadro_eletrico_disjuntor — quadro de luz, disjuntor, tomada, fiação ou ponto elétrico.
6. ambiente_generico — ambiente sem informação suficiente.

Retorne JSON válido sem markdown:

{
  "image_type": "local_interno_instalacao",
  "confidence": 0.9,
  "observations": "parede com reboco, ambiente interno sem aparelho visível",
  "hvac_relevant": true,
  "installation_context": {
    "has_internal_wall": true,
    "has_external_place": false,
    "has_visible_electrical_point": false,
    "has_visible_drain_option": false,
    "access_difficulty_visible": "unknown"
  },
  "equipment_context": {
    "brand": null,
    "model": null,
    "btus": null,
    "equipment_type": null
  }
}

Se for parede/ambiente interno sem aparelho, classifique como local_interno_instalacao.
Foto de área externa sem aparelho é local_externo_instalacao.
Não diga que não há etiqueta; classifique pelo tipo real da imagem.\
"""


class VisionService:
    """Análise de imagens HVAC via Qwen 2.5 VL local (PC2, porta 8010)."""

    def __init__(self) -> None:
        self._evo_url = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
        self._evo_key = os.getenv("EVOLUTION_API_KEY", os.getenv("AUTHENTICATION_API_KEY", ""))
        self._evo_instance = os.getenv("EVOLUTION_INSTANCE", "RefrimixLead")
        self._local_qwen_url = os.getenv("LOCAL_QWEN_BASE_URL", "http://127.0.0.1:8010/v1").rstrip("/")
        self._local_qwen_model = os.getenv("LOCAL_QWEN_MODEL", "qwen2.5-vl-7b-instruct")

    async def _fetch_image_b64(
        self,
        image_url: str,
        instance: str | None,
        msg_id: str | None = None,
        media_base64: str | None = None,
    ) -> str:
        """Retorna imagem como base64. Tenta URL pública, depois Evolution API via msg_id."""
        if media_base64:
            return media_base64

        if image_url:
            try:
                async with httpx.AsyncClient(timeout=_TIMEOUT_FETCH) as client:
                    resp = await client.get(image_url)
                    if resp.status_code == 200 and len(resp.content) > 512:
                        return base64.b64encode(resp.content).decode()
            except Exception:
                pass

        if not msg_id:
            raise RuntimeError("Sem media_base64, URL acessível ou msg_id para baixar a imagem")

        inst = instance or self._evo_instance
        async with httpx.AsyncClient(timeout=_TIMEOUT_FETCH) as client:
            resp = await client.post(
                f"{self._evo_url}/chat/getBase64FromMediaMessage/{inst}",
                headers={"apikey": self._evo_key, "Content-Type": "application/json"},
                json={"message": {"key": {"id": msg_id}}, "convertToMp4": False},
            )
            resp.raise_for_status()
            data = resp.json()
            b64 = data.get("base64") or data.get("data", {}).get("base64", "")
            if not b64:
                raise RuntimeError(f"Evolution API não retornou base64 de imagem: {data}")
            return b64

    async def _analyze_local_qwen(self, image_b64: str, caption: str, prompt: str | None = None) -> str:
        user_text = prompt or _HVAC_VISION_PROMPT
        if caption:
            user_text += f"\nLegenda do usuário: {caption}"

        async with httpx.AsyncClient(timeout=_TIMEOUT_INFER) as client:
            resp = await client.post(
                f"{self._local_qwen_url}/chat/completions",
                headers={"Content-Type": "application/json"},
                json={
                    "model": self._local_qwen_model,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": user_text},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                            ],
                        }
                    ],
                    "max_tokens": 512,
                    "temperature": 0.2,
                    "frequency_penalty": 0.5,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("choices"):
                raise RuntimeError(f"Vision local sem choices: {data}")
            return data["choices"][0]["message"]["content"].strip()

    async def analyze_image(
        self,
        image_url: str,
        caption: str = "",
        instance: str | None = None,
        msg_id: str | None = None,
        media_base64: str | None = None,
    ) -> str:
        """Analisa imagem HVAC via Qwen 2.5 VL local e retorna descrição técnica em pt-BR."""
        try:
            image_b64 = await self._fetch_image_b64(image_url, instance, msg_id, media_base64)
        except Exception as e:
            logger.warning(f"Vision: falhou ao buscar imagem {image_url!r}: {e}")
            return caption or "Imagem não processada."

        try:
            result = await self._analyze_local_qwen(image_b64, caption)
            logger.info(f"Vision (Qwen local): {result[:80]!r}")
            return result
        except Exception as e:
            logger.error(f"Vision Qwen local falhou: {e}")
            return caption or "Não foi possível analisar a imagem."

    async def analyze_image_structured(
        self,
        image_url: str,
        caption: str = "",
        instance: str | None = None,
        msg_id: str | None = None,
        media_base64: str | None = None,
    ) -> dict[str, Any]:
        """Analisa imagem e retorna dict estruturado com image_type e contexto HVAC."""
        try:
            image_b64 = await self._fetch_image_b64(image_url, instance, msg_id, media_base64)
        except Exception as e:
            logger.warning(f"Vision structured: falhou ao buscar imagem {image_url!r}: {e}")
            return _fallback_structured(caption or "Imagem não processada.")

        try:
            raw = await self._analyze_local_qwen(image_b64, caption, prompt=_HVAC_VISION_STRUCTURED_PROMPT)
            logger.info(f"Vision structured (Qwen local): {raw[:120]!r}")
            # Limpa possível markdown antes do JSON
            clean = raw.strip()
            if clean.startswith("```"):
                clean = clean.split("```")[1]
                if clean.startswith("json"):
                    clean = clean[4:]
                clean = clean.strip()
            data = json.loads(clean)
            if not isinstance(data, dict) or "image_type" not in data:
                raise ValueError("JSON sem image_type")
            return data
        except Exception as e:
            logger.warning(f"Vision structured parse falhou: {e}; raw={raw[:80] if 'raw' in dir() else '?'!r}")
            return _fallback_structured(caption or "Imagem recebida.")


def _fallback_structured(observations: str) -> dict[str, Any]:
    return {
        "image_type": "ambiente_generico",
        "confidence": 0.0,
        "observations": observations,
        "hvac_relevant": False,
        "installation_context": {
            "has_internal_wall": False,
            "has_external_place": False,
            "has_visible_electrical_point": False,
            "has_visible_drain_option": False,
            "access_difficulty_visible": "unknown",
        },
        "equipment_context": {"brand": None, "model": None, "btus": None, "equipment_type": None},
    }


_vision = VisionService()


async def analyze_image(
    image_url: str,
    caption: str = "",
    instance: str | None = None,
    msg_id: str | None = None,
    media_base64: str | None = None,
) -> str:
    return await _vision.analyze_image(image_url, caption, instance, msg_id, media_base64)


async def analyze_image_structured(
    image_url: str,
    caption: str = "",
    instance: str | None = None,
    msg_id: str | None = None,
    media_base64: str | None = None,
) -> dict[str, Any]:
    return await _vision.analyze_image_structured(image_url, caption, instance, msg_id, media_base64)
