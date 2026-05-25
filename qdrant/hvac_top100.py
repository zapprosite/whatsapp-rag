"""Top 100 FAQ para RAG de vendas e atendimento da Refrimix.

O formato e a copy seguem o padrão pt-BR/SP documentado em AGENTS.md e
GUIDE_REFINAMENTO.md: resposta curta, natural, sem PT-PT, sem inglês em copy
de cliente e sempre com próximo passo claro.
"""

from __future__ import annotations

from typing import Any


VALID_SERVICES = {
    None,
    "instalacao",
    "manutencao",
    "higienizacao",
    "pmoc",
    "consultoria",
    "projeto-central",
}


def faq(
    question: str,
    answer: str,
    service_name: str | None = None,
    outcome: str = "duvida",
    priority: int = 50,
    tags: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "question": question,
        "answer": answer,
        "service_name": service_name,
        "outcome": outcome,
        "priority": priority,
        "tags": tags,
    }


TOP100_FAQ: list[dict[str, Any]] = [
    # Onboarding e triagem
    faq("Oi, vocês fazem serviço de ar-condicionado?", "Fazemos sim. Aqui é o Will da Refrimix. A gente trabalha com instalação, manutenção, higienização, PMOC e projetos de climatização. Você precisa de qual desses serviços?", None, "onboarding", 5, ("onboarding",)),
    faq("Bom dia, preciso de ajuda com meu ar.", "Bom dia! Me conta rapidinho o que está acontecendo com o ar: não gela, está pingando, faz barulho ou é instalação nova?", None, "onboarding", 5, ("onboarding",)),
    faq("Vocês atendem em quais cidades?", "Atendemos Guarujá, Santos, São Vicente, Praia Grande e região da Baixada Santista. Me passa a cidade e o serviço que você precisa?", None, "onboarding", 10, ("regiao",)),
    faq("Vocês conseguem atender hoje?", "Consigo verificar a agenda. Me fala a cidade, o bairro e se é instalação, manutenção ou higienização?", None, "onboarding", 10, ("agenda",)),
    faq("Como funciona o orçamento?", "Primeiro a gente entende o serviço pelo WhatsApp. Só instalação high-wall simples e higienização high-wall têm preço fixo. O restante vai para análise técnica de R$50 abatível. Qual serviço você precisa?", None, "onboarding", 15, ("orcamento",)),
    faq("Você manda orçamento por escrito?", "Mando sim. Pra eu montar certinho, você me passa o serviço, a cidade, o modelo do aparelho e uma foto da etiqueta ou do local?", None, "onboarding", 15, ("orcamento",)),
    faq("Vocês fazem serviço para empresa?", "Fazemos sim. Atendemos loja, escritório, clínica, restaurante, condomínio e indústria. Me fala o tipo de empresa e quantos aparelhos são?", None, "onboarding", 10, ("empresa",)),
    faq("Vocês atendem residência?", "Atendemos sim. Me conta se é instalação, manutenção ou higienização e em qual bairro fica o aparelho?", None, "onboarding", 10, ("residencial",)),
    faq("Quero falar com uma pessoa.", "Pode deixar. Eu já vou conduzir por aqui e, se precisar, alguém da equipe assume. Pra adiantar, qual serviço você precisa?", None, "escalar_humano", 10, ("handoff",)),
    faq("Já sou cliente da Refrimix.", "Perfeito. Me passa seu nome, o endereço do atendimento e o que aconteceu com o equipamento?", None, "onboarding", 10, ("pos-venda",)),
    faq("É urgente, meu ar parou.", "Entendi. Me fala a cidade e consegue mandar uma foto do aparelho ou do painel, se tiver alguma luz ou código aparecendo?", None, "analise_tecnica", 10, ("urgencia",)),
    faq("Não sei explicar o problema.", "Sem problema. Pra eu te orientar certinho: é instalação, manutenção ou higienização?", None, "duvida", 10, ("ambigua",)),

    # Instalação
    faq("Quanto custa para instalar um split?", "Se for split high-wall com acesso simples, fica R$800 no Guarujá ou R$850 em Santos, São Vicente e Praia Grande. Me manda cidade, BTU e fotos da unidade interna, externa, quadro de luz e dreno?", "instalacao", "analise_tecnica", 5, ("preco",)),
    faq("O que está incluso na instalação?", "No preço fixo entra instalação high-wall com acesso simples, material padrão, dreno, suporte, fiação básica e teste. Se tiver telhado, escada alta ou distância grande, vira análise de R$50 abatível. Me manda fotos do local?", "instalacao", "analise_tecnica", 10, ("incluso",)),
    faq("Comprei o ar na loja. Vocês instalam?", "Instalamos sim. Se for high-wall com acesso simples, entra no preço fixo; se tiver acesso difícil, precisa análise de R$50 abatível. Me manda foto da caixa, unidade interna, externa e ponto elétrico?", "instalacao", "analise_tecnica", 10, ("equipamento-cliente",)),
    faq("Quais marcas vocês instalam?", "A gente instala as principais marcas, como Springer Carrier, Daikin, Midea, LG, Samsung e Elgin. Qual é a marca e o BTU do seu aparelho?", "instalacao", "analise_tecnica", 15, ("marcas",)),
    faq("Não sei quantos BTUs tem meu aparelho.", "Sem problema. Me manda uma foto da etiqueta lateral ou da caixa para eu identificar o modelo e confirmar o caminho da instalação?", "instalacao", "analise_tecnica", 15, ("btu",)),
    faq("Instala em apartamento?", "Instalamos sim. Para manter preço fixo, preciso confirmar acesso simples, ponto elétrico e destino do dreno. Me manda fotos da evaporadora, condensadora, quadro de luz e dreno?", "instalacao", "analise_tecnica", 15, ("apartamento",)),
    faq("Dá pra instalar a condensadora na varanda?", "Em muitos casos dá, mas precisa ver ventilação, acesso e regra do condomínio. Se for simples, fica no preço fixo; se exigir acesso especial, análise de R$50 abatível. Me manda foto da varanda?", "instalacao", "analise_tecnica", 15, ("condensadora",)),
    faq("Instala em parede de drywall ou gesso?", "Instala, mas precisa avaliar a estrutura e a fixação correta. Me manda foto da parede e o BTU do aparelho?", "instalacao", "analise_tecnica", 15, ("drywall",)),
    faq("A tubulação vai ficar muito longe. Dá pra fazer?", "Dá para fazer em vários casos, mas distância maior sai do preço fixo e precisa análise técnica de R$50 abatível. Me manda foto do caminho entre evaporadora e condensadora?", "instalacao", "analise_tecnica", 15, ("tubulacao",)),
    faq("Precisa de ponto elétrico separado?", "O ideal é ter circuito adequado para o ar-condicionado. A gente verifica a infraestrutura e orienta o que precisa antes de instalar. Qual o BTU do aparelho?", "instalacao", "analise_tecnica", 20, ("eletrica",)),
    faq("Quanto tempo demora uma instalação?", "High-wall com acesso simples normalmente resolve no mesmo dia. Telhado, escada alta, distância grande ou sistema maior precisa análise técnica de R$50 abatível. Qual é o seu caso?", "instalacao", "analise_tecnica", 20, ("prazo",)),
    faq("Tem garantia na instalação?", "Tem sim. A instalação feita pela Refrimix tem garantia de serviço. Pra confirmar o escopo, me manda a cidade, o modelo e a foto do local?", "instalacao", "analise_tecnica", 20, ("garantia",)),
    faq("Vocês instalam aparelho usado?", "A gente avalia. Antes de instalar usado, precisa conferir estado do equipamento e se ele está completo. Me manda foto da etiqueta e das peças?", "instalacao", "analise_tecnica", 20, ("usado",)),
    faq("Tenho vários aparelhos para instalar.", "Ótimo. Se forem high-wall simples, dá para cotar direto por unidade; se tiver acesso difícil ou sistemas diferentes, precisa análise de R$50 abatível. Quantos são e em qual cidade?", "instalacao", "analise_tecnica", 10, ("volume",)),
    faq("Por que em Santos, São Vicente e Praia Grande é outro valor?", "Por causa do deslocamento e logística. A instalação padrão nessas cidades fica R$850. Me passa o bairro e o modelo do aparelho?", "instalacao", "analise_tecnica", 10, ("deslocamento",)),
    faq("Não quero quebrar parede.", "A gente tenta fazer da forma mais limpa possível. Se precisar acabamento ou passagem especial, sai do preço fixo e entra análise de R$50 abatível. Me manda foto do ambiente?", "instalacao", "analise_tecnica", 20, ("acabamento",)),
    faq("O acesso da condensadora é difícil.", "Acesso difícil sai do preço fixo por segurança. Nesse caso a análise técnica custa R$50 e abate se aprovar o orçamento. Me manda foto do local da condensadora?", "instalacao", "analise_tecnica", 10, ("acesso",)),
    faq("Vocês vendem o aparelho também?", "A Refrimix foca na instalação e no serviço técnico. Você pode comprar onde preferir e a gente te orienta o modelo correto. Qual o tamanho do ambiente?", "instalacao", "reuniao_projeto", 20, ("compra",)),

    # Manutenção
    faq("Meu ar não está gelando.", "Quando não gela, precisa diagnóstico. A análise técnica no local custa R$50 e abate se aprovar o orçamento. Me fala marca, BTU, cidade e manda foto da etiqueta?", "manutencao", "analise_tecnica", 5, ("nao-gela",)),
    faq("O ar está pingando água dentro de casa.", "Isso costuma ser dreno entupido ou aparelho fora de nível. Desliga por enquanto e me manda uma foto do ponto onde está pingando?", "manutencao", "analise_tecnica", 5, ("vazamento",)),
    faq("Meu ar está fazendo barulho.", "Barulho pode vir de turbina, fixação, coxim ou condensadora. Você consegue mandar um vídeo curto com o som?", "manutencao", "analise_tecnica", 10, ("barulho",)),
    faq("O ar liga e desliga sozinho.", "Pode ser proteção por sujeira, sensor, pressão de gás ou parte elétrica. Me manda a marca e diz depois de quantos minutos ele desliga?", "manutencao", "analise_tecnica", 10, ("liga-desliga",)),
    faq("O split não liga mais.", "Pode ser capacitor, placa, fusível ou alimentação elétrica. Aparece alguma luz piscando no painel? Se puder, me manda foto.", "manutencao", "analise_tecnica", 10, ("nao-liga",)),
    faq("Senti cheiro de queimado.", "Desliga o aparelho e não força o uso. Me manda a cidade, a marca e se o cheiro vem da evaporadora ou da condensadora?", "manutencao", "analise_tecnica", 5, ("seguranca",)),
    faq("O controle não funciona.", "Pode ser pilha, sensor do controle ou receptor da evaporadora. Troca as pilhas e, se continuar, me manda foto do controle e do aparelho?", "manutencao", "analise_tecnica", 25, ("controle",)),
    faq("Apareceu código de erro no painel.", "Me manda uma foto do código ou escreve exatamente o que aparece para eu direcionar melhor o diagnóstico?", "manutencao", "analise_tecnica", 10, ("erro",)),
    faq("A evaporadora está congelando.", "Congelamento costuma ter relação com fluxo de ar, sujeira, gás ou sensor. Desliga para não forçar e me manda modelo e cidade?", "manutencao", "analise_tecnica", 10, ("congelando",)),
    faq("Precisa completar gás?", "Antes de colocar gás, precisa entender se existe vazamento. Me manda o modelo do aparelho e o sintoma que ele apresenta?", "manutencao", "analise_tecnica", 10, ("gas",)),
    faq("Quanto custa carga de gás?", "Carga de gás não tem preço fechado sem verificar vazamento, tipo de gás e condição do aparelho. A análise custa R$50 e abate se aprovar o orçamento. Me manda foto da etiqueta?", "manutencao", "analise_tecnica", 10, ("preco", "gas")),
    faq("Vocês fazem manutenção preventiva residencial?", "Fazemos sim. A preventiva ajuda a evitar mau cheiro, vazamento e perda de rendimento. Quantos aparelhos você tem e em qual cidade fica?", "manutencao", "analise_tecnica", 15, ("preventiva",)),
    faq("A análise técnica tem custo?", "A análise técnica no local custa R$50 e esse valor abate se você aprovar o orçamento. Só high-wall simples e higienização high-wall têm preço fechado por WhatsApp. Qual é o serviço?", "manutencao", "analise_tecnica", 20, ("visita",)),
    faq("A placa do meu ar queimou?", "Pode ser placa, mas precisa testar antes de condenar peça. Me manda foto do painel e conta se teve queda de energia recente?", "manutencao", "analise_tecnica", 10, ("placa",)),
    faq("Será que é compressor?", "Pode ser, mas compressor só dá pra confirmar com teste técnico. Me fala marca, BTU e o que acontece quando tenta ligar?", "manutencao", "analise_tecnica", 10, ("compressor",)),
    faq("Depois da queda de energia o ar parou.", "Pode ter afetado placa, capacitor ou proteção elétrica. Me manda uma foto do aparelho e diz se ele acende alguma luz?", "manutencao", "analise_tecnica", 10, ("energia",)),
    faq("O ar está fraco.", "Ar fraco pode ser filtro sujo, evaporadora carregada ou falta de manutenção. Quando foi a última limpeza completa?", "manutencao", "analise_tecnica", 15, ("fluxo",)),
    faq("Qual a diferença entre manutenção e higienização?", "Higienização é limpeza profunda. Manutenção é diagnóstico e correção de falha. O seu ar está sujo, com cheiro, sem gelar ou com algum defeito?", "manutencao", "analise_tecnica", 10, ("triagem",)),

    # Higienização
    faq("Quanto custa para higienizar um split?", "Higienização de split high-wall fica R$200 por aparelho. Cassete, duto, splitão ou acesso difícil precisa análise de R$50 abatível. Quantos high-wall são?", "higienizacao", "higienizacao_preventiva", 5, ("preco",)),
    faq("O que inclui a higienização?", "No split high-wall, inclui limpeza profunda da evaporadora, filtros e partes internas acessíveis, com produto bacteriostático. Quantos aparelhos high-wall são?", "higienizacao", "higienizacao_preventiva", 10, ("incluso",)),
    faq("Limpar filtro resolve?", "Limpar filtro ajuda, mas não substitui higienização profunda. Se tem cheiro, alergia ou queda de rendimento, o ideal é higienizar. Quantos aparelhos são?", "higienizacao", "higienizacao_preventiva", 15, ("filtro",)),
    faq("Meu ar está com cheiro de mofo.", "Cheiro de mofo geralmente vem de sujeira e micro-organismos na evaporadora. A higienização resolve a causa na maioria dos casos. Qual a cidade e quantos aparelhos são?", "higienizacao", "higienizacao_preventiva", 5, ("mofo",)),
    faq("Tenho criança em casa. Precisa higienizar?", "É recomendado manter a higienização em dia, principalmente com criança, alergia ou rinite em casa. Me fala há quanto tempo o aparelho não passa por limpeza profunda?", "higienizacao", "higienizacao_preventiva", 10, ("saude",)),
    faq("De quanto em quanto tempo higienizar em casa?", "Para uso residencial, a referência prática é a cada 6 meses. Se tem alergia, mofo ou uso intenso, pode ser antes. Quantos aparelhos você tem?", "higienizacao", "higienizacao_preventiva", 15, ("frequencia",)),
    faq("E em loja ou escritório?", "Em loja e escritório, normalmente a higienização precisa ser mais frequente, muitas vezes a cada 3 meses. Quantos aparelhos ficam no local?", "higienizacao", "higienizacao_preventiva", 15, ("comercial",)),
    faq("Vocês fazem ozônio?", "Quando indicado, a gente pode usar sanitização complementar. Depois precisa ventilar o ambiente antes de usar normalmente. Qual o sintoma: cheiro, mofo ou alergia?", "higienizacao", "higienizacao_preventiva", 20, ("ozonio",)),
    faq("Emitem certificado de higienização?", "Emitimos registro do serviço quando necessário para empresa, auditoria ou controle interno. Me fala se é residencial ou comercial?", "higienizacao", "higienizacao_preventiva", 20, ("certificado",)),
    faq("Tenho vários aparelhos para limpar.", "Perfeito. Se forem split high-wall, fica R$200 por aparelho. Se tiver cassete, duto ou acesso difícil, precisa análise de R$50 abatível. Quantos e quais tipos são?", "higienizacao", "higienizacao_preventiva", 10, ("volume",)),
    faq("Quanto tempo demora a higienização?", "Split high-wall costuma ser mais direto; o tempo depende da quantidade. Cassete, duto ou acesso difícil precisa análise de R$50 abatível. Quantos high-wall são?", "higienizacao", "higienizacao_preventiva", 20, ("prazo",)),
    faq("Precisa desmontar o ar?", "A gente desmonta o que for necessário e seguro para fazer a limpeza correta. Me manda a marca e uma foto do aparelho?", "higienizacao", "higienizacao_preventiva", 20, ("procedimento",)),
    faq("Vocês limpam cassete também?", "Limpamos sim, mas o procedimento muda conforme acesso e modelo. Me manda foto do cassete e a cidade do atendimento?", "higienizacao", "higienizacao_preventiva", 20, ("cassete",)),
    faq("Depois da higienização já pode ligar?", "Depois da finalização e ventilação correta, pode usar normalmente. Me fala quantos aparelhos você quer agendar?", "higienizacao", "higienizacao_preventiva", 20, ("pos-servico",)),

    # PMOC
    faq("O que é PMOC?", "PMOC é o programa de manutenção preventiva e operação dos sistemas de climatização. Ele organiza rotinas, registros e responsabilidade técnica. Seu caso é empresa, clínica, loja ou condomínio?", "pmoc", "analise_tecnica", 5, ("pmoc",)),
    faq("Quando o PMOC é obrigatório?", "Em geral, é obrigatório para sistemas de climatização acima de 60.000 BTU em estabelecimentos coletivos ou comerciais. Quantos aparelhos vocês têm hoje?", "pmoc", "analise_tecnica", 5, ("obrigatorio",)),
    faq("Minha loja precisa de PMOC?", "Pode precisar, principalmente se a soma dos equipamentos for alta ou houver exigência de fiscalização. Me passa quantidade de aparelhos, BTU e cidade?", "pmoc", "analise_tecnica", 10, ("loja",)),
    faq("Clínica ou restaurante precisa de atenção especial?", "Sim. Clínica, restaurante e ambiente com público recorrente precisam de controle mais cuidadoso de manutenção e higiene. Quantos equipamentos ficam no local?", "pmoc", "analise_tecnica", 10, ("alto-risco",)),
    faq("Vocês fazem ART?", "Para PMOC e projetos, a proposta pode incluir ART do responsável técnico quando aplicável. Me passa o tipo de estabelecimento e a quantidade de aparelhos?", "pmoc", "analise_tecnica", 10, ("art",)),
    faq("Preciso de PMOC para alvará.", "A gente pode ajudar com levantamento, documentação e rotina técnica. Me manda cidade, tipo de estabelecimento e quantidade de equipamentos?", "pmoc", "analise_tecnica", 5, ("alvara",)),
    faq("Tenho vários aparelhos, como levantar?", "O ideal é montar uma lista com tipo, marca, BTU e localização de cada aparelho. Você prefere mandar essa lista ou agendar um levantamento técnico no local?", "pmoc", "analise_tecnica", 10, ("levantamento",)),
    faq("Como é a primeira visita do PMOC?", "A primeira etapa é levantar equipamentos, estado geral, riscos e rotina necessária. Depois a gente monta a proposta e o cronograma. Qual o endereço do local?", "pmoc", "analise_tecnica", 10, ("visita",)),
    faq("Quanto custa PMOC?", "PMOC não tem preço fechado por WhatsApp. Precisa levantamento técnico, e a análise custa R$50 abatível se aprovar a proposta. Quantos aparelhos e qual tipo de estabelecimento?", "pmoc", "analise_tecnica", 5, ("preco",)),
    faq("PMOC é mensal ou trimestral?", "Depende do risco, uso e exigência do local. A gente define a periodicidade no cronograma técnico. Qual é o tipo de estabelecimento?", "pmoc", "analise_tecnica", 15, ("periodicidade",)),
    faq("O PMOC inclui limpeza dos filtros?", "O plano pode incluir limpeza, inspeção, registros, higienização programada e verificações técnicas. Me fala quantos aparelhos são?", "pmoc", "analise_tecnica", 15, ("escopo",)),
    faq("E se tiver fiscalização?", "Com PMOC organizado, você tem registros, cronograma e documentação para apresentar. Me fala se já recebeu alguma exigência ou notificação?", "pmoc", "analise_tecnica", 10, ("fiscalizacao",)),
    faq("Vocês atendem condomínio?", "Atendemos sim. Para condomínio, preciso saber quantidade de aparelhos, áreas atendidas e se existe sistema central. Me passa esses dados?", "pmoc", "analise_tecnica", 15, ("condominio",)),
    faq("Tenho 12 aparelhos na empresa.", "Com 12 aparelhos, vale montar um plano preventivo com cronograma e documentação. Me passa cidade, tipo de negócio e lista dos equipamentos?", "pmoc", "analise_tecnica", 5, ("lead-quente",)),

    # Consultoria e dimensionamento
    faq("Quantos BTUs preciso para minha sala?", "Pra calcular certo, preciso da metragem, sol da tarde, quantidade de pessoas e eletrônicos no ambiente. Me passa esses dados?", "consultoria", "reuniao_projeto", 10, ("dimensionamento",)),
    faq("Qual ar colocar no quarto?", "Depende da metragem, insolação e uso. Me fala o tamanho do quarto e se bate sol forte à tarde?", "consultoria", "reuniao_projeto", 15, ("quarto",)),
    faq("Tenho uma loja de 40 metros.", "Para loja, além da metragem, entram porta aberta, circulação de pessoas, vitrine e equipamentos. Me descreve o layout ou manda a planta?", "consultoria", "reuniao_projeto", 10, ("loja",)),
    faq("Split ou cassete?", "Split costuma ser mais simples e econômico. Cassete distribui melhor em teto rebaixado e ambiente comercial. O local tem forro de gesso?", "consultoria", "reuniao_projeto", 15, ("cassete",)),
    faq("Vale a pena comprar inverter?", "Na maioria dos usos, inverter ajuda no conforto e no consumo, principalmente com uso diário. Me fala quantas horas por dia o ar fica ligado?", "consultoria", "reuniao_projeto", 20, ("inverter",)),
    faq("Meu prédio é 110 ou 220, isso importa?", "Importa sim. O ar precisa ser compatível com a elétrica do local e ter circuito adequado. Você já tem ponto pronto para ar-condicionado?", "consultoria", "reuniao_projeto", 20, ("eletrica",)),
    faq("Estou em obra, quando devo chamar vocês?", "O ideal é antes de fechar parede e forro. Assim a gente planeja tubulação, dreno e elétrica sem retrabalho. Você tem planta baixa?", "consultoria", "reuniao_projeto", 10, ("obra",)),
    faq("Tenho planta do apartamento.", "Perfeito. Me manda a planta e marca onde quer climatizar para eu avaliar evaporadora, condensadora, dreno e capacidade?", "consultoria", "reuniao_projeto", 10, ("planta",)),
    faq("Quero economizar energia.", "O caminho é dimensionar certo, escolher equipamento eficiente e manter limpeza em dia. Me fala o ambiente, metragem e rotina de uso?", "consultoria", "reuniao_projeto", 20, ("energia",)),
    faq("Não sei qual aparelho comprar.", "A gente te orienta sem empurrar modelo caro à toa. Me passa metragem, cidade, sol do ambiente e quantas pessoas usam o espaço?", "consultoria", "reuniao_projeto", 10, ("compra",)),

    # Projeto central
    faq("Preciso de VRF ou multisplit.", "Dá pra avaliar. VRF/VRV, multisplit e projeto de dutos precisam levantamento técnico, não preço por chute. Me passa planta, metragem e quantidade de ambientes?", "projeto-central", "reuniao_projeto", 10, ("vrf",)),
    faq("Tenho escritório com vários ambientes.", "Para escritório, a gente separa por zonas, uso e horários. Me manda planta ou lista dos ambientes para marcar uma reunião técnica?", "projeto-central", "reuniao_projeto", 10, ("escritorio",)),
    faq("Restaurante precisa de projeto diferente?", "Precisa sim. Cozinha, salão e exaustão devem ser tratados separadamente. Me passa planta ou fotos do local?", "projeto-central", "reuniao_projeto", 10, ("restaurante",)),
    faq("Galpão industrial precisa de climatização.", "Galpão exige cálculo de carga térmica, pé-direito, telhado, máquinas e ocupação. Me passa metragem e atividade do galpão?", "projeto-central", "reuniao_projeto", 10, ("galpao",)),
    faq("Tenho sala de servidor ou TI.", "Sala de TI precisa olhar carga térmica, redundância e funcionamento contínuo. Me passa tamanho da sala e equipamentos principais?", "projeto-central", "reuniao_projeto", 10, ("ti",)),
    faq("Hotel ou pousada precisa climatizar vários quartos.", "Nesse caso a gente avalia padrão por quarto, áreas comuns, manutenção e consumo. Quantos quartos e quais áreas precisam de ar?", "projeto-central", "reuniao_projeto", 15, ("hotel",)),
    faq("Quero trocar um sistema antigo.", "A gente faz retrofit avaliando o que dá para aproveitar e o que precisa trocar. Me manda fotos da casa de máquinas, evaporadoras e condensadoras?", "projeto-central", "reuniao_projeto", 15, ("retrofit",)),
    faq("Quanto tempo leva um projeto?", "Depende da planta, tamanho e complexidade. Primeiro fazemos reunião técnica e levantamento. Você já tem planta ou só fotos do local?", "projeto-central", "reuniao_projeto", 20, ("prazo",)),

    # Objeções, fechamento e pós-serviço
    faq("Achei caro.", "Entendo. Em ar-condicionado, preço baixo demais costuma cortar etapa importante, como vácuo, dreno, suporte e teste. Me manda o modelo e o local para eu confirmar o orçamento justo?", None, "duvida", 10, ("objecao",)),
    faq("Vi alguém fazendo instalação por R$400.", "Entendo a comparação. A gente não ataca concorrente, mas instalação mal feita pode virar vazamento, ruído e perda de garantia. Me manda foto do local para eu te explicar o que entra no serviço?", "instalacao", "analise_tecnica", 5, ("objecao",)),
    faq("Consegue desconto?", "Consigo avaliar condição quando tenho quantidade, cidade e tipo de serviço. Me passa esses dados para eu ver o melhor formato possível?", None, "duvida", 15, ("negociacao",)),
    faq("Quais formas de pagamento?", "A condição depende do serviço e do orçamento final. Me passa primeiro o tipo de serviço, cidade e quantidade de aparelhos?", None, "duvida", 20, ("pagamento",)),
    faq("Quero agendar visita.", "Perfeito. A análise técnica custa R$50 e abate se aprovar o orçamento. Me passa nome, cidade, bairro, melhor período e o serviço que você precisa?", None, "analise_tecnica", 5, ("agenda",)),
    faq("Fiz serviço e deu problema.", "Sinto muito por isso. Me manda nome, endereço do atendimento, data aproximada e foto ou vídeo do problema para eu verificar o caso?", None, "analise_tecnica", 5, ("pos-venda",)),
]


if len(TOP100_FAQ) != 100:
    raise RuntimeError(f"TOP100_FAQ deve ter 100 itens; atual={len(TOP100_FAQ)}")

for item in TOP100_FAQ:
    service = item["service_name"]
    if service not in VALID_SERVICES:
        raise RuntimeError(f"service_name inválido em FAQ: {service!r}")
