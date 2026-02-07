"""Audit tests for services/creator_knowledge_service.py."""

import json
import os
import tempfile

from services.creator_knowledge_service import (
    CreatorKnowledge,
    CreatorKnowledgeService,
    get_creator_knowledge_service,
)


class TestCreatorKnowledgeServiceInit:
    """Test 1: init/import - Service initializes with correct defaults."""

    def test_service_default_directory(self):
        svc = CreatorKnowledgeService()
        assert svc.knowledge_dir == "data/stefan_knowledge"
        assert svc._knowledge_cache == {}

    def test_service_custom_directory(self):
        svc = CreatorKnowledgeService(knowledge_dir="/tmp/knowledge")
        assert svc.knowledge_dir == "/tmp/knowledge"

    def test_creator_knowledge_dataclass(self):
        knowledge = CreatorKnowledge(
            creator_id="c1",
            name="Test Creator",
            nickname="Testy",
            location="Barcelona",
            profession=["coach"],
            services=["yoga"],
            communication_style={"tone": "friendly"},
            values=["health"],
            content_themes=["wellness"],
            faqs={"pricing": "Contact me"},
        )
        assert knowledge.creator_id == "c1"
        assert knowledge.name == "Test Creator"

    def test_singleton_returns_same_instance(self):
        import services.creator_knowledge_service as mod

        mod._knowledge_service = None
        s1 = get_creator_knowledge_service()
        s2 = get_creator_knowledge_service()
        assert s1 is s2
        mod._knowledge_service = None  # cleanup

    def test_knowledge_cache_starts_empty(self):
        svc = CreatorKnowledgeService()
        assert len(svc._knowledge_cache) == 0


