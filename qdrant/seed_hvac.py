"""
Seed HVAC knowledge base into whatsapp_rag collection.
Uses FastEmbed (paraphrase-multilingual-MiniLM-L12-v2) for CPU embeddings.
Run: python qdrant/seed_hvac.py

Chunks escritos na voz do Will (Refrimix) para FAQ clone do dono.
"""

from __future__ import annotations
import logging

from fastembed import TextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.http import models

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

COLLECTION = "hermes_hvac_rag_service_staging"
VECTOR_DIM = 384
EMBEDDING_MODEL = "nomic-ai/nomic-embed-text-v1.5"

# ─── Knowledge base na voz do Will ────────────────────────────────────────────
# outcome: analise_tecnica | higienizacao_preventiva | reuniao_projeto | duvida

CHUNKS = [
    # ── INSTALAÇÃO ────────────────────────────────────────────────────────────
    {
        "service_name": "instalacao",
        "outcome": "analise_tecnica",
        "title": "Marcas de split que instalamos",
        "text": (
            "A gente instala qualquer marca de split: Springer Carrier, Daikin, Midea, LG, Samsung, Elgin. "
            "Não vendemos o equipamento — você compra onde quiser, a gente vai lá e instala com todo o material incluído: "
            "cobre, dreno, fiação, suporte. "
            "A visita técnica pra avaliar o local é gratuita e sem compromisso. "
            "Me manda o endereço e quantos equipamentos são que eu já marco pra você."
        ),
    },
    {
        "service_name": "instalacao",
        "outcome": "analise_tecnica",
        "title": "Instalação em drywall, vidro e forro de gesso",
        "text": (
            "Pode! A gente trabalha com drywall, vidro temperado e forro de gesso. "
            "Cada superfície tem fixação específica — usamos buchas e suportes adequados pra cada caso. "
            "No forro de gesso a gente passa a tubulação por dentro, com saída discreta pra evaporadora. "
            "Antes de furar, a gente avalia se a estrutura aguenta o peso. "
            "Se precisar de reforço, a gente orienta. Sem surpresa no dia."
        ),
    },
    {
        "service_name": "instalacao",
        "outcome": "analise_tecnica",
        "title": "Quanto tempo leva a instalação",
        "text": (
            "Até 3 splits a gente resolve em 1 dia. Pra 4 ou mais, em geral 2 dias. "
            "O processo é: visita técnica primeiro pra medir e planejar, depois agenda o dia da instalação. "
            "Inclui marcação, furação, suporte externo, tubulação em cobre, dreno, fiação e teste completo. "
            "No final a gente orienta você sobre uso e manutenção. "
            "Garantia de 12 meses na instalação. Me fala quantos equipamentos são?"
        ),
    },
    {
        "service_name": "instalacao",
        "outcome": "analise_tecnica",
        "title": "Instalar equipamento que o cliente já comprou",
        "text": (
            "Claro, pode trazer! A gente instala equipamento comprado em loja, internet, qualquer lugar. "
            "Quando chegamos, verificamos as condições do aparelho — se tiver algum problema de fábrica, já avisamos. "
            "O orçamento é só mão de obra e material de instalação, não cobramos o equipamento. "
            "Springer, Carrier, Daikin, Midea, LG, Samsung — todos a gente instala. "
            "Me manda foto da caixa com o modelo que eu faço o orçamento."
        ),
    },
    {
        "service_name": "instalacao",
        "outcome": "analise_tecnica",
        "title": "Instalação com tubulação em forro de gesso",
        "text": (
            "A gente faz passagem de tubulação embutida no forro de gesso sim. "
            "Usamos cobre flexível pra facilitar as curvas dentro do forro. "
            "A saída fica discreta, com grelha de acabamento. "
            "Vedação com borracha e silicone neutro — sem risco de vazamento. "
            "É o tipo de serviço que precisa de visita técnica primeiro pra medir o trajeto. "
            "Me manda o endereço e a planta baixa se tiver, que já marco a visita."
        ),
    },
    # ── MANUTENÇÃO ────────────────────────────────────────────────────────────
    {
        "service_name": "manutencao",
        "outcome": "analise_tecnica",
        "title": "Barulho de vibração ao ligar",
        "text": (
            "Barulho de vibração é quase sempre suporte do compressor desgastado ou coxim com folga. "
            "Pode ser também o ventilador da condensadora desbalanceado, ou a tubulação encostando na parede. "
            "A gente vai lá, identifica a origem, ajusta suporte, troca coxim se precisar e testa. "
            "Não é nada grave, mas melhor resolver logo antes de virar problema no compressor. "
            "Qual o modelo do aparelho e em que cidade você tá?"
        ),
    },
    {
        "service_name": "manutencao",
        "outcome": "analise_tecnica",
        "title": "Split que gela demais e desliga sozinho",
        "text": (
            "Quando o split gela demais e cai por proteção, o mais comum é filtro entupido causando superaquecimento, "
            "ou baixa pressão de gás — aí o sensor de temperatura entra em pânico e desliga. "
            "Pode ser também o sensor de temperatura do evaporador com defeito. "
            "A gente diagnóstica na hora com manômetro e multímetro. "
            "Se for gás, recarregamos e verificamos vazamento. Se for sensor, trocamos. "
            "Me fala a marca e o BTU do aparelho."
        ),
    },
    {
        "service_name": "manutencao",
        "outcome": "analise_tecnica",
        "title": "Ar não esquenta no inverno",
        "text": (
            "Ar que não aquece no inverno é clássico de baixa pressão de gás ou compressor com desgaste. "
            "A gente coloca o manômetro, verifica a pressão de trabalho e já sabe o diagnóstico. "
            "Se tiver vazamento de gás, a gente localiza, corrige e recarrega — R-410A ou R-22 conforme o modelo. "
            "O serviço inclui verificação de estanqueidade depois. "
            "Qual a marca e capacidade do aparelho? E em que bairro você tá?"
        ),
    },
    {
        "service_name": "manutencao",
        "outcome": "analise_tecnica",
        "title": "Vazamento de água do split",
        "text": (
            "Vazamento de água é quase sempre dreno entupido — sujeira, mofo, alga bloqueando a saída. "
            "Às vezes é a instalação fora de nível, que faz a água escorrer pelo lado errado. "
            "A gente limpa o dreno com compressor de ar e produto bacteriostático. "
            "Se tiver mal instalado, a gente corrige o nível. "
            "Enquanto isso, desliga o aparelho pra não alagar. "
            "Me manda foto mostrando onde tá vazando que já oriento."
        ),
    },
    {
        "service_name": "manutencao",
        "outcome": "analise_tecnica",
        "title": "Split não liga — possível queimado",
        "text": (
            "Split que não liga pode ser desde um capacitor queimado — peça barata, troca rápida — "
            "até placa eletrônica danificada por surto de tensão. "
            "A gente verifica o capacitor com multímetro, testa a placa e checa os fusíveis internos. "
            "Troca de placa tem garantia de 6 meses no componente. "
            "Me fala: quando você tentou ligar, deu alguma luz piscando? "
            "Isso já me ajuda muito a identificar o problema antes de ir lá."
        ),
    },
    # ── PMOC ──────────────────────────────────────────────────────────────────
    {
        "service_name": "pmoc",
        "outcome": "analise_tecnica",
        "title": "O que é PMOC e para quem é obrigatório",
        "text": (
            "PMOC é o Programa de Manutenção Preventiva e Operacional de climatização. "
            "É obrigatório por lei pra sistemas acima de 60.000 BTU em estabelecimentos comerciais, industriais e de serviços. "
            "Prédio de escritórios, hotel, restaurante, hospital, shopping — todos precisam. "
            "Sem PMOC, você corre risco de notificação e multa na fiscalização. "
            "A gente faz o programa completo: laudos, registros, ART de engenheiro. "
            "Me fala quantos equipamentos e o tipo do estabelecimento que eu já faço um orçamento."
        ),
    },
    {
        "service_name": "pmoc",
        "outcome": "analise_tecnica",
        "title": "PMOC para alvará do bombeiros",
        "text": (
            "Pra alvará do corpo de bombeiros, o PMOC precisa ter laudo técnico, certificado de execução "
            "e ART do engenheiro responsável — a gente emite tudo isso. "
            "O documento cobre as exigências da ABNT NBR 16001 e das legislações estaduais e municipais. "
            "Já ajudamos muita empresa no Guarujá e região a regularizar a situação. "
            "Me manda o CNPJ e endereço do estabelecimento que eu verifico o que você precisa exatamente."
        ),
    },
    {
        "service_name": "pmoc",
        "outcome": "analise_tecnica",
        "title": "O que inclui o programa de manutenção PMOC",
        "text": (
            "Nosso PMOC inclui visita trimestral de filtros, limpeza semestral completa de evaporadora e condensadora, "
            "verificação anual de pressão de gás, testes elétricos semestrais "
            "e laudo técnico anual pro órgão regulador. "
            "Tudo registrado e arquivado por no mínimo 5 anos — pra qualquer fiscalização que aparecer. "
            "Você recebe certificado de higiene operacional após cada execução. "
            "Quer que eu monte um cronograma pra você?"
        ),
    },
    {
        "service_name": "pmoc",
        "outcome": "analise_tecnica",
        "title": "Custo do PMOC para múltiplos equipamentos",
        "text": (
            "O custo do PMOC é calculado pela quantidade de equipamentos e complexidade do sistema. "
            "Até 5 equipamentos: valor fixo mensal acessível. "
            "De 6 a 10: tem desconto progressivo. "
            "Acima de 10: orçamento personalizado com desconto por volume. "
            "Tudo incluso: visitas, laudos, ART e certificado. Sem surpresa no boleto. "
            "Me fala quantos aparelhos são e eu monto a proposta ainda hoje."
        ),
    },
    {
        "service_name": "pmoc",
        "outcome": "analise_tecnica",
        "title": "Como funciona o processo para contratar PMOC",
        "text": (
            "É simples: você me manda o endereço e quantidade de equipamentos, "
            "eu passo o orçamento, a gente agenda uma visita técnica pra levantamento, "
            "assina o contrato e já começamos o programa. "
            "A primeira visita não cobra nada — orçamento é gratuito. "
            "Do levantamento até o início do programa, em geral menos de 2 semanas. "
            "Me manda o endereço que eu já marco."
        ),
    },
    # ── CONSULTORIA ──────────────────────────────────────────────────────────
    {
        "service_name": "consultoria",
        "outcome": "reuniao_projeto",
        "title": "Cálculo de BTU para o ambiente",
        "text": (
            "Pra calcular o BTU certo, preciso saber a metragem do ambiente, "
            "pra qual lado fica o sol da tarde, quantas pessoas usam o espaço "
            "e quantos equipamentos eletrônicos tem lá (computadores, servidores, TV). "
            "A regra geral é 600 a 800 BTU por m², mas cada caso é um caso. "
            "Sala de reunião com 20m² e 8 pessoas, por exemplo, precisa de 24.000 a 30.000 BTU. "
            "Me manda esses dados que eu calculo pra você agora."
        ),
    },
    {
        "service_name": "consultoria",
        "outcome": "reuniao_projeto",
        "title": "Projeto de climatização para obra nova",
        "text": (
            "Melhor contratar a consultoria antes da obra fechar as paredes — "
            "evita quebra e reforma depois. "
            "A gente faz o projeto completo: cálculo de carga térmica por ambiente, "
            "especificação dos equipamentos, projeto de tubulação e dreno, "
            "coordenação com projeto elétrico e hidráulico. "
            "Entregamos em PDF com memorial descritivo e cronograma de execução. "
            "Me manda a planta baixa que eu já começo a avaliar."
        ),
    },
    {
        "service_name": "consultoria",
        "outcome": "reuniao_projeto",
        "title": "Split ou cassete para loja comercial",
        "text": (
            "Depende do layout da loja e do teto. "
            "Split é mais barato e instalação mais simples. "
            "Cassete distribui o ar de forma mais uniforme pelos 4 lados — fica mais bonito em loja com teto rebaixado. "
            "Pra loja de 40m² com pé-direito de 3m, em geral 2 splits de 12.000 BTU ou 1 cassete de 36.000 BTU. "
            "Cassete permite controle por zona se a loja tiver ambientes separados. "
            "Me manda a planta ou me descreve o espaço que eu indico o melhor."
        ),
    },
    {
        "service_name": "consultoria",
        "outcome": "reuniao_projeto",
        "title": "Eficiência energética e economia na conta de luz",
        "text": (
            "Equipamento com selo PROCEL classe A gasta menos energia — o investimento a mais paga em 2 a 3 anos. "
            "Pra uso comercial intenso de 12h por dia, o retorno é ainda mais rápido. "
            "A gente ajuda a escolher o equipo certo pro seu padrão de uso, "
            "sem te empurrar o mais caro à toa. "
            "Se quiser, fazemos uma análise de custo-benefício comparando modelos. "
            "Me fala quantas horas por dia você usa e o porte do ambiente."
        ),
    },
    {
        "service_name": "consultoria",
        "outcome": "reuniao_projeto",
        "title": "Assessoria para climatização residencial",
        "text": (
            "A gente oferece assessoria gratuita pra climatização residencial. "
            "A gente vai até você, faz o levantamento sem custo, sugere os melhores equipamentos "
            "pro seu padrão de uso e orçamenta tudo: equipamento, material e instalação. "
            "Se a obra ainda tá no começo, a gente já inclui no projeto pra evitar quebra depois. "
            "É sem compromisso — você decide se contrata ou não depois do orçamento. "
            "Me manda o endereço pra marcar a visita."
        ),
    },
    # ── HIGIENIZAÇÃO ─────────────────────────────────────────────────────────
    {
        "service_name": "higienizacao",
        "outcome": "higienizacao_preventiva",
        "title": "Diferença entre limpeza e higienização",
        "text": (
            "Limpeza é tirar a poeira dos filtros — você mesmo pode fazer em casa a cada 15 dias. "
            "Higienização é outra coisa: limpeza profunda com produto bacteriostático que mata ácaros, "
            "fungos e bactérias que você não vê, mas tá respirando. "
            "A gente inclui sanitização por ozônio — elimina cheiro e microorganismo na superfície interna. "
            "Depois do serviço, emitimos certificado de higienização. "
            "Uso doméstico: a cada 6 meses. Comercial: a cada 3 meses."
        ),
    },
    {
        "service_name": "higienizacao",
        "outcome": "higienizacao_preventiva",
        "title": "Higienização com ozônio para eliminar cheiro",
        "text": (
            "O ozônio é o método mais eficaz pra cheiro forte no ar condicionado — "
            "elimina mofo, ácaro e micro-organismo na superfície das pás do evaporador e nos dutos. "
            "O processo leva uns 30 minutos de ação, depois 15 minutos de ventilação do ambiente. "
            "Depois disso o ar fica limpo de verdade — sem máscara de perfume, sem produto temporário. "
            "É seguro pra humanos e animais depois da ventilação. "
            "Quer agendar? Me manda o endereço e quantos aparelhos são."
        ),
    },
    {
        "service_name": "higienizacao",
        "outcome": "higienizacao_preventiva",
        "title": "Com que frequência fazer higienização",
        "text": (
            "Uso doméstico: a cada 6 meses. "
            "Escritório ou loja: a cada 3 meses. "
            "Restaurante ou hospital: mensal. "
            "Os sinais de que tá na hora: cheiro forte quando liga, espirros ou alergias que pioram em casa, "
            "água escura saindo do dreno, performance caindo sem motivo. "
            "Higienização bem feita melhora o desempenho e reduz consumo de energia em até 15%. "
            "Posso agendar a próxima pra você não esquecer?"
        ),
    },
    {
        "service_name": "higienizacao",
        "outcome": "higienizacao_preventiva",
        "title": "Higienização de dutos — remove ácaros e fungos",
        "text": (
            "Pra sistemas com dutos, a gente usa equipamento de pressão negativa + produtos químicos certificados. "
            "Remove até 99% de ácaros e fungos nos dutos. "
            "O processo: inspeção com câmera, escovação mecânica, aplicação de bacteriostático, secagem por sucção "
            "e laudo de qualidade do ar antes e depois. "
            "Muita gente que sofre de alergia vê melhora significativa depois desse serviço. "
            "Qual o tamanho do sistema e onde fica?"
        ),
    },
    {
        "service_name": "higienizacao",
        "outcome": "higienizacao_preventiva",
        "title": "Certificado de higienização após o serviço",
        "text": (
            "Sim, emitimos certificado de higienização após cada serviço. "
            "Consta: data, produtos utilizados, método de sanitização, número de série do equipamento e laudo do ar. "
            "Vale pra auditorias, alvarás e seguros. "
            "A gente mantém o registro por 5 anos — se precisar de segunda via, é só pedir. "
            "Também agendamos o próximo serviço preventivo pra você não perder o prazo. "
            "Quer agendar agora?"
        ),
    },
    # ── PROJETO CENTRAL ──────────────────────────────────────────────────────
    {
        "service_name": "projeto-central",
        "outcome": "reuniao_projeto",
        "title": "Projeto central para escritório comercial",
        "text": (
            "Pra escritório comercial, a gente dimensiona por zona ou por andar. "
            "Podemos especificar chiller, rooftop ou sistema VRF dependendo da metragem e do orçamento. "
            "O projeto inclui dutos com difusores e registros, sistema de controle centralizado (DDC ou BMS) "
            "e coordenação com projeto elétrico e estrutural. "
            "Atendemos de 1.000 a 10.000 m². Engenheiros próprios com ART. "
            "Me manda a planta e a metragem total que eu marco uma reunião técnica."
        ),
    },
    {
        "service_name": "projeto-central",
        "outcome": "reuniao_projeto",
        "title": "Split central ou multisplit para múltiplos ambientes",
        "text": (
            "Pra 6 ambientes ou mais, as opções são: "
            "Multi V (1 condensadora externa pra até 6 evaporadoras) — econômico e com controle individual. "
            "Multisplit com condensadoras menores — mais flexível pra layout complexo. "
            "VRF — mais eficiente, controle preciso por zona, investimento maior mas retorno em energia. "
            "A recomendação depende da arquitetura e de como cada ambiente é usado. "
            "Me fala o número de ambientes e a metragem de cada um que eu oriento."
        ),
    },
    {
        "service_name": "projeto-central",
        "outcome": "reuniao_projeto",
        "title": "Projeto para galpão industrial",
        "text": (
            "Galpão industrial é especialidade nossa. "
            "Pé-direito alto, máquinas gerando calor, variação de ocupação — tudo isso entra no cálculo. "
            "A gente considera tipo de telhado (metálico ou com isolamento), presença de máquinário "
            "e metas de temperatura por zona. "
            "Sistemas indicados: evaporativo pra galpões grandes sem exigência de temperatura precisa, "
            "split industrial de alta capacidade, ou sistema central com dutos pra maior controle. "
            "Me manda a metragem e localização que marco uma visita técnica."
        ),
    },
    {
        "service_name": "projeto-central",
        "outcome": "reuniao_projeto",
        "title": "Climatização para restaurante com cozinha",
        "text": (
            "Restaurante com cozinha tem que separar bem as zonas. "
            "Cozinha gera calor intenso e precisa de sistema independente do salão, "
            "mais exaustão mecânica pra tirar o calor e gordura do ambiente. "
            "Salão precisa de temperatura confortável pro cliente — cassete distribui bem o ar. "
            "A gente faz projeto que cumpre as normas da ANVISA e municipais. "
            "É o tipo de projeto que precisa de visita técnica e reunião com o projeto do arquiteto. "
            "Me manda o endereço que marco."
        ),
    },
    {
        "service_name": "projeto-central",
        "outcome": "reuniao_projeto",
        "title": "Sistema central com controle individual por ambiente",
        "text": (
            "Sistema central moderno com controle individual por zona é possível e não precisa ser caro. "
            "Termostato digital por zona, controle via celular (IoT), integração com BMS. "
            "Cada ambiente programa a temperatura que quiser e no horário que quiser. "
            "VRF ou split central com controladores individuais é a solução mais elegante. "
            "Pra saber o que faz sentido pro seu caso, precisamos ver a planta e entender como cada ambiente é usado. "
            "Posso marcar uma reunião técnica sem compromisso?"
        ),
    },
    # ── PLAYBOOK COMERCIAL / PREÇOS ─────────────────────────────────────────
    {
        "service_name": "instalacao",
        "outcome": "analise_tecnica",
        "doc_type": "pricing",
        "priority": 5,
        "title": "Preço de instalação de split",
        "text": (
            "Quando o lead pergunta preço de instalação de split, responda direto: "
            "instalação padrão no Guarujá fica R$800. Para Santos, São Vicente e Praia Grande fica R$850 por causa do deslocamento. "
            "Inclui mão de obra e material básico de instalação. Depois peça cidade, tipo do aparelho e endereço "
            "pra confirmar se é instalação padrão ou se precisa visita técnica gratuita."
        ),
    },
    {
        "service_name": "higienizacao",
        "outcome": "higienizacao_preventiva",
        "doc_type": "pricing",
        "priority": 5,
        "title": "Preço de higienização de split",
        "text": (
            "Quando o lead pergunta preço de higienização, responda direto: higienização de split fica R$200 por aparelho. "
            "Explique em uma frase que é limpeza profunda com produto bacteriostático, não só lavar filtro. "
            "Depois pergunte quantos aparelhos são. A cidade fica para a próxima mensagem se ainda faltar."
        ),
    },
    {
        "service_name": "instalacao",
        "outcome": "analise_tecnica",
        "doc_type": "objection",
        "priority": 10,
        "title": "Objeção de preço baixo do concorrente",
        "text": (
            "Se o lead compara com instalação muito barata, não ataque o concorrente. "
            "Diga que entende, mas instalação de ar precisa de cobre, dreno, suporte, vácuo e teste de pressão. "
            "Preço muito baixo costuma cortar etapa que depois vira vazamento ou perda de garantia. "
            "Finalize oferecendo confirmar o caso por foto/endereço."
        ),
    },
    {
        "service_name": None,
        "outcome": "onboarding",
        "doc_type": "sales_playbook",
        "priority": 15,
        "title": "Estilo de atendimento WhatsApp",
        "text": (
            "O Will deve responder como dono prestativo no WhatsApp: curto, humano e prático. "
            "Evite lista, texto grande e frase de call center. Cada resposta deve resolver a dúvida principal "
            "e fazer uma pergunta que leve para orçamento, visita técnica, endereço, quantidade de aparelhos ou reunião."
        ),
    },
    {
        "service_name": "pmoc",
        "outcome": "analise_tecnica",
        "doc_type": "sales_playbook",
        "priority": 10,
        "title": "Qualificação de PMOC",
        "text": (
            "Para PMOC, qualifique tipo de estabelecimento, cidade, quantidade de aparelhos e BTU aproximado. "
            "Se o lead citar clínica, restaurante, empresa ou alvará, trate como lead quente. "
            "Explique que a proposta depende do levantamento, laudos e ART, e conduza para visita/reunião técnica."
        ),
    },
    {
        "service_name": None,
        "outcome": "duvida",
        "doc_type": "sales_playbook",
        "priority": 100,
        "title": "Regra Anti-Alucinação: Como lidar com preços e serviços não tabelados",
        "text": (
            "Se o cliente perguntar o preço de um serviço que não consta explicitamente no seu conhecimento atual "
            "(exemplo: conserto de placa, carga de gás específica, instalação complexa), VOCÊ NÃO PODE INVENTAR UM VALOR. "
            "Responda profissionalmente: 'Para te passar o valor exato desse serviço, vou precisar avaliar melhor os detalhes. "
            "Você consegue me mandar uma foto ou confirmar o modelo do aparelho? Assim eu calculo e te envio o orçamento correto.' "
            "Nunca invente preços, nunca prometa prazos e nunca diga que fazemos serviços de linha branca (como geladeira ou máquina de lavar) "
            "se não estiver no seu contexto de climatização."
        ),
    },
]


