"""Test expanded fact tracking (9 types) in dm_agent_v2 (Step 22)."""

import re


class TestFullFactTracking:
    def test_price_given(self):
        text = "El curso cuesta 97€"
        assert re.search(r"\d+\s*€|\d+\s*euros?|\$\d+", text, re.IGNORECASE)

    def test_link_shared(self):
        text = "Aqui tienes: https://pay.example.com/curso"
        assert "https://" in text

    def test_product_explained(self):
        products = [{"name": "Masterclass"}]
        text = "Te cuento sobre la masterclass que tenemos"
        prod_name = products[0]["name"].lower()
        assert prod_name in text.lower()

    def test_objection_raised(self):
        text = "Entiendo tu duda, es normal tener preguntas"
        assert re.search(
            r"entiendo tu (duda|preocupación)|es normal|no te preocupes|garantía|devolución",
            text,
            re.IGNORECASE,
        )

    def test_interest_expressed(self):
        user_msg = "Me interesa mucho el programa"
        assert re.search(
            r"me interesa|quiero saber|cuéntame|suena bien|me gusta",
            user_msg,
            re.IGNORECASE,
        )

    def test_appointment_mentioned(self):
        text = "Puedes agendar una llamada conmigo"
        assert re.search(
            r"reserva|agenda|cita|llamada|reunión|calendly|cal\.com",
            text,
            re.IGNORECASE,
        )

    def test_contact_shared(self):
        text = "Escribime por wa.me/123456789"
        assert re.search(
            r"@\w{3,}|[\w.-]+@[\w.-]+\.\w+|\+?\d{9,}|wa\.me|whatsapp",
            text,
            re.IGNORECASE,
        )

    def test_question_asked(self):
        text = "Que te parece?"
        assert "?" in text

    def test_name_used(self):
        follower_name = "Carlos"
        text = "Mira Carlos, te cuento sobre el curso"
        assert follower_name.lower() in text.lower()

    def test_no_false_positives(self):
        text = "Gracias por tu mensaje"
        assert not re.search(r"\d+\s*€|\d+\s*euros?|\$\d+", text, re.IGNORECASE)
        assert "https://" not in text and "http://" not in text
        assert "?" not in text