class TestCreatorKnowledgeRetrieval:
    """Test 2: happy path - Knowledge loads and is cached correctly."""

    def _create_profile_file(self, tmpdir):
        profile = {
            "name": "Stefan",
            "nickname": "Stef",
            "location": "Barcelona",
            "profession": ["yoga teacher", "coach"],
            "services": ["yoga classes", "retreats", "online courses"],
            "communication_style": {"tone": "warm", "energy": "high"},
            "values": ["health", "mindfulness"],
            "content_themes": ["yoga", "meditation", "travel"],
            "faqs": {
                "cuanto_dura": "La sesión dura 60 minutos",
                "precio": "Consulta la web",
            },
        }
        os.makedirs(tmpdir, exist_ok=True)
        profile_path = os.path.join(tmpdir, "stefan_profile.json")
        with open(profile_path, "w") as f:
            json.dump(profile, f)
        return profile_path

    def test_load_knowledge_returns_creator_knowledge(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._create_profile_file(tmpdir)
            svc = CreatorKnowledgeService(knowledge_dir=tmpdir)
            knowledge = svc.load_knowledge("c1")

        assert knowledge is not None
        assert knowledge.name == "Stefan"
        assert knowledge.nickname == "Stef"
        assert "yoga classes" in knowledge.services

    def test_load_knowledge_caches_result(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._create_profile_file(tmpdir)
            svc = CreatorKnowledgeService(knowledge_dir=tmpdir)
            k1 = svc.load_knowledge("c1")
            k2 = svc.load_knowledge("c1")

        assert k1 is k2  # Same object from cache

    def test_to_system_context_includes_name(self):
        knowledge = CreatorKnowledge(
            creator_id="c1",
            name="Stefan",
            nickname="Stef",
            location="Barcelona",
            profession=["yoga teacher"],
            services=["classes"],
            communication_style={},
            values=["health"],
            content_themes=["yoga"],
            faqs={},
        )
        context = knowledge.to_system_context()
        assert "Stefan" in context
        assert "Stef" in context
        assert "Barcelona" in context

    def test_get_relevant_info_services_query(self):
        knowledge = CreatorKnowledge(
            creator_id="c1",
            name="Stefan",
            nickname="Stef",
            location="Barcelona",
            profession=["coach"],
            services=["yoga classes", "retreats"],
            communication_style={},
            values=[],
            content_themes=[],
            faqs={},
        )
        info = knowledge.get_relevant_info("Que servicio ofreces?")
        assert "yoga classes" in info

    def test_get_context_for_message_combines_base_and_relevant(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._create_profile_file(tmpdir)
            svc = CreatorKnowledgeService(knowledge_dir=tmpdir)
            context = svc.get_context_for_message("c1", "Donde estas ubicado?")

        assert "Barcelona" in context
        assert "Stefan" in context


class TestCreatorKnowledgeEmpty:
    """Test 3: edge case - Empty or missing knowledge handled."""

    def test_get_relevant_info_no_match(self):
        knowledge = CreatorKnowledge(
            creator_id="c1",
            name="Stefan",
            nickname="Stef",
            location="Barcelona",
            profession=[],
            services=[],
            communication_style={},
            values=[],
            content_themes=[],
            faqs={},
        )
        info = knowledge.get_relevant_info("random unrelated question")
        assert info == ""

    def test_get_relevant_info_price_query(self):
        knowledge = CreatorKnowledge(
            creator_id="c1",
            name="Stefan",
            nickname="Stef",
            location="Barcelona",
            profession=[],
            services=[],
            communication_style={},
            values=[],
            content_themes=[],
            faqs={},
        )
        info = knowledge.get_relevant_info("Cuanto cuesta el curso?")
        assert "precios" in info.lower() or "contactar" in info.lower()

    def test_get_relevant_info_duration_from_faq(self):
        knowledge = CreatorKnowledge(
            creator_id="c1",
            name="Stefan",
            nickname="Stef",
            location="Barcelona",
            profession=[],
            services=[],
            communication_style={},
            values=[],
            content_themes=[],
            faqs={"cuanto_dura": "60 minutos"},
        )
        info = knowledge.get_relevant_info("Cuanto dura la sesión?")
        assert "60 minutos" in info

    def test_get_relevant_info_location_query(self):
        knowledge = CreatorKnowledge(
            creator_id="c1",
            name="Stefan",
            nickname="Stef",
            location="Madrid",
            profession=[],
            services=[],
            communication_style={},
            values=[],
            content_themes=[],
            faqs={},
        )
        info = knowledge.get_relevant_info("Donde estas?")
        assert "Madrid" in info

    def test_get_relevant_info_identity_query(self):
        knowledge = CreatorKnowledge(
            creator_id="c1",
            name="Stefan",
            nickname="Stef",
            location="Barcelona",
            profession=["yoga teacher", "life coach"],
            services=[],
            communication_style={},
            values=[],
            content_themes=[],
            faqs={},
        )
        info = knowledge.get_relevant_info("Quien eres?")
        assert "yoga teacher" in info


class TestCreatorKnowledgeFormat:
    """Test 4: error handling - Knowledge format and system context output."""

    def test_to_system_context_contains_rules(self):
        knowledge = CreatorKnowledge(
            creator_id="c1",
            name="Stefan",
            nickname="Stef",
            location="Barcelona",
            profession=["coach"],
            services=["retreats"],
            communication_style={},
            values=["mindfulness"],
            content_themes=["yoga"],
            faqs={},
        )
        ctx = knowledge.to_system_context()
        assert "REGLAS DE CONOCIMIENTO" in ctx
        assert "nunca inventes" in ctx.lower() or "Nunca inventes" in ctx

    def test_to_system_context_lists_services(self):
        knowledge = CreatorKnowledge(
            creator_id="c1",
            name="Test",
            nickname="T",
            location="X",
            profession=["a"],
            services=["service_a", "service_b"],
            communication_style={},
            values=["v1"],
            content_themes=["t1"],
            faqs={},
        )
        ctx = knowledge.to_system_context()
        assert "service_a" in ctx
        assert "service_b" in ctx

    def test_load_knowledge_missing_file_returns_none(self):
        svc = CreatorKnowledgeService(knowledge_dir="/nonexistent/path")
        result = svc.load_knowledge("c1")
        assert result is None

    def test_get_context_for_message_no_knowledge_returns_empty(self):
        svc = CreatorKnowledgeService(knowledge_dir="/nonexistent/path")
        result = svc.get_context_for_message("c1", "Hola")
        assert result == ""

    def test_load_knowledge_with_malformed_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "stefan_profile.json")
            with open(path, "w") as f:
                f.write("{invalid json")
            svc = CreatorKnowledgeService(knowledge_dir=tmpdir)
            result = svc.load_knowledge("c1")
        assert result is None


class TestCreatorNotFound:
    """Test 5: integration check - Full flow from load to context generation."""

    def test_full_flow_with_service_query(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            profile = {
                "name": "Ana",
                "nickname": "Anita",
                "location": "Madrid",
                "profession": ["nutritionist"],
                "services": ["meal plans", "consultations"],
                "communication_style": {"tone": "warm"},
                "values": ["health"],
                "content_themes": ["nutrition"],
                "faqs": {"horario": "Lunes a viernes de 9 a 17"},
            }
            os.makedirs(tmpdir, exist_ok=True)
            with open(os.path.join(tmpdir, "stefan_profile.json"), "w") as f:
                json.dump(profile, f)

            svc = CreatorKnowledgeService(knowledge_dir=tmpdir)
            ctx = svc.get_context_for_message("c1", "Que servicio ofreces?")

        assert "Ana" in ctx
        assert "meal plans" in ctx

    def test_full_flow_no_relevant_info(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            profile = {
                "name": "Ana",
                "nickname": "Anita",
                "location": "Madrid",
                "profession": ["nutritionist"],
                "services": ["meal plans"],
                "communication_style": {},
                "values": ["health"],
                "content_themes": ["nutrition"],
                "faqs": {},
            }
            os.makedirs(tmpdir, exist_ok=True)
            with open(os.path.join(tmpdir, "stefan_profile.json"), "w") as f:
                json.dump(profile, f)

            svc = CreatorKnowledgeService(knowledge_dir=tmpdir)
            ctx = svc.get_context_for_message("c1", "Hola")

        # Should still contain base context
        assert "Ana" in ctx
        # Should NOT contain "INFORMACIÓN RELEVANTE" section
        assert "RELEVANTE" not in ctx

    def test_cache_avoids_repeated_file_reads(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            profile = {
                "name": "Test",
                "nickname": "T",
                "location": "X",
                "profession": [],
                "services": [],
                "communication_style": {},
                "values": [],
                "content_themes": [],
                "faqs": {},
            }
            os.makedirs(tmpdir, exist_ok=True)
            with open(os.path.join(tmpdir, "stefan_profile.json"), "w") as f:
                json.dump(profile, f)

            svc = CreatorKnowledgeService(knowledge_dir=tmpdir)
            svc.load_knowledge("c1")

            # Now delete the file - cache should still work
            os.remove(os.path.join(tmpdir, "stefan_profile.json"))
            k2 = svc.load_knowledge("c1")
            assert k2 is not None
            assert k2.name == "Test"

    def test_multiple_creators_cached_independently(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            profile = {
                "name": "Creator",
                "nickname": "C",
                "location": "X",
                "profession": [],
                "services": [],
                "communication_style": {},
                "values": [],
                "content_themes": [],
                "faqs": {},
            }
            os.makedirs(tmpdir, exist_ok=True)
            with open(os.path.join(tmpdir, "stefan_profile.json"), "w") as f:
                json.dump(profile, f)

            svc = CreatorKnowledgeService(knowledge_dir=tmpdir)
            k1 = svc.load_knowledge("creator_a")
            k2 = svc.load_knowledge("creator_b")

        # Both load from same file but cached under different keys
        assert k1.creator_id == "creator_a"
        assert k2.creator_id == "creator_b"
        assert "creator_a" in svc._knowledge_cache
        assert "creator_b" in svc._knowledge_cache

    def test_faq_matching_via_word_overlap(self):
        knowledge = CreatorKnowledge(
            creator_id="c1",
            name="Stefan",
            nickname="Stef",
            location="Barcelona",
            profession=[],
            services=[],
            communication_style={},
            values=[],
            content_themes=[],
            faqs={"horario clases": "Martes y jueves a las 18h"},
        )
        info = knowledge.get_relevant_info("horario de las clases?")
        assert "18h" in info