def main() -> None:
    logger.info(f"Modelo de embedding: {EMBEDDING_MODEL}")
    model = TextEmbedding(model=EMBEDDING_MODEL, max_length=512)

    logger.info("Gerando embeddings...")
    texts = [c["text"] for c in CHUNKS]
    embeddings = list(model.embed(texts))

    logger.info("Conectando ao Qdrant em localhost:6333")
    qc = QdrantClient(url="http://localhost:6333")

    logger.info(f"Recriando coleção '{COLLECTION}'")
    qc.recreate_collection(
        collection_name=COLLECTION,
        vectors_config=models.VectorParams(
            size=VECTOR_DIM,
            distance=models.Distance.COSINE,
        ),
    )

    points = []
    for i, (chunk, embedding) in enumerate(zip(CHUNKS, embeddings)):
        points.append(
            models.PointStruct(
                id=i + 1,
                vector=embedding.tolist(),
                payload={
                    "service_name": chunk.get("service_name"),
                    "outcome": chunk["outcome"],
                    "title": chunk["title"],
                    "doc_type": chunk.get("doc_type", "technical"),
                    "priority": chunk.get("priority", 50),
                    "source": "seed_hvac.py",
                    "text": chunk["text"],
                },
            )
        )

    logger.info(f"Inserindo {len(points)} pontos...")
    operation_info = qc.upsert(
        collection_name=COLLECTION,
        points=points,
    )
    logger.info(f"Upsert completo: {operation_info}")

    coll = qc.get_collection(COLLECTION)
    logger.info(f"Coleção '{COLLECTION}': {coll.points_count} pontos, dim={VECTOR_DIM}")
    logger.info("Seed OK!")


if __name__ == "__main__":
    main()
