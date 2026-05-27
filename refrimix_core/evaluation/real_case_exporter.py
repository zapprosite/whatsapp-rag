"""Exportador de casos reais anonimizados para o loop de refinamento.

Métricas de anonimização:
- Telefone mascarado: MASCARA_TEL
- Nome mascarado: MASCARA_NOME
- Endereço mascarado: MASCARA_END
- Conversation ID mascarado: MASCARA_CONV

NUNCA exportar dados sensíveis sem anonimização.
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class AnonymizedMessage:
    """Mensagem com dados anonimizados."""
    conversation_id: str
    message_index: int
    sender: str
    text: str
    timestamp: str
    intent: Optional[str] = None
    was_suggested: bool = False
    was_edited: bool = False


class RealCaseExporter:
    """Exportador de casos reais para JSONL."""

    PHONE_PATTERN = re.compile(r'[\+]?[0-9]{1,3}[\s.-]?\(?[0-9]{2}\)?[\s.-]?[0-9]{4,5}[\s.-]?[0-9]{4}')
    NAME_PATTERNS = [
        re.compile(r'\bmeu nome é ([A-Z][a-z]+(?: [A-Z][a-z]+)*)'),
        re.compile(r'\bsou ([A-Z][a-z]+(?: [A-Z][a-z]+)*)'),
        re.compile(r'\bchamo ([A-Z][a-z]+(?: [A-Z][a-z]+)*)'),
    ]
    ADDRESS_PATTERNS = [
        re.compile(r'\b(?:rua|avenida|av\.|travessa|trav\.|alameda|praça|praca)\s+[A-Za-zà-ú\s]+', re.IGNORECASE),
        re.compile(r'\b(?:bairro|neighborhoods?)\s+[A-Za-zà-ú\s]+', re.IGNORECASE),
    ]

    def anonymize_message(
        self,
        conversation_id: str,
        message_index: int,
        text: str,
        sender: str,
        timestamp: str,
        intent: Optional[str] = None,
        was_suggested: bool = False,
        was_edited: bool = False,
    ) -> AnonymizedMessage:
        """Anonimiza mensagem substituindo dados sensíveis."""
        masked_text = text
        masked_text = self.PHONE_PATTERN.sub('MASCARA_TEL', masked_text)
        for pattern in self.NAME_PATTERNS:
            masked_text = pattern.sub('MASCARA_NOME', masked_text)
        for pattern in self.ADDRESS_PATTERNS:
            masked_text = pattern.sub('MASCARA_END', masked_text)
        masked_conv_id = f"MASCARA_CONV_{conversation_id[:8]}"
        return AnonymizedMessage(
            conversation_id=masked_conv_id,
            message_index=message_index,
            sender=sender,
            text=masked_text,
            timestamp=timestamp,
            intent=intent,
            was_suggested=was_suggested,
            was_edited=was_edited,
        )

    def export_real_cases(
        self,
        feedback_store,
        outcome_tracker,
        min_cases: int = 30,
    ) -> list[dict]:
        """Exporta casos reais anonimizados para JSONL."""
        if len(feedback_store.get_all_entries()) < min_cases:
            return []
        dataset = []
        for entry in feedback_store.get_all_entries():
            messages = entry.suggested_response.split('\n')
            for i, msg_text in enumerate(messages):
                if not msg_text.strip():
                    continue
                anonymized = self.anonymize_message(
                    conversation_id=entry.conversation_id,
                    message_index=i,
                    text=msg_text,
                    sender="bot",
                    timestamp=entry.timestamp.isoformat(),
                    intent=entry.intent,
                    was_suggested=True,
                    was_edited=entry.was_edited,
                )
                dataset.append({
                    "conversation_id": anonymized.conversation_id,
                    "message_index": anonymized.message_index,
                    "sender": anonymized.sender,
                    "text": anonymized.text,
                    "timestamp": anonymized.timestamp,
                    "intent": anonymized.intent,
                    "was_suggested": anonymized.was_suggested,
                    "was_edited": anonymized.was_edited,
                    "human_response": entry.human_response if anonymized.was_edited else None,
                })
        return dataset

    def export_to_jsonl(self, dataset: list[dict], output_path: str) -> int:
        """Escreve dataset para arquivo JSONL."""
        count = 0
        with open(output_path, 'w', encoding='utf-8') as f:
            for item in dataset:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
                count += 1
        return count