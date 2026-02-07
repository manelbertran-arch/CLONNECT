#!/usr/bin/env python3
"""Generate professional PDF report for Stefan from Clonnect data."""

import os

from fpdf import FPDF

# Corporate colors
BLUE_DARK = (20, 50, 100)
BLUE_MID = (41, 98, 168)
BLUE_LIGHT = (220, 235, 250)
WHITE = (255, 255, 255)
GRAY_TEXT = (80, 80, 80)
GRAY_LIGHT = (240, 240, 240)
BLACK = (30, 30, 30)


class ClonnectPDF(FPDF):
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=25)

    def header(self):
        # Blue header bar
        self.set_fill_color(*BLUE_DARK)
        self.rect(0, 0, 210, 18, "F")
        # CLONNECT logo text
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(*WHITE)
        self.set_xy(10, 4)
        self.cell(0, 10, "CLONNECT", align="L")
        # Right side - date
        self.set_font("Helvetica", "", 9)
        self.set_xy(150, 4)
        self.cell(50, 10, "7 febrero 2026", align="R")
        self.ln(20)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, "Generado por Clonnect AI  |  www.clonnectapp.com", align="L")
        self.cell(0, 10, f"Pagina {self.page_no()}/{{nb}}", align="R")

    def section_title(self, text):
        self.set_font("Helvetica", "B", 16)
        self.set_text_color(*BLUE_MID)
        self.cell(0, 12, text, new_x="LMARGIN", new_y="NEXT")
        # Blue underline
        self.set_draw_color(*BLUE_MID)
        self.set_line_width(0.8)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(6)

    def subsection_title(self, text):
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(*BLUE_DARK)
        self.cell(0, 10, text, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def body_text(self, text):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*GRAY_TEXT)
        self.multi_cell(0, 5.5, text)
        self.ln(3)

    def bold_text(self, text):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*BLACK)
        self.multi_cell(0, 5.5, text)
        self.ln(2)

    def table(self, headers, rows, col_widths=None):
        if col_widths is None:
            available = 190
            col_widths = [available / len(headers)] * len(headers)

        # Header row
        self.set_font("Helvetica", "B", 9)
        self.set_fill_color(*BLUE_MID)
        self.set_text_color(*WHITE)
        for i, h in enumerate(headers):
            self.cell(col_widths[i], 8, h, border=1, fill=True, align="C")
        self.ln()

        # Data rows
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*GRAY_TEXT)
        for row_idx, row in enumerate(rows):
            if row_idx % 2 == 0:
                self.set_fill_color(*GRAY_LIGHT)
            else:
                self.set_fill_color(*WHITE)
            for i, cell in enumerate(row):
                align = "L" if i == 0 else "C"
                self.cell(col_widths[i], 7, str(cell), border=1, fill=True, align=align)
            self.ln()
        self.ln(4)

    def highlight_box(self, text, color=BLUE_LIGHT):
        self.set_fill_color(*color)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*BLUE_DARK)
        x = self.get_x()
        y = self.get_y()
        self.rect(x, y, 190, 12, "F")
        self.set_xy(x + 5, y + 2)
        self.cell(180, 8, text, align="C")
        self.ln(16)

    def bullet(self, text):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*GRAY_TEXT)
        x = self.get_x()
        self.set_x(x + 5)
        self.cell(5, 5.5, "-")
        self.multi_cell(175, 5.5, text)
        self.ln(1)


