#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compilador mestre de documentos — Refrimix Tecnologia (Padrão 05/2026)
Gera Propostas, Contratos, Ordens de Serviço e Orçamentos com identidade visual ultra-premium.
"""

import os
import sys
import json
import argparse
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfgen import canvas

# Cores oficiais da Refrimix (Slate Dark Mode Premium 05/2026)
COLOR_PRIMARY_NAVY = colors.HexColor("#0A0E17")      # Deep Slate Dark Mode background
COLOR_LOGO_NAVY = colors.HexColor("#0A0E17")         # Matching dark slate
COLOR_STEEL_BLUE = colors.HexColor("#00E5FF")        # Bright Neon Cyan
COLOR_CREAM = colors.HexColor("#0A0E17")             # Cream is now Dark slate
COLOR_GOLD = colors.HexColor("#00E5FF")              # Gold replaced by vibrant Neon Cyan
COLOR_SECONDARY_STEEL = colors.HexColor("#94A3B8")   # Slate-400 light grey text
COLOR_WHITE = colors.HexColor("#FFFFFF")
COLOR_LIGHT_BG = colors.HexColor("#1E293B")          # Deep Slate grid background stripe
COLOR_GRID_GREY = colors.HexColor("#00E5FF")         # Cyan grid lines
COLOR_GREEN = colors.HexColor("#00E5FF")             # In-scope cyan
COLOR_RED = colors.HexColor("#FF3366")               # Neon red/pink

LOGO_PATH = "/home/will/whatsapp-rag/app/services/refrimix_data/logo_white.png"

class NumberedCanvas(canvas.Canvas):
    """
    Canvas customizado para desenhar cabeçalhos e rodapés institucionais
    da Refrimix Tecnologia com numeração de página precisa.
    """
    def __init__(self, *args, skip_first_standard_decorations=False, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []
        self._skip_first_standard_decorations = skip_first_standard_decorations

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        # A capa da proposta usa layout editorial próprio; demais documentos recebem decoração desde a página 1.
        if self._skip_first_standard_decorations and self._pageNumber == 1 and page_count > 2:
            return

        self.saveState()
        
        # ── CABEÇALHO ──────────────────────────────────────────────────────────
        # Detalhe ciano no topo
        self.setFillColor(COLOR_GOLD)
        self.rect(0, A4[1] - 4*mm, A4[0], 4*mm, fill=True, stroke=False)
        
        # Textos do cabeçalho
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(COLOR_WHITE)
        self.drawString(18*mm, A4[1] - 12*mm, "REFRIMIX TECNOLOGIA  |  ENGENHARIA HVAC-R")
        self.drawRightString(A4[0] - 18*mm, A4[1] - 12*mm, "CNPJ: 37.308.021/0001-89  •  @willrefrimix")
        
        # Linha fina ciano abaixo do texto
        self.setStrokeColor(COLOR_GOLD)
        self.setLineWidth(1)
        self.line(18*mm, A4[1] - 15*mm, A4[0] - 18*mm, A4[1] - 15*mm)
        
        # ── RODAPÉ ─────────────────────────────────────────────────────────────
        # Linha fina ciano acima do rodapé
        self.setStrokeColor(COLOR_GOLD)
        self.setLineWidth(1)
        self.line(18*mm, 15*mm, A4[0] - 18*mm, 15*mm)
        
        # Textos do rodapé
        self.setFont("Helvetica", 8)
        self.setFillColor(COLOR_SECONDARY_STEEL)
        self.drawString(18*mm, 8*mm, "Refrimix Tecnologia  |  Climatização • Engenharia HVAC-R  |  Guarujá — SP")
        self.drawRightString(A4[0] - 18*mm, 8*mm, f"Pág. {self._pageNumber} de {page_count}")
        
        self.restoreState()


def draw_cover_background(canvas, doc):
    """Desenha o fundo blueprint e a faixa ciano lateral na capa (primeiro pass)."""
    canvas.saveState()
    # 1. Fill background with dark blueprint blue
    canvas.setFillColor(COLOR_PRIMARY_NAVY)
    canvas.rect(0, 0, A4[0], A4[1], fill=True, stroke=False)
    
    # 2. Draw blueprint grid lines
    canvas.setStrokeColor(colors.HexColor("#1A2436"))
    canvas.setLineWidth(0.5)
    grid_size = 15*mm
    for x in range(0, int(A4[0]), int(grid_size)):
        canvas.line(x, 0, x, A4[1])
    for y in range(0, int(A4[1]), int(grid_size)):
        canvas.line(0, y, A4[0], y)
        
    # 3. Draw neon cyan left vertical border stripe
    canvas.setFillColor(COLOR_GOLD)
    canvas.rect(0, 0, 10*mm, A4[1], fill=True, stroke=False)
    canvas.restoreState()


def draw_later_background(canvas, doc):
    """Desenha o fundo blueprint e a faixa ciano lateral nas páginas internas (primeiro pass)."""
    canvas.saveState()
    # 1. Fill background with dark blueprint blue
    canvas.setFillColor(COLOR_PRIMARY_NAVY)
    canvas.rect(0, 0, A4[0], A4[1], fill=True, stroke=False)
    
    # 2. Draw blueprint grid lines
    canvas.setStrokeColor(colors.HexColor("#1A2436"))
    canvas.setLineWidth(0.5)
    grid_size = 15*mm
    for x in range(0, int(A4[0]), int(grid_size)):
        canvas.line(x, 0, x, A4[1])
    for y in range(0, int(A4[1]), int(grid_size)):
        canvas.line(0, y, A4[0], y)
        
    # 3. Draw neon cyan left vertical border stripe
    canvas.setFillColor(COLOR_GOLD)
    canvas.rect(0, 0, 8*mm, A4[1], fill=True, stroke=False)
    canvas.restoreState()


def format_currency(val):
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def create_branded_header(title, subtitle_html, style_title, style_body):
    header_table_data = []
    col_widths = [174*mm]
    if os.path.exists(LOGO_PATH):
        # We have a logo, so we split columns
        logo_img = Image(LOGO_PATH, width=22*mm, height=22*mm, hAlign='LEFT')
        right_content = [
            Paragraph(title, style_title),
            Paragraph(subtitle_html, style_body)
        ]
        header_table_data = [[logo_img, right_content]]
        col_widths = [26*mm, 148*mm]
    else:
        # Fallback without logo
        content = [
            Paragraph(title, style_title),
            Paragraph(subtitle_html, style_body)
        ]
        header_table_data = [[content]]
        
    t_header = Table(header_table_data, colWidths=col_widths)
    t_header.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('PADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (0,0), 4*mm)
    ]))
    
    # Gold divider line
    line_table = Table([[""]], colWidths=[174*mm], rowHeights=[1])
    line_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), COLOR_GOLD),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
    ]))
    
    return KeepTogether([t_header, Spacer(1, 3*mm), line_table, Spacer(1, 5*mm)])


def build_master_document(config):
    pdf_path = config["output"]
    doc_type = config["tipo"]
    
    # O.S. rápida e orçamentos curtos têm margens de cabeçalho menores caso caibam em poucas páginas
    top_margin = 35*mm if doc_type not in ["os", "orcamento_material", "orcamento_mao_de_obra"] else 25*mm
    bottom_margin = 28*mm if doc_type not in ["os"] else 20*mm
    
    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        leftMargin=18*mm,
        rightMargin=18*mm,
        topMargin=top_margin,
        bottomMargin=bottom_margin,
        title=f"{doc_type.replace('_', ' ').title()} - Refrimix Tecnologia - {config['cliente']}",
        author="Refrimix Tecnologia"
    )
    
    styles = getSampleStyleSheet()
    
    # Customização de estilos
    style_cover_title = ParagraphStyle(
        "CoverTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=28,
        leading=34,
        textColor=COLOR_WHITE,
        spaceAfter=15
    )
    
    style_header_title = ParagraphStyle(
        "HeaderTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=19,
        textColor=COLOR_WHITE,
        spaceAfter=4
    )
    
    style_cover_subtitle = ParagraphStyle(
        "CoverSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=13,
        leading=17,
        textColor=COLOR_GOLD, # Vibrant Cyan
        spaceAfter=30
    )
    
    style_h1 = ParagraphStyle(
        "RFXH1",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=19,
        textColor=COLOR_GOLD, # Vibrant Cyan
        spaceBefore=14,
        spaceAfter=8,
        keepWithNext=True
    )

    style_h2 = ParagraphStyle(
        "RFXH2",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=15,
        textColor=COLOR_WHITE,
        spaceBefore=8,
        spaceAfter=4,
        keepWithNext=True
    )
    
    style_body = ParagraphStyle(
        "RFXBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13.5,
        textColor=colors.HexColor("#E2E8F0"), # Light grey
        spaceAfter=6,
        alignment=TA_JUSTIFY
    )

    style_body_bold = ParagraphStyle(
        "RFXBodyBold",
        parent=style_body,
        fontName="Helvetica-Bold",
        textColor=COLOR_WHITE
    )

    style_clause = ParagraphStyle(
        "RFXClause",
        parent=style_body,
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#CBD5E1"),
        spaceAfter=4,
        alignment=TA_JUSTIFY
    )

    style_table_text = ParagraphStyle(
        "RFXTableText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#E2E8F0")
    )

    style_table_text_bold = ParagraphStyle(
        "RFXTableTextBold",
        parent=style_table_text,
        fontName="Helvetica-Bold",
        textColor=COLOR_WHITE
    )

    style_table_header = ParagraphStyle(
        "RFXTableHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        textColor=COLOR_WHITE
    )

    def premium_table(rows, col_widths, header_rows=1, highlight_last=False):
        table = Table(rows, colWidths=col_widths, repeatRows=header_rows)
        style = [
            ('BACKGROUND', (0,0), (-1,header_rows-1), COLOR_PRIMARY_NAVY),
            ('GRID', (0,0), (-1,-1), 0.45, COLOR_GRID_GREY),
            ('PADDING', (0,0), (-1,-1), 6),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('ROWBACKGROUNDS', (0,header_rows), (-1,-1), [COLOR_PRIMARY_NAVY, COLOR_LIGHT_BG]),
        ]
        if highlight_last:
            style.append(('BACKGROUND', (0, len(rows)-1), (-1, len(rows)-1), COLOR_PRIMARY_NAVY))
        table.setStyle(TableStyle(style))
        return table
    
    story = []
    
    # ─────────────────────────────────────────────────────────────────────────
    # DOCUMENT TIER ROUTER
    # ─────────────────────────────────────────────────────────────────────────
    
    if doc_type == "proposta":
        # ── 1. PROPOSTA TÉCNICA DETALHADA (11 Páginas) ────────────────────────
        # Capa
        story.append(Spacer(1, 8*mm))
        if os.path.exists(LOGO_PATH):
            story.append(Image(LOGO_PATH, width=42*mm, height=42*mm, hAlign='LEFT'))
        story.append(Spacer(1, 10*mm))
        story.append(Paragraph("PROPOSTA TÉCNICA EXECUTIVA", style_cover_title))
        story.append(Paragraph("Engenharia de Climatização & Sistemas HVAC-R Premium", style_cover_subtitle))
        story.append(Spacer(1, 5*mm))
        
        info_data = [
            [Paragraph("<b>CLIENTE:</b>", style_body), Paragraph(config["cliente"], style_body_bold)],
            [Paragraph("<b>CNPJ/CPF:</b>", style_body), Paragraph(config.get("cnpj_cliente", "Não Informado"), style_body)],
            [Paragraph("<b>DATA:</b>", style_body), Paragraph(config["data"], style_body)],
            [Paragraph("<b>VALIDADE:</b>", style_body), Paragraph(config["validade_proposta"], style_body)],
            [Paragraph("<b>GARANTIA:</b>", style_body), Paragraph(config["garantia_instalacao"], style_body)],
        ]
        t_info = Table(info_data, colWidths=[30*mm, 120*mm])
        t_info.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('BOTTOMPADDING', (0,0), (-1,-1), 4)]))
        story.append(t_info)
        story.append(Spacer(1, 12*mm))
        story.append(Paragraph("<b>REFRIMIX TECNOLOGIA LTDA</b><br/>Guarujá — SP | CNPJ 37.308.021/0001-89 | @willrefrimix", style_body))
        story.append(PageBreak())
        
        # Página 2: Apresentação
        story.append(Paragraph("1. Apresentação Institucional", style_h1))
        story.append(Paragraph(
            "A <b>Refrimix Tecnologia</b> é uma empresa especializada em engenharia de climatização e sistemas HVAC-R "
            "de alta performance na Baixada Santista e estado de São Paulo. Nosso compromisso é aliar conforto térmico extraordinário, "
            "acabamento estético impecável e durabilidade mecânica extrema em ambientes litorâneos.",
            style_body
        ))
        story.append(Spacer(1, 5*mm))
        story.append(Paragraph("<b>Diferenciais Tecnológicos:</b>", style_h2))
        story.append(Paragraph("• Dimensionamento térmico de precisão baseado em normas ABNT e ASHRAE.<br/>"
                               "• Equipe técnica especializada SRE, engenheiros mecânicos habilitados CREA.<br/>"
                               "• Credenciamento Premium Daikin para instalação e manutenção.", style_body))
        story.append(PageBreak())
        
        # Página 3: Engenharia Litorânea
        story.append(Paragraph("2. Engenharia Anti-Corrosão Litorânea", style_h1))
        story.append(Paragraph(
            "Para suportar a maresia rigorosa do litoral paulista, aplicamos o padrão de engenharia mais resistente do mercado:",
            style_body
        ))
        story.append(Paragraph(
            "<b>A. Proteção de Aletas:</b> Aplicação de selante e verniz naval nas serpentinas de alumínio.<br/>"
            "<b>B. Suportes Especiais:</b> Utilização exclusiva de suportes de aço inox 304 ou resina estrutural antivibração.<br/>"
            "<b>C. Brasagem sob Nitrogênio:</b> Previne a oxidação e formação de fuligem interna nos tubos de cobre durante a brasagem.",
            style_body
        ))
        story.append(PageBreak())
        
        # Página 4: Objetivo & Equipamentos
        story.append(Paragraph("3. Objetivo do Projeto & Fornecimento Daikin", style_h1))
        eq_rows = [[Paragraph("<b>Modelo / Equipamento</b>", style_table_header), 
                    Paragraph("<b>BTU</b>", style_table_header), 
                    Paragraph("<b>Qtd</b>", style_table_header), 
                    Paragraph("<b>Tecnologia</b>", style_table_header)]]
        for eq in config["equipamentos"]:
            eq_rows.append([
                Paragraph(eq["modelo"], style_table_text_bold),
                Paragraph(eq["btu"], style_table_text),
                Paragraph(str(eq["qtd"]), style_table_text),
                Paragraph(eq["tecnologia"], style_table_text)
            ])
        t_eq = Table(eq_rows, colWidths=[70*mm, 30*mm, 20*mm, 54*mm])
        t_eq.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), COLOR_PRIMARY_NAVY),
            ('GRID', (0,0), (-1,-1), 0.5, COLOR_GRID_GREY),
            ('PADDING', (0,0), (-1,-1), 6),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [COLOR_PRIMARY_NAVY, COLOR_LIGHT_BG])
        ]))
        story.append(t_eq)
        story.append(PageBreak())
        
        # Página 5: Metodologia e Dutos
        story.append(Paragraph("4. Distribuição de Ar e Acústica Térmica", style_h1))
        story.append(Paragraph(
            "Nosso sistema de dutos é projetado com isolamento duplo elastomérico ou painéis MPU premium, garantindo ruído zero e "
            "evitando qualquer choque térmico ou gotejamento no gesso decorativo.",
            style_body
        ))
        story.append(PageBreak())
        
        # Página 6: Comissionamento
        story.append(Paragraph("5. Comissionamento SRE e Teste de Estanqueidade", style_h1))
        story.append(Paragraph(
            "Nossos técnicos realizam testes de estanqueidade a 550 PSI com nitrogênio por 24h e evacuação "
            "completa de umidade monitorada por vacuômetro digital até estabilizar abaixo de 500 microns.",
            style_body
        ))
        story.append(PageBreak())
        
        # Página 7: Responsabilidade Técnica
        story.append(Paragraph("6. Responsabilidade Técnica & PMOC", style_h1))
        story.append(Paragraph(
            "Todos os projetos contam com emissão de ART do CREA e elaboração do livro do PMOC, atestando a qualidade do ar "
            "e a integridade estrutural das instalações mecânicas.",
            style_body
        ))
        story.append(PageBreak())
        
        # Página 8: Seção 13 — Investimento
        story.append(Paragraph("7. Seção 13 — Investimento Comercial", style_h1))
        
        v_gestao = config["gestao_valor"]
        v_materiais = config["materiais_valor"]
        v_dutos = config["dutos_valor"]
        total_extras = sum(item["valor"] for item in config["dutos_extras"])
        total_exec = v_gestao + v_materiais + v_dutos + total_extras
        v_equip = sum(eq.get("valor", 0) for eq in config["equipamentos"])
        total_geral = total_exec + v_equip
        
        inv_rows = [
            [Paragraph("<b>Serviço / Fornecimento Executivo</b>", style_table_header), Paragraph("<b>Valor</b>", style_table_header)],
            [Paragraph("Gestão Técnica, Planejamento e Engenharia SRE", style_table_text), Paragraph(format_currency(v_gestao), style_table_text_bold)],
            [Paragraph("Materiais e Insumos Especiais com Proteção Naval", style_table_text), Paragraph(format_currency(v_materiais), style_table_text_bold)],
            [Paragraph("Sistema de Dutos, Dampers e Balanceamento Acústico", style_table_text), Paragraph(format_currency(v_dutos), style_table_text_bold)],
        ]
        for item in config["dutos_extras"]:
            inv_rows.append([
                Paragraph(f"<font color='#2e7d32'>➕ <b>{item['desc']}</b></font>", style_table_text),
                Paragraph(f"<font color='#2e7d32'><b>{format_currency(item['valor'])}</b></font>", style_table_text_bold)
            ])
        inv_rows.append([Paragraph("<b>SUBTOTAL DE EXECUÇÃO E INSTALAÇÃO</b>", style_table_text_bold), Paragraph(format_currency(total_exec), style_table_text_bold)])
        inv_rows.append([Paragraph("Fornecimento de Equipamentos Daikin (Faturamento Direto)", style_table_text), Paragraph(format_currency(v_equip), style_table_text_bold)])
        inv_rows.append([Paragraph("<b>INVESTIMENTO TOTAL GERAL (Execução + Equipamentos)</b>", style_table_header), Paragraph(format_currency(total_geral), style_table_header)])
        
        t_inv = Table(inv_rows, colWidths=[120*mm, 54*mm])
        t_inv.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), COLOR_PRIMARY_NAVY),
            ('GRID', (0,0), (-1,-1), 0.5, COLOR_GRID_GREY),
            ('PADDING', (0,0), (-1,-1), 7),
            ('BACKGROUND', (0, len(inv_rows)-3), (-1, len(inv_rows)-3), COLOR_LIGHT_BG),
            ('BACKGROUND', (0, len(inv_rows)-1), (-1, len(inv_rows)-1), COLOR_PRIMARY_NAVY),
        ]))
        story.append(t_inv)
        story.append(PageBreak())
        
        # Página 9: Condições Comerciais
        story.append(Paragraph("8. Condições Comerciais e Aceite", style_h1))
        story.append(Paragraph(
            f"<b>Validade da Proposta:</b> {config['validade_proposta']}<br/>"
            f"<b>Garantia de Instalação:</b> {config['garantia_instalacao']}<br/>"
            "<b>Pagamento:</b> Faturamento de equipamentos em até 10x sem juros direto Daikin. Serviços de instalação: 40% de sinal e saldo em 4 parcelas quinzenais.",
            style_body
        ))
        story.append(Spacer(1, 15*mm))
        story.append(Table([
            [Paragraph("________________________________________<br/>REFRIMIX TECNOLOGIA LTDA", style_body),
             Paragraph("________________________________________<br/>ACEITE DO CLIENTE", style_body)]
        ], colWidths=[87*mm, 87*mm], style=[('ALIGN', (0,0), (-1,-1), 'CENTER')]))
        story.append(PageBreak())
        
        # Páginas 10 & 11: Checklist
        story.append(Paragraph("9. Checklist de Rigor Técnico e Contratação", style_h1))
        ch_headers = [Paragraph("<b>Item de Qualidade / Critério Refrimix</b>", style_table_header), Paragraph("<b>Garantido</b>", style_table_header)]
        checklist_items = [
            "Dimensionamento térmico por software oficial ASHRAE/ABNT.",
            "Utilização exclusiva de tubulação de cobre classe A sem costuras.",
            "Brasagem de cobre sob fluxo constante de nitrogênio ativo.",
            "Pressurização de segurança a 550 PSI por 24 horas consecutivas.",
            "Evacuação (vácuo) monitorada por vacuômetro digital abaixo de 500 microns.",
            "Tratamento de aletas com primer e verniz naval anticorrosão.",
            "Fixação com suportes de aço inox 304 ou resina de engenharia.",
            "Drenagem por gravidade com tubos rígidos soldáveis e isolamento térmico.",
            "Instalação de bombas de dreno silenciosas nos evaporadores (se necessário).",
            "Isolamento térmico de alta resistência elastomérica blindada.",
            "Balanceamento estático e dinâmico de vazão de ar em dutos.",
            "Uso de fixadores e parafusos de aço inox em todas as unidades externas.",
            "Quadros elétricos de potência dedicados com disjuntores adequados.",
            "Aterramento elétrico exclusivo de todas as unidades.",
            "Cabos de comando blindados contra interferência eletromagnética.",
            "Emissão de PMOC assinado por Engenheiro Mecânico credenciado no CREA.",
            "Emissão de ART (Anotação de Responsabilidade Técnica).",
            "Comissionamento com termo de aceitação técnica formal assinado.",
            "Instrução operacional prática de uso das unidades Daikin ao cliente.",
            "Garantia estendida de instalação da Refrimix por 12 meses.",
            "Garantia estendida Daikin de compressor de até 10 anos.",
            "Preservação estética total das fachadas do condomínio.",
            "Trabalho em altura com equipe certificada na norma NR-35.",
            "Segurança operacional elétrica com equipe certificada na norma NR-10.",
            "Descarte ecológico de resíduos e embalagens após o término.",
            "Utilização exclusiva de fluido refrigerante ecológico de nova geração R32.",
            "Ocultação técnica inteligente das linhas de comando elétrico.",
            "Verificação de vazão com anemômetro digital após conclusão.",
            "Entrega de manual de usuário unificado e termo de garantia.",
            "Visita técnica de acompanhamento pós-instalação de cortesia em 30 dias.",
            "Suporte telefônico de engenharia e atendimento prioritário.",
            "Plano de contingência mecânica ativo para condensadoras.",
            "Garantia de nível de ruído acústico de evaporadoras abaixo de 19 dB(A).",
            "Polimento estético e limpeza pós-obra em todos os ambientes afetados."
        ]
        
        # Pág 10
        t_ch1 = [ch_headers]
        for i in range(17):
            t_ch1.append([Paragraph(f"{i+1}. {checklist_items[i]}", style_table_text), Paragraph("<b>SIM [✔]</b>", ParagraphStyle("G1", parent=style_table_text_bold, textColor=COLOR_GREEN))])
        ch_table1 = Table(t_ch1, colWidths=[144*mm, 30*mm])
        ch_table1.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), COLOR_PRIMARY_NAVY), ('GRID', (0,0), (-1,-1), 0.5, COLOR_GRID_GREY),
            ('PADDING', (0,0), (-1,-1), 5), ('ROWBACKGROUNDS', (0,1), (-1,-1), [COLOR_PRIMARY_NAVY, COLOR_LIGHT_BG])
        ]))
        story.append(ch_table1)
        story.append(PageBreak())
        
        # Pág 11
        t_ch2 = [ch_headers]
        for i in range(17, 34):
            t_ch2.append([Paragraph(f"{i+1}. {checklist_items[i]}", style_table_text), Paragraph("<b>SIM [✔]</b>", ParagraphStyle("G2", parent=style_table_text_bold, textColor=COLOR_GREEN))])
        ch_table2 = Table(t_ch2, colWidths=[144*mm, 30*mm])
        ch_table2.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), COLOR_PRIMARY_NAVY), ('GRID', (0,0), (-1,-1), 0.5, COLOR_GRID_GREY),
            ('PADDING', (0,0), (-1,-1), 5), ('ROWBACKGROUNDS', (0,1), (-1,-1), [COLOR_PRIMARY_NAVY, COLOR_LIGHT_BG])
        ]))
        story.append(ch_table2)
        story.append(PageBreak())

        # Página 12: Fechamento institucional
        story.append(Spacer(1, 18*mm))
        if os.path.exists(LOGO_PATH):
            story.append(Image(LOGO_PATH, width=34*mm, height=34*mm, hAlign='CENTER'))
            story.append(Spacer(1, 8*mm))
        story.append(Paragraph("10. Fechamento Executivo", style_h1))
        story.append(Paragraph(
            "A Refrimix Tecnologia entrega esta proposta como um documento de decisao tecnica: escopo, metodologia, "
            "equipamentos, garantias, investimento e criterios de contratacao estao consolidados para reduzir risco, "
            "evitar retrabalho e sustentar uma instalacao HVAC-R duravel em ambiente litoraneo.",
            style_body
        ))
        story.append(Spacer(1, 6*mm))
        story.append(Paragraph(
            "<b>Proximo passo recomendado:</b> validacao comercial, assinatura do aceite, programacao de mobilizacao "
            "e confirmacao das frentes de obra para inicio seguro da execucao.",
            style_body_bold
        ))
        story.append(Spacer(1, 14*mm))
        story.append(Paragraph("<b>REFRIMIX TECNOLOGIA LTDA</b><br/>Climatizacao • Engenharia HVAC-R<br/>Guaruja - Sao Paulo<br/>CNPJ: 37.308.021/0001-89<br/>Instagram tecnico: @willrefrimix", style_body))

    elif doc_type == "contrato":
        # ── 2. CONTRATO FORMAL DE INSTALAÇÃO E EXECUÇÃO ───────────────────────
        total_exec_contrato = (
            config["gestao_valor"] +
            config["materiais_valor"] +
            config["dutos_valor"] +
            sum(item["valor"] for item in config["dutos_extras"])
        )
        contrato_subtitle = (
            "<b>CONTRATANTE:</b> " + config["cliente"] + "<br/>"
            "<b>CONTRATADA:</b> REFRIMIX TECNOLOGIA LTDA  |  CNPJ: 37.308.021/0001-89  |  CREA-SP Ativo<br/>"
            "<b>OBJETO:</b> Instalação, engenharia, infraestrutura e comissionamento HVAC-R em ambiente litorâneo."
        )
        story.append(create_branded_header("CONTRATO DE INSTALAÇÃO E EXECUÇÃO", contrato_subtitle, style_header_title, style_body))

        story.append(Paragraph("QUADRO EXECUTIVO DO CONTRATO", style_h1))
        summary_rows = [
            [Paragraph("<b>Campo</b>", style_table_header), Paragraph("<b>Definição Contratual</b>", style_table_header)],
            [Paragraph("Contratante", style_table_text_bold), Paragraph(config["cliente"], style_table_text)],
            [Paragraph("Contratada", style_table_text_bold), Paragraph("REFRIMIX TECNOLOGIA LTDA - CNPJ 37.308.021/0001-89", style_table_text)],
            [Paragraph("Valor de execução", style_table_text_bold), Paragraph(format_currency(total_exec_contrato), style_table_text_bold)],
            [Paragraph("Prazo estimado", style_table_text_bold), Paragraph(config.get("obra_prazo", "15 dias úteis") + " após sinal, liberação de frente de obra e acesso técnico.", style_table_text)],
            [Paragraph("Garantia de instalação", style_table_text_bold), Paragraph(config["garantia_instalacao"] + " sobre mão de obra e materiais aplicados pela Refrimix.", style_table_text)],
            [Paragraph("Documentos vinculados", style_table_text_bold), Paragraph("Proposta técnica aprovada, memorial de execução, checklist de entrega, ART/CREA quando aplicável e ordens de serviço emitidas durante a obra.", style_table_text)],
        ]
        story.append(premium_table(summary_rows, [42*mm, 132*mm], highlight_last=False))
        story.append(Spacer(1, 5*mm))
        story.append(Paragraph(
            "Este contrato transforma a proposta técnica em obrigação executável: define escopo, valor, prazos, "
            "responsabilidades, critérios de aceite e documentação mínima para que a instalação seja entregue com "
            "rastreabilidade técnica, proteção anticorrosiva e padrão profissional compatível com operação em região litorânea.",
            style_body
        ))
        
        story.append(Paragraph("CLÁUSULAS ESSENCIAIS", style_h1))
        
        clauses = [
            ("CLÁUSULA PRIMEIRA - OBJETO E ESCOPO",
             "O objeto deste instrumento é a execução especializada de infraestrutura frigorígena, instalação, integração, testes e comissionamento de sistemas de climatização, conforme proposta técnica aprovada. O escopo inclui os serviços, materiais e premissas expressamente descritos nos documentos vinculados, excluídas intervenções civis, elétricas ou arquitetônicas não aprovadas por escrito."),
            ("CLÁUSULA SEGUNDA - EXECUÇÃO, NORMAS E RIGOR TÉCNICO",
             "A CONTRATADA executará os serviços observando boas práticas de engenharia HVAC-R, recomendações do fabricante, segurança operacional e critérios específicos para ambiente litorâneo. Quando aplicável, serão realizados pressurização com nitrogênio, vácuo técnico, verificação de estanqueidade, partida assistida, balanceamento e registro de entrega."),
            ("CLÁUSULA TERCEIRA - VALOR, PAGAMENTO E MOBILIZAÇÃO",
             f"O valor de execução contratado é de {format_currency(total_exec_contrato)}. A mobilização ocorre após assinatura, pagamento do sinal e liberação das frentes de serviço. Condições parceladas, medições ou retenções técnicas somente prevalecem quando registradas na proposta aprovada ou em aditivo assinado pelas partes."),
            ("CLÁUSULA QUARTA - PRAZO, DEPENDÊNCIAS E CRONOGRAMA",
             f"O prazo estimado de execução é de {config.get('obra_prazo', '15 dias úteis')}, contado a partir da liberação efetiva do local, disponibilidade dos equipamentos e ausência de impedimentos por terceiros. Interrupções por obra civil, condomínio, falta de energia, ausência de acesso ou mudança de escopo suspendem a contagem do prazo."),
            ("CLÁUSULA QUINTA - GARANTIA E LIMITES",
             f"A garantia de instalação é de {config['garantia_instalacao']} para mão de obra e materiais aplicados pela Refrimix. A garantia de equipamentos segue política, nota fiscal e condições do fabricante. Mau uso, falta de manutenção, intervenção de terceiros, energia fora de padrão, drenagem obstruída por obra externa ou ambiente agressivo sem manutenção preventiva não integram a garantia."),
        ]
        
        for title, text in clauses:
            story.append(Paragraph(f"<b>{title}</b>", style_h2))
            story.append(Paragraph(text, style_clause))
            story.append(Spacer(1, 2*mm))
        
        story.append(PageBreak())

        story.append(Paragraph("RESPONSABILIDADES E CRITÉRIOS DE ACEITE", style_h1))
        responsibility_rows = [
            [Paragraph("<b>Parte</b>", style_table_header), Paragraph("<b>Responsabilidades Principais</b>", style_table_header)],
            [Paragraph("Refrimix Tecnologia", style_table_text_bold), Paragraph("Executar o escopo aprovado, orientar tecnicamente a instalação, registrar etapas críticas, preservar organização de obra, informar impeditivos e entregar o sistema testado dentro das premissas contratadas.", style_table_text)],
            [Paragraph("Contratante", style_table_text_bold), Paragraph("Liberar acesso, energia, frentes de trabalho, aprovações condominiais, pontos civis/elétricos necessários, pagamentos nas datas acordadas e decisões de projeto em prazo compatível com o cronograma.", style_table_text)],
            [Paragraph("Terceiros e obra civil", style_table_text_bold), Paragraph("Atividades de alvenaria, gesso, pintura, marcenaria, elétrica predial, automação ou alterações arquitetônicas somente entram no escopo se constarem expressamente na proposta ou em aditivo.", style_table_text)],
        ]
        story.append(premium_table(responsibility_rows, [42*mm, 132*mm]))
        story.append(Spacer(1, 5*mm))

        acceptance_rows = [
            [Paragraph("<b>Marco de Aceite</b>", style_table_header), Paragraph("<b>Evidência Esperada</b>", style_table_header)],
            [Paragraph("Infraestrutura frigorígena", style_table_text_bold), Paragraph("Rotas organizadas, isolamento aplicado, fixação adequada e pontos preparados conforme premissas de obra.", style_table_text)],
            [Paragraph("Estanqueidade e vácuo", style_table_text_bold), Paragraph("Teste de pressão, verificação de vazamento e vácuo técnico compatível com boas práticas do fabricante.", style_table_text)],
            [Paragraph("Partida e comissionamento", style_table_text_bold), Paragraph("Equipamentos energizados, operação inicial validada, vazão/drenagem observadas e cliente orientado sobre uso básico.", style_table_text)],
            [Paragraph("Documentação", style_table_text_bold), Paragraph("Ordem de serviço, checklist de entrega, termos de garantia e ART/CREA quando contratada ou aplicável ao escopo.", style_table_text)],
        ]
        story.append(premium_table(acceptance_rows, [52*mm, 122*mm]))
        story.append(Spacer(1, 5*mm))

        additional_clauses = [
            ("CLÁUSULA SEXTA - ALTERAÇÕES DE ESCOPO E ADITIVOS",
             "Qualquer alteração de equipamento, rota, quantidade, prazo, material, acabamento, acesso ou condição de execução deverá ser aprovada por escrito. Serviços adicionais serão precificados antes da execução e poderão alterar prazo e valor total."),
            ("CLÁUSULA SÉTIMA - SEGURANÇA, ACESSO E CONDOMÍNIO",
             "A execução dependerá de regras de acesso, horários, elevadores, documentação e exigências do condomínio ou administração local. Exigências adicionais de segurança, integração, documentação ou equipe dedicada poderão gerar ajuste de prazo e custo."),
            ("CLÁUSULA OITAVA - PENALIDADES, INADIMPLEMENTO E SUSPENSÃO",
             "O atraso injustificado de pagamento acarretará multa de 2%, juros de 1% ao mês e poderá suspender mobilização, compra de materiais ou continuidade dos serviços. A suspensão por inadimplemento não caracteriza atraso da CONTRATADA."),
            ("CLÁUSULA NONA - ENTREGA, ACEITE E ENCERRAMENTO",
             "A entrega será formalizada mediante checklist, ordem de serviço ou assinatura de aceite. Pendências causadas por terceiros serão registradas separadamente e não impedem o aceite do escopo executado pela Refrimix quando este estiver tecnicamente concluído."),
            ("CLÁUSULA DÉCIMA - RESCISÃO E DOCUMENTOS VINCULADOS",
             "A rescisão poderá ocorrer por descumprimento contratual, impossibilidade técnica superveniente ou acordo entre as partes. Permanecem exigíveis valores de serviços executados, materiais adquiridos, mobilizações realizadas e custos comprovados até a data da rescisão."),
        ]
        for title, text in additional_clauses:
            story.append(Paragraph(f"<b>{title}</b>", style_h2))
            story.append(Paragraph(text, style_clause))
            story.append(Spacer(1, 1.5*mm))

        story.append(PageBreak())

        story.append(Paragraph("ENCERRAMENTO, ANEXOS E ASSINATURAS", style_h1))
        annex_rows = [
            [Paragraph("<b>Documento</b>", style_table_header), Paragraph("<b>Função no Contrato</b>", style_table_header)],
            [Paragraph("Proposta técnica aprovada", style_table_text_bold), Paragraph("Define escopo comercial, valores, equipamentos, condições e premissas aceitas pelo cliente.", style_table_text)],
            [Paragraph("Ordens de serviço", style_table_text_bold), Paragraph("Registram execução em campo, presença técnica, pendências, evidências e aceite operacional por etapa.", style_table_text)],
            [Paragraph("Checklist de entrega", style_table_text_bold), Paragraph("Comprova critérios mínimos de conclusão: estanqueidade, vácuo, partida, drenagem, acabamento e orientação ao cliente.", style_table_text)],
            [Paragraph("ART/CREA e documentos técnicos", style_table_text_bold), Paragraph("Formalizam responsabilidade técnica quando aplicável ou contratada, vinculando a execução ao padrão de engenharia.", style_table_text)],
        ]
        story.append(premium_table(annex_rows, [52*mm, 122*mm]))
        story.append(Spacer(1, 7*mm))
        story.append(Paragraph(
            "O aceite deste contrato confirma que as partes compreendem o escopo contratado, as dependências de obra, "
            "as condições de garantia e os documentos que serão usados para comprovar a entrega técnica.",
            style_body
        ))
        story.append(Spacer(1, 6*mm))
        story.append(Paragraph("Por estarem justos e acordados, as partes assinam o presente instrumento em duas vias de igual teor.", style_body))
        story.append(Spacer(1, 8*mm))
        
        sig_data = [
            [Paragraph("________________________________________<br/><b>REFRIMIX TECNOLOGIA LTDA</b><br/>CONTRATADA", style_body),
             Paragraph("________________________________________<br/><b>" + config["cliente"].upper() + "</b><br/>CONTRATANTE", style_body)]
        ]
        t_sig = Table(sig_data, colWidths=[87*mm, 87*mm])
        t_sig.setStyle(TableStyle([('ALIGN', (0,0), (-1,-1), 'CENTER'), ('PADDING', (0,0), (-1,-1), 8)]))
        story.append(t_sig)

    elif doc_type == "os":
        # ── 3. ORDEM DE SERVIÇO RÁPIDA (Layout O.S. de Campo) ────────────────
        os_subtitle = (
            "<b>Nº OS:</b> " + datetime.now().strftime("%Y%m%d") + "-01  |  "
            "<b>Data de Abertura:</b> " + config["data"] + "<br/>"
            "<b>Execução Técnica de Campo autorizada pela Refrimix.</b>"
        )
        story.append(create_branded_header("ORDEM DE SERVIÇO (O.S.)", os_subtitle, style_header_title, style_body))
        
        client_os_data = [
            [Paragraph("<b>Cliente:</b>", style_table_text_bold), Paragraph(config["cliente"], style_table_text),
             Paragraph("<b>Data:</b>", style_table_text_bold), Paragraph(config["data"], style_table_text)],
            [Paragraph("<b>Técnico:</b>", style_table_text_bold), Paragraph(config.get("tecnico_nome", "Equipe Refrimix"), style_table_text),
             Paragraph("<b>Veículo/Placa:</b>", style_table_text_bold), Paragraph(config.get("placa_veiculo", "LOG-1A80"), style_table_text)],
        ]
        t_cl_os = Table(client_os_data, colWidths=[20*mm, 70*mm, 30*mm, 54*mm])
        t_cl_os.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, COLOR_GRID_GREY),
            ('BACKGROUND', (0,0), (0,-1), COLOR_LIGHT_BG),
            ('BACKGROUND', (2,0), (2,-1), COLOR_LIGHT_BG),
            ('PADDING', (0,0), (-1,-1), 5),
        ]))
        story.append(t_cl_os)
        story.append(Spacer(1, 6*mm))
        
        story.append(Paragraph("ATIVIDADES E ESCOPO DA O.S.:", style_h1))
        story.append(Paragraph(
            "Execução técnica de infraestrutura frigorígena, teste de pressão com Nitrogênio a 550 PSI e balanceamento "
            "acústico de rede de dutos com dampers.",
            style_body
        ))
        
        story.append(Spacer(1, 4*mm))
        story.append(Paragraph("CHECKLIST OPERACIONAL DE CAMPO (Verificado pelo Técnico):", style_h2))
        
        os_ch_rows = [
            [Paragraph("<b>Procedimento Técnico Executado</b>", style_table_header), Paragraph("<b>Status</b>", style_table_header)],
            [Paragraph("Pressurização estanque com Nitrogênio ativo (550 PSI)", style_table_text), Paragraph("✔ OK / SIM", style_table_text_bold)],
            [Paragraph("Evacuação profunda de umidade com Vacuômetro (<500 microns)", style_table_text), Paragraph("✔ OK / SIM", style_table_text_bold)],
            [Paragraph("Aplicação de proteção naval anti-maresia nas aletas externas", style_table_text), Paragraph("✔ OK / SIM", style_table_text_bold)],
            [Paragraph("Fixação estrutural de suportes em inox 304 / resina", style_table_text), Paragraph("✔ OK / SIM", style_table_text_bold)],
            [Paragraph("Balanceamento de vazão de dutos via damper", style_table_text), Paragraph("✔ OK / SIM", style_table_text_bold)],
        ]
        t_os_ch = Table(os_ch_rows, colWidths=[134*mm, 40*mm])
        t_os_ch.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), COLOR_PRIMARY_NAVY),
            ('GRID', (0,0), (-1,-1), 0.5, COLOR_GRID_GREY),
            ('PADDING', (0,0), (-1,-1), 6),
            ('TEXTCOLOR', (1,1), (1,-1), COLOR_GREEN),
        ]))
        story.append(t_os_ch)
        
        story.append(Spacer(1, 15*mm))
        story.append(Paragraph("<b>Assinaturas de Encerramento e Entrega:</b>", style_body_bold))
        story.append(Spacer(1, 10*mm))
        
        os_sig = [
            [Paragraph("________________________________________<br/><b>TÉCNICO RESPONSÁVEL</b>", style_body),
             Paragraph("________________________________________<br/><b>ASSINATURA DE ACEITE DO CLIENTE</b>", style_body)]
        ]
        t_os_sig = Table(os_sig, colWidths=[87*mm, 87*mm])
        t_os_sig.setStyle(TableStyle([('ALIGN', (0,0), (-1,-1), 'CENTER')]))
        story.append(t_os_sig)

    elif doc_type == "contrato_prestacao":
        # ── 4. CONTRATO DE PRESTAÇÃO DE SERVIÇOS COMPLETO SRE ─────────────────
        total_servicos_sre = config["gestao_valor"] + config["materiais_valor"] + config["dutos_valor"]
        pres_subtitle = (
            "<b>CONTRATANTE:</b> " + config["cliente"] + "<br/>"
            "<b>CONTRATADA:</b> REFRIMIX TECNOLOGIA LTDA  |  CNPJ: 37.308.021/0001-89  |  CREA-SP Habilitado<br/>"
            "<b>ESCOPO DE ENGENHARIA:</b> Prestação de Serviços sob Regras SRE e SLAs Técnicos."
        )
        story.append(create_branded_header("CONTRATO DE PRESTAÇÃO DE SERVIÇOS SRE", pres_subtitle, style_header_title, style_body))

        story.append(Paragraph("QUADRO EXECUTIVO SRE", style_h1))
        sre_summary_rows = [
            [Paragraph("<b>Campo</b>", style_table_header), Paragraph("<b>Definicao Operacional</b>", style_table_header)],
            [Paragraph("Cliente", style_table_text_bold), Paragraph(config["cliente"], style_table_text)],
            [Paragraph("Escopo", style_table_text_bold), Paragraph("Prestacao de servicos HVAC-R com rastreabilidade, resposta organizada, evidencias de execucao e controle de risco tecnico.", style_table_text)],
            [Paragraph("Valor contratado", style_table_text_bold), Paragraph(format_currency(total_servicos_sre), style_table_text_bold)],
            [Paragraph("Garantia", style_table_text_bold), Paragraph(config["garantia_instalacao"], style_table_text)],
            [Paragraph("SLA critico", style_table_text_bold), Paragraph("Resposta inicial em ate 24 horas corridas para ocorrencias emergenciais, condicionada a acesso, agenda e disponibilidade de pecas.", style_table_text)],
        ]
        story.append(premium_table(sre_summary_rows, [42*mm, 132*mm]))
        story.append(Spacer(1, 5*mm))
        story.append(Paragraph(
            "A Refrimix Tecnologia aplica disciplina SRE a sistemas de climatizacao: prevencao de falhas, registro de "
            "evidencias, resposta mensuravel e melhoria continua dos ativos HVAC-R. Este contrato define o que sera "
            "atendido, como sera comprovado e quais limites dependem de terceiros, acesso, pecas ou aprovacoes.",
            style_body
        ))

        story.append(Paragraph("TERMOS E CONDIÇÕES DA PRESTAÇÃO", style_h1))

        terms = [
            ("1. RIGOR E MONITORAMENTO SRE", "A CONTRATADA adota práticas de SRE (Site Reliability Engineering) aplicadas a sistemas de climatização. Isso garante redundância mecânica ativa das unidades condensadoras, monitoramento de vibração e proteção anti-maresia de grau industrial."),
            ("2. VALORES COM RASTREABILIDADE TOTAL", f"Os serviços contratados têm o valor total de {format_currency(total_servicos_sre)}. A Refrimix oferece previsibilidade comercial, registro de escopo e controle de alteracoes por aditivo quando houver mudanca de premissas."),
            ("3. GARANTIAS E SLAs DE ATENDIMENTO", f"A garantia técnica de instalação é de {config['garantia_instalacao']}. O SLA de atendimento emergencial contra condensação e falhas mecânicas é de 24 horas corridas para o Condomínio."),
            ("4. ENGENHARIA DE SEGURANÇA E NR-10/NR-35", "Toda a equipe da CONTRATADA trabalha estritamente segurada e qualificada nas normas federais NR-10 (Segurança em Eletricidade) e NR-35 (Trabalho em Altura)."),
            ("5. LIMITES DO ESCOPO", "Pecas, obras civis, alteracoes eletricas prediais, automacao, acesso por terceiros e substituicoes fora do escopo inicial dependem de aprovacao previa e podem alterar prazo, custo e SLA."),
        ]
        
        for num, text in terms:
            story.append(Paragraph(f"<b>{num}</b>", style_h2))
            story.append(Paragraph(text, style_clause))
            story.append(Spacer(1, 2*mm))

        story.append(PageBreak())
        story.append(Paragraph("MATRIZ DE SLA E EVIDENCIAS", style_h1))
        sla_rows = [
            [Paragraph("<b>Tipo de chamado</b>", style_table_header), Paragraph("<b>Resposta</b>", style_table_header), Paragraph("<b>Evidencia</b>", style_table_header)],
            [Paragraph("Critico", style_table_text_bold), Paragraph("Ate 24h corridas", style_table_text), Paragraph("OS, fotos, diagnostico e plano de contencao.", style_table_text)],
            [Paragraph("Operacional", style_table_text_bold), Paragraph("Ate 2 dias uteis", style_table_text), Paragraph("Checklist, orientacao tecnica e registro de acao.", style_table_text)],
            [Paragraph("Preventivo", style_table_text_bold), Paragraph("Agenda programada", style_table_text), Paragraph("Relatorio de visita, medições, limpeza e recomendacoes.", style_table_text)],
            [Paragraph("Melhoria", style_table_text_bold), Paragraph("Sob proposta", style_table_text), Paragraph("Escopo, orcamento, prazo e aditivo aprovado.", style_table_text)],
        ]
        story.append(premium_table(sla_rows, [48*mm, 38*mm, 88*mm]))
        story.append(Spacer(1, 6*mm))

        resp_rows = [
            [Paragraph("<b>Parte</b>", style_table_header), Paragraph("<b>Responsabilidade</b>", style_table_header)],
            [Paragraph("Refrimix Tecnologia", style_table_text_bold), Paragraph("Triar chamado, orientar contencao, executar atendimento contratado, registrar evidencia e indicar risco tecnico recorrente.", style_table_text)],
            [Paragraph("Contratante", style_table_text_bold), Paragraph("Liberar acesso, informar sintomas com clareza, preservar seguranca do local, aprovar pecas/aditivos e manter pagamentos em dia.", style_table_text)],
            [Paragraph("Terceiros", style_table_text_bold), Paragraph("Fabricantes, administradora, obra civil, eletrica predial e automacao respondem por suas interferencias fora do escopo Refrimix.", style_table_text)],
        ]
        story.append(premium_table(resp_rows, [42*mm, 132*mm]))

        story.append(PageBreak())
        story.append(Paragraph("VIGENCIA, RELATORIOS E ASSINATURAS", style_h1))
        evidence_rows = [
            [Paragraph("<b>Entrega</b>", style_table_header), Paragraph("<b>Conteudo minimo</b>", style_table_header)],
            [Paragraph("Relatorio tecnico", style_table_text_bold), Paragraph("Diagnostico, acao executada, fotos quando aplicavel, pendencias e recomendacoes.", style_table_text)],
            [Paragraph("Ordem de servico", style_table_text_bold), Paragraph("Data, tecnico, atividade, status, assinatura ou aceite operacional.", style_table_text)],
            [Paragraph("Plano de melhoria", style_table_text_bold), Paragraph("Quando houver risco recorrente, proposta de correcao, prioridade e impacto esperado.", style_table_text)],
            [Paragraph("Documentacao legal", style_table_text_bold), Paragraph("ART, PMOC ou documentos correlatos quando contratados ou exigidos pelo escopo.", style_table_text)],
        ]
        story.append(premium_table(evidence_rows, [50*mm, 124*mm]))
        story.append(Spacer(1, 7*mm))
        story.append(Paragraph(
            "O aceite confirma que as partes compreendem o escopo SRE, os limites de SLA, as evidencias de execucao "
            "e as dependencias externas que podem afetar prazo ou custo.",
            style_body
        ))
        story.append(Spacer(1, 12*mm))
        story.append(Table([
            [Paragraph("________________________________________<br/>REFRIMIX TECNOLOGIA LTDA", style_body),
             Paragraph("________________________________________<br/>" + config["cliente"].upper(), style_body)]
        ], colWidths=[87*mm, 87*mm], style=[('ALIGN', (0,0), (-1,-1), 'CENTER')]))

    elif doc_type == "orcamento_material":
        # ── 5. ORÇAMENTO SÓ DE MATERIAL ──────────────────────────────────────
        mat_subtitle = (
            "<b>Cliente:</b> " + config["cliente"] + "  |  "
            "<b>Data:</b> " + config["data"] + "<br/>"
            "<b>Tipo:</b> Fornecimento exclusivo de materiais com isolamento classe naval."
        )
        story.append(create_branded_header("ORÇAMENTO DE MATERIAIS E INSUMOS", mat_subtitle, style_header_title, style_body))
        
        story.append(Paragraph("DETALHAMENTO DE MATERIAIS E INSUMOS ESPECIAIS", style_h1))
        
        mat_rows = [
            [Paragraph("<b>Item / Insumo Técnico</b>", style_table_header), Paragraph("<b>Descrição do Material</b>", style_table_header), Paragraph("<b>Valor</b>", style_table_header)],
            [Paragraph("Insumos Frigorígenos", style_table_text), Paragraph("Tubulação de cobre classe A, isolamento blindado elastomérico, fita vinílica e solda prata.", style_table_text), Paragraph(format_currency(config["materiais_valor"] * 0.4), style_table_text_bold)],
            [Paragraph("Sistema de Dutos", style_table_text), Paragraph("Dutos de MPU pré-isolados, dampers e grelhas de alumínio anodizado.", style_table_text), Paragraph(format_currency(config["dutos_valor"]), style_table_text_bold)],
            [Paragraph("Proteção Naval e Inox", style_table_text), Paragraph("Suportes em inox 304, parafusos e arruelas inoxidáveis, verniz naval anticorrosivo.", style_table_text), Paragraph(format_currency(config["materiais_valor"] * 0.6), style_table_text_bold)],
        ]
        
        for item in config["dutos_extras"]:
            mat_rows.append([
                Paragraph(f"<font color='#2e7d32'>➕ <b>Extra: {item['desc']}</b></font>", style_table_text),
                Paragraph("Insumo ou acessório adicional para o duto.", style_table_text),
                Paragraph(f"<font color='#2e7d32'><b>{format_currency(item['valor'])}</b></font>", style_table_text_bold)
            ])
            
        total_mat = config["materiais_valor"] + config["dutos_valor"] + sum(item["valor"] for item in config["dutos_extras"])
        
        mat_rows.append([
            Paragraph("<b>TOTAL GERAL DE MATERIAIS</b>", style_table_header),
            Paragraph("<b>Faturamento e Logística Inclusa (Guarujá)</b>", style_table_header),
            Paragraph(format_currency(total_mat), style_table_header)
        ])
        
        t_mat = Table(mat_rows, colWidths=[45*mm, 85*mm, 44*mm])
        t_mat.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), COLOR_PRIMARY_NAVY),
            ('GRID', (0,0), (-1,-1), 0.5, COLOR_GRID_GREY),
            ('PADDING', (0,0), (-1,-1), 8),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BACKGROUND', (0, len(mat_rows)-1), (-1, len(mat_rows)-1), COLOR_PRIMARY_NAVY),
        ]))
        story.append(t_mat)
        
        story.append(Spacer(1, 10*mm))
        story.append(Paragraph(
            "<b>Condições logísticas:</b> Entrega direta no local da obra em até 3 dias úteis após faturamento. "
            "Todos os materiais contam com nota fiscal eletrônica e rastreabilidade total de lote do fabricante.",
            style_body
        ))

    elif doc_type == "orcamento_mao_de_obra":
        # ── 6. ORÇAMENTO SÓ DE MÃO DE OBRA ───────────────────────────────────
        labor_subtitle = (
            "<b>Cliente:</b> " + config["cliente"] + "  |  "
            "<b>Data:</b> " + config["data"] + "<br/>"
            "<b>Tipo:</b> Execução de obra por equipe própria altamente qualificada e credenciada Daikin."
        )
        story.append(create_branded_header("ORÇAMENTO DE MÃO DE OBRA E EXECUÇÃO", labor_subtitle, style_header_title, style_body))
        
        story.append(Paragraph("DETALHAMENTO DE HORAS TÉCNICAS E GESTÃO DE ENGENHARIA", style_h1))
        
        labor_rows = [
            [Paragraph("<b>Serviço / Atividade Técnica</b>", style_table_header), Paragraph("<b>Horas/Regime</b>", style_table_header), Paragraph("<b>Valor</b>", style_table_header)],
            [Paragraph("Engenharia SRE e Dimensionamento de Fluido", style_table_text), Paragraph("Dedicado (Fase de Planejamento)", style_table_text), Paragraph(format_currency(config["gestao_valor"] * 0.4), style_table_text_bold)],
            [Paragraph("Instalação, Brasagem e Interligação Frigorígena", style_table_text), Paragraph("Equipe própria de instalação especializada", style_table_text), Paragraph(format_currency(config["gestao_valor"] * 0.6), style_table_text_bold)],
            [Paragraph("Comissionamento Técnico, PMOC e Emissão de ART", style_table_text), Paragraph("Engenheiro Mecânico CREA Ativo", style_table_text), Paragraph(format_currency(2500.00), style_table_text_bold)],
        ]
        
        total_labor = (config["gestao_valor"]) + 2500.00
        
        labor_rows.append([
            Paragraph("<b>TOTAL GERAL DE MÃO DE OBRA</b>", style_table_header),
            Paragraph("<b>Equipe Própria Refrimix e Engenharia Habilitada</b>", style_table_header),
            Paragraph(format_currency(total_labor), style_table_header)
        ])
        
        t_labor = Table(labor_rows, colWidths=[65*mm, 65*mm, 44*mm])
        t_labor.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), COLOR_PRIMARY_NAVY),
            ('GRID', (0,0), (-1,-1), 0.5, COLOR_GRID_GREY),
            ('PADDING', (0,0), (-1,-1), 8),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BACKGROUND', (0, len(labor_rows)-1), (-1, len(labor_rows)-1), COLOR_PRIMARY_NAVY),
        ]))
        story.append(t_labor)
        
        story.append(Spacer(1, 10*mm))
        story.append(Paragraph(
            "<b>Segurança e Certificações:</b> Toda a equipe envolvida possui treinamento ativo nas normas "
            "federais NR-10 e NR-35, garantindo total segurança jurídica e operacional para o Condomínio.",
            style_body
        ))
        
    if doc_type == "proposta":
        def proposal_canvas(*args, **kwargs):
            return NumberedCanvas(*args, skip_first_standard_decorations=True, **kwargs)
        doc.build(story, canvasmaker=proposal_canvas, onFirstPage=draw_cover_background, onLaterPages=draw_later_background)
    else:
        doc.build(story, canvasmaker=NumberedCanvas, onFirstPage=draw_later_background, onLaterPages=draw_later_background)
    print(f"[SUCCESS] PDF gerado em: {pdf_path}")
    
    # Mapeamento do tipo de documento para a pasta de entrega correspondente
    def get_delivery_folder(d_type):
        mapping = {
            "proposta": "01_PROPOSTAS_TECNICAS",
            "contrato": "02_CONTRATOS_E_SLA",
            "contrato_prestacao": "02_CONTRATOS_E_SLA",
            "os": "03_ORDENS_DE_SERVICO",
            "orcamento_material": "05_ORCAMENTOS/MATERIAL",
            "orcamento_mao_de_obra": "05_ORCAMENTOS/MAO_DE_OBRA"
        }
        return mapping.get(d_type, "")

    # SRE Automated Delivery and Google Drive Synchronization (Estrutura Organizada por Cliente)
    local_delivery_root = "/home/will/Refrimix-tecnologia"
    gdrive_mount_root = "/run/user/1000/gvfs/google-drive:host=gmail.com,user=refrimixtecnologia/0AF2hQ71kEgWWUk9PVA/15UxA-7DTRUd7LkDC7wyLXZqc9neN-TP0"
    
    # Extrai o nome do cliente e normaliza para pasta
    import re
    client_name = config.get("cliente", "Cliente_Geral").strip()
    client_folder = re.sub(r'[\\/*?:"<>|]', "", client_name).replace(" ", "_")
    
    subfolder = get_delivery_folder(doc_type)
    if subfolder:
        filename = os.path.basename(pdf_path)
        
        # Estrutura local com subpasta do cliente
        local_dest_dir = os.path.join(local_delivery_root, subfolder, client_folder)
        os.makedirs(local_dest_dir, exist_ok=True)
        local_dest_file = os.path.join(local_dest_dir, filename)
        
        try:
            with open(pdf_path, 'rb') as fsrc:
                content = fsrc.read()
                
            # Salva na entrega local estruturada
            with open(local_dest_file, 'wb') as fdst:
                fdst.write(content)
            print(f"[DELIVERY] Copiado para entrega local estruturada por cliente: {local_dest_file}")
                
            # Sincroniza com o Google Drive estruturado
            if os.path.exists(gdrive_mount_root):
                gdrive_dest_dir = os.path.join(gdrive_mount_root, subfolder, client_folder)
                os.makedirs(gdrive_dest_dir, exist_ok=True)
                gdrive_dest_file = os.path.join(gdrive_dest_dir, filename)
                
                with open(gdrive_dest_file, 'wb') as fdst:
                    fdst.write(content)
                print(f"[DELIVERY GDRIVE] Sincronizado para Google Drive estruturado por cliente: {gdrive_dest_file}")
            else:
                print("[SRE INFO] Google Drive não está montado. Ignorando sincronização remota.")
        except Exception as e:
            print(f"[WARNING] Erro de entrega: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Master Document Compiler Refrimix PDF")
    parser.add_argument("--cliente", required=True)
    parser.add_argument("--tipo", choices=["proposta", "contrato", "os", "contrato_prestacao", "orcamento_material", "orcamento_mao_de_obra"], default="proposta")
    parser.add_argument("--data", default="")
    parser.add_argument("--output", required=True)
    parser.add_argument("--gestao_valor", type=float, default=39938.06)
    parser.add_argument("--materiais_valor", type=float, default=25369.00)
    parser.add_argument("--dutos_valor", type=float, default=63150.00)
    parser.add_argument("--validade_proposta", default="30 dias")
    parser.add_argument("--garantia_instalacao", default="12 meses")
    parser.add_argument("--equipamentos", default="[]")
    parser.add_argument("--dutos_extras", default="[]")
    parser.add_argument("--checklist_incluir", type=bool, default=True)
    
    # OS / Contract extra options
    parser.add_argument("--tecnico_nome", default="Equipe Refrimix")
    parser.add_argument("--placa_veiculo", default="LOG-1A80")
    parser.add_argument("--cnpj_cliente", default="")
    parser.add_argument("--obra_prazo", default="15 dias úteis")
    
    args = parser.parse_args()
    
    if not args.data:
        meses = [
            "janeiro", "fevereiro", "março", "abril", "maio", "junho",
            "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"
        ]
        now = datetime.now()
        args.data = f"{now.day} de {meses[now.month - 1]} de {now.year}"
        
    try:
        equipamentos = json.loads(args.equipamentos)
        if not equipamentos:
            equipamentos = [
                {"modelo": "Daikin Cassete Inverter Premium", "btu": "36.000 BTU", "qtd": 2, "tecnologia": "Inverter Neodymium", "valor": 12500.00},
                {"modelo": "Daikin Cassete Multi-Split", "btu": "18.000 BTU", "qtd": 1, "tecnologia": "Inverter R32", "valor": 6800.00}
            ]
    except Exception:
        equipamentos = []
        
    try:
        dutos_extras = json.loads(args.dutos_extras)
    except Exception:
        dutos_extras = []
        
    config = {
        "cliente": args.cliente,
        "tipo": args.tipo,
        "data": args.data,
        "output": args.output,
        "gestao_valor": args.gestao_valor,
        "materiais_valor": args.materiais_valor,
        "dutos_valor": args.dutos_valor,
        "validade_proposta": args.validade_proposta,
        "garantia_instalacao": args.garantia_instalacao,
        "equipamentos": equipamentos,
        "dutos_extras": dutos_extras,
        "checklist_incluir": args.checklist_incluir,
        "tecnico_nome": args.tecnico_nome,
        "placa_veiculo": args.placa_veiculo,
        "cnpj_cliente": args.cnpj_cliente,
        "obra_prazo": args.obra_prazo
    }
    
    build_master_document(config)

if __name__ == "__main__":
    main()

import tempfile
import base64
import httpx
import logging

logger = logging.getLogger(__name__)

def generate_pdf(context_data: dict) -> bytes:
    """Gera um PDF em memória baseado nos dados do contexto."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name
        
    # Ensure all required keys exist in context_data for build_master_document
    default_config = {
        "tipo": "orcamento_material",
        "cliente": context_data.get("cliente_nome", "Cliente"),
        "data": context_data.get("data", datetime.now().strftime("%d/%m/%Y")),
        "output": tmp_path,
        "gestao_valor": 0,
        "materiais_valor": 0,
        "dutos_valor": 0,
        "validade_proposta": "15 dias",
        "garantia_instalacao": "12 meses",
        "equipamentos": [],
        "dutos_extras": [],
        "checklist_incluir": True,
        "tecnico_nome": "Equipe Refrimix",
        "placa_veiculo": "",
        "cnpj_cliente": "",
        "obra_prazo": "15 dias",
    }
    default_config.update(context_data)
    
    build_master_document(default_config)
    
    with open(tmp_path, "rb") as f:
        pdf_bytes = f.read()
        
    os.remove(tmp_path)
    return pdf_bytes

async def send_pdf_via_evolution(phone: str, pdf_bytes: bytes, filename: str = "orcamento.pdf", instance: str = "default") -> bool:
    """Envia o PDF gerado via Evolution API para o lead."""
    api_key = os.getenv("EVOLUTION_API_KEY", os.getenv("AUTHENTICATION_API_KEY", ""))
    api_url = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
    instance_name = os.getenv("EVOLUTION_INSTANCE", instance)
    
    b64_data = base64.b64encode(pdf_bytes).decode('utf-8')
    
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(
                f"{api_url}/message/sendMedia/{instance_name}",
                headers={"apikey": api_key, "Content-Type": "application/json"},
                json={
                    "number": phone,
                    "mediatype": "document",
                    "media": b64_data,
                    "mimetype": "application/pdf",
                    "fileName": filename,
                },
            )
            if resp.status_code in (200, 201):
                logger.info(f"PDF {filename} enviado com sucesso para {phone}.")
                return True
            else:
                logger.warning(f"Erro Evolution API PDF {resp.status_code}: {resp.text}")
                return False
    except Exception as e:
        logger.error(f"Falha ao enviar PDF para {phone}: {e}")
        return False
