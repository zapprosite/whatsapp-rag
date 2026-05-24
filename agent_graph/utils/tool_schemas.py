from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent_graph.utils.llm_output import parse_llm_json


class OrcamentoItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    descricao: str = Field(min_length=1)
    valor: float = Field(ge=0)

    @field_validator("descricao", mode="before")
    @classmethod
    def _descricao_str(cls, value: object) -> str:
        return "" if value is None else str(value).strip()


class EmitirOrcamentoPDFArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cliente_nome: str = Field(default="Cliente Refrimix", min_length=1)
    servico: str = Field(min_length=1)
    itens: list[OrcamentoItem] = Field(min_length=1)
    doc_type: Literal["orcamento_mao_de_obra", "orcamento_material", "proposta", "contrato"]

    @field_validator("cliente_nome", "servico", mode="before")
    @classmethod
    def _required_str(cls, value: object) -> str:
        return "" if value is None else str(value).strip()


def parse_emitir_orcamento_args(raw: str | bytes) -> EmitirOrcamentoPDFArgs:
    return parse_llm_json(raw, EmitirOrcamentoPDFArgs)