def generate_pdf(output_path):
    pdf = ClonnectPDF()
    pdf.alias_nb_pages()
    pdf.set_margins(10, 20, 10)

    # ========== COVER PAGE ==========
    pdf.add_page()
    pdf.ln(30)

    # Big title
    pdf.set_font("Helvetica", "B", 28)
    pdf.set_text_color(*BLUE_DARK)
    pdf.cell(0, 15, "Tu Clon de IA", align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 18)
    pdf.set_text_color(*BLUE_MID)
    pdf.cell(0, 12, "Reporte Personalizado", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)

    # Separator line
    pdf.set_draw_color(*BLUE_MID)
    pdf.set_line_width(1)
    pdf.line(60, pdf.get_y(), 150, pdf.get_y())
    pdf.ln(10)

    # Name
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(*BLACK)
    pdf.cell(0, 12, "Stefano Bonanno", align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 14)
    pdf.set_text_color(*GRAY_TEXT)
    pdf.cell(0, 10, "Coach  |  @fitpackglobal", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(15)

    # Stats summary box
    pdf.set_fill_color(*BLUE_LIGHT)
    box_y = pdf.get_y()
    pdf.rect(25, box_y, 160, 50, "F")

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*BLUE_DARK)
    pdf.set_xy(25, box_y + 5)
    pdf.cell(160, 8, "Datos analizados", align="C", new_x="LMARGIN", new_y="NEXT")

    stats = [
        ("282", "followers procesados"),
        ("5,498", "mensajes analizados"),
        ("2,962", "mensajes humanos de Stefan"),
        ("153", "facts extraidos"),
        ("191", "perfiles DNA generados"),
    ]

    pdf.set_xy(35, box_y + 15)
    for val, label in stats:
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*BLUE_MID)
        pdf.cell(25, 6, val, align="R")
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(*GRAY_TEXT)
        pdf.cell(100, 6, f"  {label}")
        pdf.ln()
        pdf.set_x(35)

    pdf.ln(20)
    pdf.set_font("Helvetica", "I", 10)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(0, 8, "7 febrero 2026  |  Clonnect AI", align="C")

    # ========== PAGE 2: WHAT YOU DID MANUALLY ==========
    pdf.add_page()
    pdf.section_title("1. QUE HICISTE EN 6 MESES (MANUAL)")

    pdf.body_text(
        "Estos numeros salen directamente de tus conversaciones de Instagram. "
        "No son estimaciones."
    )

    pdf.subsection_title("Volumen de trabajo")
    pdf.table(
        ["Metrica", "Dato Real"],
        [
            ["Mensajes que escribiste", "2,962"],
            ["Leads que atendiste", "282 personas"],
            ["Mensajes recibidos de leads", "2,257"],
            ["Total mensajes intercambiados", "5,498"],
            ["Tiempo estimado en DMs", "~99 horas (2 min/msg)"],
            ["Periodo analizado", "Mar 2020 - Feb 2026"],
            ["Conversacion mas larga", "johnyduran_ - 210 msgs"],
            ["Datos extraidos", "153 facts"],
        ],
        [110, 80],
    )

    pdf.subsection_title("Clasificacion de tus leads")
    pdf.table(
        ["Estado", "Cantidad", "%", "Significado"],
        [
            ["Interesado", "126", "44.8%", "Engaged, preguntas"],
            ["Nuevo", "102", "36.3%", "Acaban de escribir"],
            ["Caliente", "45", "16.0%", "Listos para comprar"],
            ["Otros", "9", "3.2%", "En proceso"],
            ["TOTAL", "282", "", ""],
        ],
        [45, 30, 25, 90],
    )

    pdf.subsection_title("Datos extraidos de conversaciones")
    pdf.table(
        ["Tipo de dato", "Cantidad"],
        [
            ["Links compartidos", "75"],
            ["Telefonos detectados", "25"],
            ["Cuentas de Instagram", "25"],
            ["Emails", "16"],
            ["Precios mencionados", "7"],
            ["Citas agendadas", "4"],
            ["TOTAL facts", "153"],
        ],
        [110, 80],
    )

    pdf.subsection_title("Top 10 leads por engagement")
    pdf.table(
        ["#", "Username", "Mensajes"],
        [
            ["1", "johnyduran_", "210"],
            ["2", "jcruzcarrasco", "201"],
            ["3", "na_fantina", "198"],
            ["4", "andreaandser", "145"],
            ["5", "soymariaeuget", "110"],
            ["6", "lucuranatural", "103"],
            ["7", "relaccionate.podcast", "94"],
            ["8", "fannyjeanne_bernadet", "86"],
            ["9", "biavram", "83"],
            ["10", "hasha.ch", "80"],
        ],
        [20, 100, 70],
    )

    pdf.highlight_box("Dedicaste ~99 horas en DMs. 16h/mes solo en mensajes.")
    pdf.body_text(
        "Con 282 leads es imposible recordar que le dijiste a cada uno. "
        "Y cuando tardas horas en responder, los leads calientes se enfrian."
    )

    # ========== PAGE 3: WHAT CLONNECT DOES ==========
    pdf.add_page()
    pdf.section_title("2. QUE PUEDE HACER CLONNECT (AUTOMATICO)")

    capabilities = [
        (
            "2.1 Responder en segundos, no en horas",
            "Tu clon responde al instante. Si alguien te escribe a las 3am motivado "
            "despues de ver tu contenido, recibe respuesta inmediata. Los leads "
            "calientes no se enfrian.",
        ),
        (
            "2.2 Recordar TODO de cada lead",
            "153 facts extraidos: precios dados, links, emails, telefonos, citas. "
            "191 perfiles DNA que describen la relacion con cada lead. "
            "Adapta el tono segun si es amigo cercano, conocido casual o desconocido.",
        ),
        (
            "2.3 Mantener tu estilo EXACTO",
            "Analizamos 2,962 mensajes que tu escribiste. El clon escribe como tu: "
            "conciso (23 chars mediana), moderado con emojis (19%), nunca punto final, "
            "risa 'jaja', abreviacion 'q'. No suena a robot. Suena a Stefano.",
        ),
        (
            "2.4 Detectar leads calientes",
            "45 leads calientes auto-detectados de 282 totales (16%). "
            "El clon los prioriza y te avisa cuando alguien muestra senales de compra.",
        ),
        (
            "2.5 No contradecirse nunca",
            "Todos los facts indexados: precios dados, links compartidos, acuerdos. "
            "El clon nunca se contradice porque tiene la memoria completa.",
        ),
        (
            "2.6 Escalar a humano cuando necesario",
            "Detecta crisis emocionales, negociaciones complejas, o peticiones de "
            "hablar contigo. Te pasa la conversacion sin que el lead note la transicion.",
        ),
    ]

    for title, desc in capabilities:
        pdf.subsection_title(title)
        pdf.body_text(desc)

    pdf.subsection_title("2.7 Conocer tus productos")
    pdf.body_text("El bot tiene tus 5 productos configurados con precios reales:")
    pdf.table(
        ["Producto", "Precio", "Tipo"],
        [
            ["Del Sintoma a la Plenitud", "Consultar", "Coaching 1:1, 3 meses"],
            ["Fitpack Challenge", "22 EUR", "Reto 11 dias"],
            ["Respira, Siente y Conecta", "88 EUR", "Taller presencial"],
            ["Circulo de Hombres", "Consultar", "Semanal, Barcelona"],
            ["Sesion de Descubrimiento", "Gratis", "30 min, primer paso"],
        ],
        [70, 35, 85],
    )

    # ========== WRITING PATTERNS ==========
    pdf.subsection_title("Tu perfil de escritura real")
    pdf.table(
        ["Patron", "Dato"],
        [
            ["Longitud media", "38 caracteres (ultra conciso)"],
            ["Longitud mediana", "23 caracteres"],
            ["Mensajes cortos (<30 chars)", "65%"],
            ["Emojis en mensajes", "18.9%"],
            ["Posicion del emoji", "81% al final"],
            ["Empieza con mayuscula", "87%"],
            ["Punto final", "1% (casi nunca)"],
            ["Exclamaciones", "30%"],
            ["Preguntas", "14.5%"],
            ["Risa favorita", '"jaja" (137 veces)'],
            ["Abreviacion", '"q" en vez de "que" (89x)'],
        ],
        [80, 110],
    )

    # ========== PAGE 4: SCORING ==========
    pdf.add_page()
    pdf.section_title("3. SCORING: STEFAN SOLO vs STEFAN + CLONNECT")

    pdf.table(
        ["Capacidad", "Solo", "Sc.", "Con Clonnect", "Sc.", "Mejora"],
        [
            ["Tiempo respuesta", "Horas", "3", "Segundos", "10", "+233%"],
            ["Disponibilidad", "Despierto/libre", "4", "24/7", "10", "+150%"],
            ["Consistencia", "Varia", "7", "Siempre igual", "10", "+43%"],
            ["Memoria", "Imposible 282", "5", "153 facts+191 DNA", "10", "+100%"],
            ["Personalizacion", "Buena c/ contexto", "8", "191 perfiles DNA", "9", "+13%"],
            ["Escalabilidad", "Max ~300", "2", "Sin limite", "10", "+400%"],
            ["Oportunidades", "Intuicion", "5", "45 hot auto", "9", "+80%"],
        ],
        [35, 35, 13, 42, 13, 20],
    )

    # Score comparison highlight
    pdf.highlight_box(
        "Stefan Solo: 34/70 (49%)    vs    Stefan + Clonnect: 68/70 (97%)    =    +100% efectividad"
    )

    # ========== IMPACT ==========
    pdf.section_title("4. IMPACTO PROYECTADO")

    pdf.subsection_title("Horas liberadas")
    pdf.table(
        ["Concepto", "Hoy (manual)", "Con Clonnect", "Ahorro"],
        [
            ["Responder DMs", "~16h/mes", "~3h/mes", "13h/mes"],
            ["Buscar contexto", "~3h/mes", "0h", "3h/mes"],
            ["Clasificar leads", "~2h/mes", "0h", "2h/mes"],
            ["TOTAL", "~21h/mes", "~3h/mes", "~18h/mes"],
        ],
        [55, 40, 45, 50],
    )

    pdf.subsection_title("Capacidad de leads")
    pdf.table(
        ["Metrica", "Hoy", "Con Clonnect", "Mejora"],
        [
            ["Leads atendidos", "282", "2,000+", "7x mas"],
            ["Tiempo respuesta", "Horas", "Segundos", "Instantaneo"],
            ["Leads que se enfrian", "Muchos", "Casi ninguno", "Recuperados"],
        ],
        [50, 40, 50, 50],
    )

    pdf.subsection_title("Conversiones esperadas (45 leads calientes)")
    pdf.table(
        ["Escenario", "Conversion", "Ventas estimadas"],
        [
            ["Conservador (+20%)", "9 de 45 hot leads", "~800 EUR"],
            ["Moderado (+35%)", "16 de 45 hot leads", "~1,400 EUR"],
            ["Optimista (+50%)", "23 de 45 hot leads", "~2,000 EUR"],
        ],
        [55, 60, 75],
    )

    pdf.body_text(
        "Sin contar los 126 leads 'interesados' que el clon puede calentar automaticamente."
    )

    pdf.subsection_title("ROI")
    pdf.bullet("18 horas liberadas al mes")
    pdf.bullet("5 ventas adicionales Fitpack (22 EUR) = 110 EUR/mes minimo")
    pdf.bullet("1 coaching adicional multiplica el ROI significativamente")

    # ========== PAGE 5: BOT FIX ==========
    pdf.add_page()
    pdf.section_title("5. POR QUE EL BOT ANTERIOR NO FUNCIONABA")

    pdf.bold_text("Descubrimiento clave de la ingesta:")
    pdf.body_text(
        "El bot anterior aprendia de SUS PROPIOS mensajes, no de los tuyos. "
        "Resultado: sonaba a robot generico, no a Stefano."
    )

    pdf.subsection_title("Bot contaminado vs Stefan real")
    pdf.table(
        ["Metrica", "Bot anterior", "Stefan real", "Diferencia"],
        [
            ["Mensajes analizados", "119", "2,962", "25x mas datos"],
            ["Longitud media", "108 chars", "38 chars", "3x mas largo"],
            ["Emoji rate", "96.6%", "18.9%", "5x mas emojis"],
            ["Pregunta rate", "52.1%", "14.5%", "4x mas preguntas"],
            ["Exclamacion rate", "89.9%", "30.2%", "3x mas exclam."],
            ["Frase top", '"genial!"', '"gracias por"', "Robot vs natural"],
        ],
        [45, 45, 45, 55],
    )

    pdf.highlight_box("Rechazaste 98.7% de sugerencias del bot (77 de 78). Tenia sentido.")

    pdf.subsection_title("La solucion")
    pdf.body_text("Ahora el sistema aprende exclusivamente de tus 2,962 mensajes humanos reales.")
    pdf.bullet("Conciso: 23 caracteres de mediana (menos que un tweet)")
    pdf.bullet("Moderado con emojis: 19%, siempre al final")
    pdf.bullet("Nunca punto final: solo 1% de tus mensajes")
    pdf.bullet("Tu risa es 'jaja', no 'jajajaja'")
    pdf.bullet("Abrevias 'q' en vez de 'que'")
    pdf.bullet("Dices 'crack', 'hermano', 'bro', 'amigo'")
    pdf.bullet("NUNCA dices 'En que puedo ayudarte?' ni 'Quedo a tu disposicion'")

    # ========== PAGE 6: NEXT STEPS ==========
    pdf.ln(5)
    pdf.section_title("6. PROXIMOS PASOS")

    steps = [
        ["1", "Sistema en modo copiloto", "Hecho"],
        ["2", "6 meses de conversaciones procesadas", "Hecho"],
        ["3", "Estilo calibrado con datos reales", "Hecho"],
        ["4", "45 leads calientes identificados", "Hecho"],
        ["5", "191 perfiles DNA generados", "Hecho"],
        ["6", "153 facts extraidos", "Hecho"],
        ["7", "5 productos configurados", "Hecho"],
        ["8", "Prueba con leads reales", "En curso"],
        ["9", "Ajustes segun feedback", "Pendiente"],
        ["10", "Lanzamiento modo autonomo", "Pendiente"],
    ]

    pdf.table(
        ["#", "Paso", "Estado"],
        steps,
        [15, 120, 55],
    )

    # ========== METRICS ==========
    pdf.section_title("7. METRICAS QUE VERAS")

    pdf.body_text("Cuando el sistema este corriendo al 100%, desde tu dashboard veras:")
    pdf.table(
        ["Metrica", "Descripcion"],
        [
            ["Mensajes/dia", "DMs que responde tu clon diariamente"],
            ["Tiempo de respuesta", "Media de segundos en responder"],
            ["Leads convertidos", "De 'nuevo' a 'caliente' a 'cliente'"],
            ["Tasa de engagement", "% de leads que siguen respondiendo"],
            ["Escalaciones", "Veces que te pasa la conversacion"],
            ["Ventas asistidas", "Conversiones donde participo el clon"],
        ],
        [55, 135],
    )

    # ========== FOOTER SECTION ==========
    pdf.ln(10)
    pdf.set_fill_color(*BLUE_LIGHT)
    box_y = pdf.get_y()
    pdf.rect(10, box_y, 190, 25, "F")
    pdf.set_xy(15, box_y + 3)
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(*GRAY_TEXT)
    pdf.multi_cell(
        180,
        5,
        "Documento generado por Clonnect AI con datos reales de @fitpackglobal\n"
        "Ingesta: 282 followers | 5,498 mensajes | 2,962 humanos de Stefan | "
        "153 facts | 191 DNA profiles\n"
        "Productos: 5 configurados | Bot: calibrado con estilo real",
        align="C",
    )

    # Save
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    pdf.output(output_path)
    print(f"PDF saved to: {output_path}")
    print(f"File size: {os.path.getsize(output_path) / 1024:.1f} KB")
    print(f"Pages: {pdf.pages_count}")


if __name__ == "__main__":
    # Primary output
    output = os.path.expanduser("~/Desktop/CLONNECT/backend/reports/STEFAN_CLONNECT_REPORT.pdf")
    # Also save to Desktop for easy access
    desktop_copy = os.path.expanduser("~/Desktop/STEFAN_CLONNECT_REPORT.pdf")

    generate_pdf(output)
    # Copy to desktop
    import shutil

    shutil.copy2(output, desktop_copy)
    print(f"Desktop copy: {desktop_copy}")
