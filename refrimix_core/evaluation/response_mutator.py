"""
Response Mutator — propõe versões melhores quando resposta falha.

Regras:
- Mantém política comercial.
- Não inventa preço.
- Não remove guardrail.
- Reduz perguntas.
- Deixa mais brasileiro e natural.

Arquivos alteráveis:
- knowledge/refrimix/playbooks/br_chat_sales_style.md
- knowledge/refrimix/playbooks/service_response_matrix.md
- refrimix_core/domain/natural_microcopy.py
- refrimix_core/domain/canonical_response.py

Nunca altera:
- risk_detector.py
- guardrail_validator.py
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


# ── Erros comuns e sugestões de correção ──────────────────────────────────────

COMMON_FAILURES = {
    "usa_portugues_europeu": {
        "description": "Resposta usa português europeu ou termos proibidos",
        "fix_template": "Reescrever mantendo apenas vocabulário brasileiro: 'vc', 'pra', 'qto', 'pq', 'tbl', 'msm'.",
        "examples": [
            ("Como posso ajudá-lo?", "Oi, tudo bem? Em que posso te ajudar?"),
            ("Por favor, envie uma foto.", "Se conseguir, manda uma foto — ajuda a adiantar."),
        ],
    },
    "mais_de_2_perguntas": {
        "description": "Resposta tem mais de 2 perguntas",
        "fix_template": "Reduzir para no máximo 2 perguntas. Priorizar a mais importante.",
        "examples": [
            ("Qual o bairro? Qual o problema? Qual horário prefere?", "Me fala o bairro e qual período prefere: manhã ou tarde?"),
        ],
    },
    "foto_obrigatoria": {
        "description": "Resposta bloqueia por foto",
        "fix_template": "Tornar foto opcional, não bloqueante. Mencionar 'se puder' ou 'se conseguir'.",
        "examples": [
            ("Me manda uma foto do local.", "Se puder, manda uma foto — ajuda a adiantar, mas não trava o atendimento."),
        ],
    },
    "diagnostico_definitivo": {
        "description": "Dá diagnóstico fechado sem avaliar",
        "fix_template": "Usar linguagem de possibilidade ('pode ser', 'provavelmente', 'talvez') e indicar necessidade de avaliação.",
        "examples": [
            ("O problema é a placa.", "O problema pode envolver a placa, sensor, ou até instalação. Precisamos avaliar no local."),
            ("Você precisa trocar o compressor.", "Provavelmente envolve compressor, mas só com avaliação técnica pra confirmar."),
        ],
    },
    "inventou_preco": {
        "description": "Passou preço sem contexto validado",
        "fix_template": "Remover preço inventado. Usar 'visita técnica de R$50' ou 'orçamento no local'.",
        "examples": [
            ("Fica R$300.", "O caminho mais seguro é visita técnica de R$50, assim evaluamos e passamos valor real."),
        ],
    },
    "como_posso_ajudar_depois_cliente_explicar": {
        "description": "Usou 'Como posso ajudar?' depois do cliente já explicar",
        "fix_template": "Não pedir para cliente explicar de novo. Confirmar que entendeu e avanzar.",
        "examples": [
            ("Entendi. Como posso ajudá-lo?", "Perfeito, entendi. Pra agilizar, me fala o bairro e qual período prefere."),
        ],
    },
    "nao_orienta_desligar_em_risco_eletrico": {
        "description": "Risco elétrico sem orientação de desligar",
        "fix_template": "Orientar desligar o equipamento IMEDIATAMENTE. Isso é inegociável.",
        "examples": [
            ("Vamos agendar uma visita.", "IMPORTANTE: mantenha o equipamento desligado até a avaliação. Me conta o bairro e agendamos logo."),
        ],
    },
    "nome_bloqueando_agendamento": {
        "description": "Nome bloqueia agendamento",
        "fix_template": "Nome é opcional. Segue para agendamento mesmo sem nome.",
        "examples": [
            ("Me passa seu nome para agendar.", "Perfeito, vamos agendar. Qual período prefere: manhã ou tarde?"),
        ],
    },
    "texto_longo_demais": {
        "description": "Texto longo para WhatsApp (>800 chars)",
        "fix_template": "Cortar para no máximo 3-4 linhas. Uma ideia por vez.",
        "examples": [
            ("Texto enorme...", "Curto e direto: {ponto principal} | {ação}."),
        ],
    },
    "instagram_fora_de_contexto": {
        "description": "Instagram enviado fora de contexto",
        "fix_template": "Instagram só quando está consultando agenda ou em espera útil.",
        "examples": [
            ("Instagram: @willrefrimix", "Usar Instagram só quando cliente está esperando resposta de agenda."),
        ],
    },
}


# ── Mutador de resposta ───────────────────────────────────────────────────────

@dataclass
class MutationResult:
    """Resultado de uma mutação proposta."""
    original_response: str
    mutated_response: str
    failure_fixed: str
    file_to_modify: str
    patch_instruction: str
    is_safe: bool  # False se tentar alterar guardrail

    def to_dict(self) -> dict:
        return {
            "original_response": self.original_response,
            "mutated_response": self.mutated_response,
            "failure_fixed": self.failure_fixed,
            "file_to_modify": self.file_to_modify,
            "patch_instruction": self.patch_instruction,
            "is_safe": self.is_safe,
        }


# Arquivos que podem ser modificados automaticamente
SAFE_FILES = {
    "knowledge/refrimix/playbooks/br_chat_sales_style.md",
    "knowledge/refrimix/playbooks/service_response_matrix.md",
    "refrimix_core/domain/natural_microcopy.py",
    "refrimix_core/domain/canonical_response.py",
}

# Arquivos que NUNCA podem ser modificados automaticamente
BLOCKED_FILES = {
    "risk_detector.py",
    "guardrail_validator.py",
    "refrimix_core/guards/",
    "agent_graph/guards/",
}


def is_safe_file(filepath: str) -> bool:
    """Verifica se arquivo pode ser modificado automaticamente."""
    for blocked in BLOCKED_FILES:
        if blocked in filepath:
            return False
    for safe in SAFE_FILES:
        if safe in filepath:
            return True
    return False


def propose_mutation(
    original_response: str,
    failure: str,
    context: dict | None = None,
) -> MutationResult | None:
    """
    Propõe uma mutação para corrigir uma falha.

    Args:
        original_response: resposta original que falhou
        failure: nome da falha
        context: contexto adicional (categoria, arquivo origem, etc)

    Returns:
        MutationResult com a resposta mutada e instrução de patch
    """
    ctx = context or {}
    failure_info = COMMON_FAILURES.get(failure)
    if not failure_info:
        return None

    mutated = original_response

    # Aplica correção específica por falha
    if failure == "mais_de_2_perguntas":
        # Reduz para 2 perguntas
        questions = original_response.split("?")
        if len(questions) > 2:
            # Mantém primeira e última pergunta, remove intermediárias
            parts = []
            for i, q in enumerate(questions[:-1]):
                if i < 2:
                    parts.append(q + "?")
            mutated = " ".join(parts)

    elif failure == "foto_obrigatoria":
        # Torna foto opcional
        mutated = re.sub(
            r"(me\s+)?(?:mande|envie|enviar|mandar)\s+(?:uma\s+)?foto",
            "Se puder, manda uma foto",
            mutated,
            flags=re.IGNORECASE,
        )
        if "não trava" not in mutated.lower() and "não bloqueia" not in mutated.lower():
            mutated = mutated + " — isso não trava o atendimento."

    elif failure == "diagnostico_definitivo":
        # Adiciona hedge language
        diagnostic_words = ["é a placa", "é o compressor", "é vazamento", "você precisa trocar"]
        for diag in diagnostic_words:
            if diag in mutated.lower():
                mutated = mutated.replace(diag, "pode ser " + diag.replace("é ", ""))

    elif failure == "inventou_preco":
        # Substitui preço por visita técnica
        mutated = re.sub(r"R\$\s*\d+", "R$50", mutated)
        if "visita técnica" not in mutated and "visita/análise" not in mutated:
            mutated = mutated + " Para ter valor seguro, o caminho é visita técnica de R$50."

    elif failure == "como_posso_ajudar_depois_cliente_explicar":
        # Remove como posso ajudar
        mutated = re.sub(
            r"(?:Entendi\.?\s*)?(?:Bom,?\s*)?(?:Deixa eu|\s*)+\s*como\s+posso\s+ajudar[?]",
            "Perfeito, entendi.",
            mutated,
            flags=re.IGNORECASE,
        )

    elif failure == "nao_orienta_desligar_em_risco_eletrico":
        # Adiciona orientação de desligar
        if "deslig" not in mutated.lower():
            mutated = "⚠️ Mantenha o equipamento DESLIGADO até a avaliação. " + mutated

    elif failure == "nome_bloqueando_agendamento":
        # Remove bloqueio de nome
        mutated = re.sub(
            r"me\s+passa\s+(?:seu\s+)?nome\s+(?:pra|para|que)",
            "Pra agilizar, qual período prefere",
            mutated,
            flags=re.IGNORECASE,
        )

    elif failure == "texto_longo_demais":
        # Trunca para ~600 chars
        if len(mutated) > 700:
            # Find last sentence boundary around 600 chars
            truncated = mutated[:700]
            last_period = truncated.rfind(".")
            last_newline = truncated.rfind("\n")
            cutoff = max(last_period, last_newline)
            if cutoff < 400:
                cutoff = 600
            mutated = truncated[:cutoff + 1]
            if not mutated.endswith((".", "!", "?")):
                mutated = mutated + "."

    # Determina arquivo para modificação
    file_to_modify = ctx.get("source_file", "")
    if not file_to_modify or not is_safe_file(file_to_modify):
        # Tenta determinar arquivo correto pela categoria
        category = ctx.get("category", "")
        if category in ("instalacao", "higienizacao", "manutencao_conserto", "nao_gela"):
            file_to_modify = "refrimix_core/domain/natural_microcopy.py"
        elif "estilo" in file_to_modify or "chat" in file_to_modify:
            file_to_modify = "knowledge/refrimix/playbooks/br_chat_sales_style.md"
        else:
            file_to_modify = "refrimix_core/domain/canonical_response.py"

    patch_instruction = f"Substituir resposta da categoria '{ctx.get('category', 'unknown')}' por: {mutated[:200]}..."

    return MutationResult(
        original_response=original_response,
        mutated_response=mutated,
        failure_fixed=failure,
        file_to_modify=file_to_modify,
        patch_instruction=patch_instruction,
        is_safe=is_safe_file(file_to_modify),
    )


def apply_mutations(
    mutations: list[MutationResult],
    dry_run: bool = True,
) -> dict[str, list[MutationResult]]:
    """
    Aplica mutações nos arquivos permitidos.

    Args:
        mutations: lista de MutationResult
        dry_run: se True, não altera arquivos

    Returns:
        dict com arquivos e mutações aplicadas
    """
    by_file: dict[str, list[MutationResult]] = {}

    for mutation in mutations:
        if not mutation.is_safe:
            continue  # Pula arquivos bloqueados

        if mutation.file_to_modify not in by_file:
            by_file[mutation.file_to_modify] = []
        by_file[mutation.file_to_modify].append(mutation)

    if dry_run:
        return by_file

    # Aplica mutações
    for filepath, file_mutations in by_file.items():
        # Lê arquivo atual
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError:
            continue

        for mutation in file_mutations:
            # Substitui no conteúdo
            if mutation.original_response in content:
                content = content.replace(
                    mutation.original_response,
                    mutation.mutated_response,
                )

        # Escreve de volta
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

    return by_file


if __name__ == "__main__":
    # Teste rápido
    result = propose_mutation(
        original_response="Quero instalar um ar. Como posso ajudá-lo? Me passa seu nome e foto do local.",
        failure="mais_de_2_perguntas",
        context={"category": "instalacao"},
    )
    if result:
        print(f"Failure: {result.failure_fixed}")
        print(f"Mutated: {result.mutated_response}")
        print(f"Safe: {result.is_safe}")