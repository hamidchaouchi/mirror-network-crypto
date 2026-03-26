"""
tests/test_mirror_zeta.py — اختبارات شاملة بـ pytest
تشغيل: pytest tests/ -v
"""
import pytest
import time
import numpy as np
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from mirror_zeta import MirrorZetaCore, MirrorStorage, SemanticSearchEngine, MemoryTrace


# ══════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════

@pytest.fixture
def storage():
    """Storage في الذاكرة (لا يترك ملفات)"""
    s = MirrorStorage(":memory:")
    yield s
    s.close()


@pytest.fixture
def engine():
    """MirrorZetaCore في الذاكرة بدون نموذج لغوي (للسرعة)"""
    z = MirrorZetaCore(db_path=":memory:", use_vector_search=False)
    yield z
    z.cleanup()


@pytest.fixture
def sample_trace():
    return MemoryTrace(
        content="تجربة اختبارية",
        world_id=1,
        emotion="محايد",
        valence=0.0,
    )


# ══════════════════════════════════════════════════════════════════
# اختبارات MemoryTrace
# ══════════════════════════════════════════════════════════════════

class TestMemoryTrace:
    def test_default_id_generated(self):
        t = MemoryTrace(content="test", world_id=1, emotion="محايد", valence=0.0)
        assert t.id is not None and len(t.id) > 0

    def test_default_timestamp(self):
        before = time.time()
        t = MemoryTrace(content="test", world_id=1, emotion="محايد", valence=0.0)
        after = time.time()
        assert before <= t.timestamp <= after

    def test_default_strength(self):
        t = MemoryTrace(content="test", world_id=1, emotion="محايد", valence=0.0)
        assert t.strength == 1.0

    def test_to_dict_has_all_keys(self, sample_trace):
        d = sample_trace.to_dict()
        for key in ['id', 'content', 'world_id', 'emotion', 'valence', 'strength', 'timestamp', 'embedding', 'related_ids']:
            assert key in d

    def test_embedding_serialization(self):
        t = MemoryTrace(content="test", world_id=1, emotion="محايد", valence=0.0,
                        embedding=np.array([0.1, 0.2, 0.3]))
        d = t.to_dict()
        assert d['embedding'] == [0.1, 0.2, 0.3]

    def test_no_embedding_is_none(self, sample_trace):
        d = sample_trace.to_dict()
        assert d['embedding'] is None

    def test_related_ids_serialized_as_json(self, sample_trace):
        sample_trace.related_ids = ['a', 'b']
        d = sample_trace.to_dict()
        import json
        assert json.loads(d['related_ids']) == ['a', 'b']


# ══════════════════════════════════════════════════════════════════
# اختبارات MirrorStorage
# ══════════════════════════════════════════════════════════════════

class TestMirrorStorage:
    def test_save_and_load(self, storage, sample_trace):
        assert storage.save_trace(sample_trace)
        loaded = storage.load_all_traces()
        assert len(loaded) == 1
        assert loaded[0].content == sample_trace.content

    def test_load_empty(self, storage):
        assert storage.load_all_traces() == []

    def test_get_by_id(self, storage, sample_trace):
        storage.save_trace(sample_trace)
        t = storage.get_trace_by_id(sample_trace.id)
        assert t is not None
        assert t.id == sample_trace.id

    def test_get_by_id_not_found(self, storage):
        assert storage.get_trace_by_id("nonexistent") is None

    def test_delete_trace(self, storage, sample_trace):
        storage.save_trace(sample_trace)
        assert storage.delete_trace(sample_trace.id)
        assert storage.get_trace_by_id(sample_trace.id) is None

    def test_save_relationship(self, storage):
        t1 = MemoryTrace(content="a", world_id=1, emotion="محايد", valence=0.0)
        t2 = MemoryTrace(content="b", world_id=1, emotion="محايد", valence=0.0)
        storage.save_trace(t1)
        storage.save_trace(t2)
        assert storage.save_relationship(t1.id, t2.id, 0.9)
        rels = storage.get_relationships(t1.id)
        assert len(rels) == 1
        assert abs(rels[0][1] - 0.9) < 1e-6

    def test_stats_count(self):
        s = MirrorStorage(":memory:")
        for i in range(3):
            s.save_trace(MemoryTrace(
                content=f"ذكرى {i}", world_id=i % 2,
                emotion="محايد", valence=0.0
            ))
        stats = s.get_stats()
        s.close()
        assert stats['total_traces'] == 3

    def test_stats_by_world(self):
        s = MirrorStorage(":memory:")
        s.save_trace(MemoryTrace(content="a", world_id=1, emotion="محايد", valence=0.0))
        s.save_trace(MemoryTrace(content="b", world_id=1, emotion="محايد", valence=0.0))
        s.save_trace(MemoryTrace(content="c", world_id=2, emotion="محايد", valence=0.0))
        stats = s.get_stats()
        s.close()
        assert stats['by_world'][1] == 2
        assert stats['by_world'][2] == 1

    def test_embedding_round_trip(self, storage):
        emb = np.array([0.1, 0.5, 0.9], dtype=np.float32)
        t = MemoryTrace(content="vec test", world_id=1, emotion="محايد", valence=0.0, embedding=emb)
        storage.save_trace(t)
        loaded = storage.load_all_traces()[0]
        assert loaded.embedding is not None
        np.testing.assert_allclose(loaded.embedding, emb, rtol=1e-5)

    def test_upsert_replaces(self, storage, sample_trace):
        storage.save_trace(sample_trace)
        sample_trace.strength = 1.5
        storage.save_trace(sample_trace)
        traces = storage.load_all_traces()
        assert len(traces) == 1
        assert traces[0].strength == 1.5


# ══════════════════════════════════════════════════════════════════
# اختبارات SemanticSearchEngine
# ══════════════════════════════════════════════════════════════════

class TestSemanticSearchEngine:
    def test_cosine_identical(self):
        v = np.array([1.0, 0.0, 0.0])
        assert SemanticSearchEngine.cosine_similarity(v, v) == pytest.approx(1.0)

    def test_cosine_orthogonal(self):
        a = np.array([1.0, 0.0])
        b = np.array([0.0, 1.0])
        assert SemanticSearchEngine.cosine_similarity(a, b) == pytest.approx(0.0)

    def test_cosine_opposite(self):
        a = np.array([1.0, 0.0])
        b = np.array([-1.0, 0.0])
        assert SemanticSearchEngine.cosine_similarity(a, b) == pytest.approx(-1.0)

    def test_cosine_none_returns_zero(self):
        assert SemanticSearchEngine.cosine_similarity(None, np.array([1.0])) == 0.0
        assert SemanticSearchEngine.cosine_similarity(np.array([1.0]), None) == 0.0

    def test_cosine_zero_vector(self):
        z = np.array([0.0, 0.0])
        v = np.array([1.0, 0.0])
        assert SemanticSearchEngine.cosine_similarity(z, v) == 0.0

    def test_text_score_exact(self):
        eng = SemanticSearchEngine(use_vector_search=False)
        assert eng.text_score("hello world", "hello world") == pytest.approx(1.0)

    def test_text_score_partial(self):
        eng = SemanticSearchEngine(use_vector_search=False)
        score = eng.text_score("hello world", "hello there")
        assert 0.0 < score < 1.0

    def test_text_score_no_match(self):
        eng = SemanticSearchEngine(use_vector_search=False)
        assert eng.text_score("xyz", "abc") == pytest.approx(0.0)

    def test_encode_without_model_returns_none(self):
        eng = SemanticSearchEngine(use_vector_search=False)
        assert eng.encode("test") is None


# ══════════════════════════════════════════════════════════════════
# اختبارات MirrorZetaCore — التكامل
# ══════════════════════════════════════════════════════════════════

class TestMirrorZetaCore:
    def test_experience_returns_id(self, engine):
        tid = engine.experience("نص اختبار", 1, "محايد", 0.0)
        assert tid is not None

    def test_experience_empty_content_returns_none(self, engine):
        assert engine.experience("", 1, "محايد", 0.0) is None
        assert engine.experience("   ", 1, "محايد", 0.0) is None

    def test_experience_negative_world_id_returns_none(self, engine):
        assert engine.experience("نص", -1, "محايد", 0.0) is None

    def test_experience_valence_clamped(self, engine):
        tid = engine.experience("نص", 1, "محايد", 5.0)
        assert tid is not None
        trace = next(t for t in engine.traces if t.id == tid)
        assert trace.valence <= 1.0

        tid2 = engine.experience("نص", 1, "محايد", -5.0)
        assert tid2 is not None
        trace2 = next(t for t in engine.traces if t.id == tid2)
        assert trace2.valence >= -1.0

    def test_experience_zero_world_id_valid(self, engine):
        tid = engine.experience("نص", 0, "محايد", 0.0)
        assert tid is not None

    def test_in_memory_count_matches_db(self, engine):
        for i in range(4):
            engine.experience(f"ذكرى {i}", 1, "محايد", 0.0)
        status = engine.get_system_status()
        assert status['in_memory_traces'] == status['database_stats']['total_traces']

    def test_recall_returns_results(self, engine):
        engine.experience("حماس للتعلم", 1, "حماس", 0.9)
        engine.experience("قلق وتوتر", 2, "قلق", -0.5)
        results = engine.recall("حماس", limit=5)
        assert isinstance(results, list)

    def test_recall_empty_traces_returns_empty(self, engine):
        assert engine.recall("أي شيء") == []

    def test_recall_world_filter(self, engine):
        engine.experience("ذكرى عالم 1", 1, "محايد", 0.0)
        engine.experience("ذكرى عالم 2", 2, "محايد", 0.0)
        results = engine.recall("ذكرى", world_id=1)
        assert all(t.world_id == 1 for t, _ in results)

    def test_recall_limit_respected(self, engine):
        for i in range(10):
            engine.experience(f"ذكرى رقم {i}", 1, "محايد", 0.0)
        results = engine.recall("ذكرى", limit=3)
        assert len(results) <= 3

    def test_reflect_empty_returns_zero(self, engine):
        r = engine.reflect()
        assert r['connections'] == 0

    def test_reflect_single_trace(self, engine):
        engine.experience("ذكرى وحيدة", 1, "محايد", 0.0)
        r = engine.reflect()
        assert r['connections'] == 0

    def test_get_world_summary_empty(self, engine):
        s = engine.get_world_summary(999)
        assert s['trace_count'] == 0

    def test_get_world_summary_correct_count(self, engine):
        engine.experience("أولى", 5, "فرح", 0.8)
        engine.experience("ثانية", 5, "حماس", 0.9)
        s = engine.get_world_summary(5)
        assert s['trace_count'] == 2
        assert s['world_id'] == 5

    def test_get_world_summary_average_valence(self, engine):
        engine.experience("إيجابية", 3, "فرح", 0.8)
        engine.experience("سلبية", 3, "حزن", -0.4)
        s = engine.get_world_summary(3)
        assert s['average_valence'] == pytest.approx(0.2, abs=0.01)

    def test_get_trace_summary_found(self, engine):
        tid = engine.experience("ذكرى للاختبار", 1, "فرح", 0.7)
        s = engine.get_trace_summary(tid)
        assert s is not None
        assert s['id'] == tid

    def test_get_trace_summary_not_found(self, engine):
        assert engine.get_trace_summary("ghost_id") is None

    def test_get_system_status_fields(self, engine):
        engine.experience("نص", 1, "محايد", 0.0)
        s = engine.get_system_status()
        for key in ['version', 'status', 'in_memory_traces', 'database_stats']:
            assert key in s
        assert s['status'] == 'online'

    def test_context_manager(self):
        with MirrorZetaCore(db_path=":memory:", use_vector_search=False) as z:
            tid = z.experience("اختبار context manager", 1, "محايد", 0.0)
            assert tid is not None
        # بعد الخروج يجب أن يعمل بدون استثناء

    def test_reflect_strengthens_related_traces(self):
        """التأمل يرفع strength للذكريات المترابطة (يحتاج embeddings حقيقية)"""
        z = MirrorZetaCore(db_path=":memory:", use_vector_search=False)
        # حقن embeddings متشابهة يدوياً
        t1 = MemoryTrace(content="test1", world_id=1, emotion="محايد", valence=0.0,
                         embedding=np.array([1.0, 0.0, 0.0]))
        t2 = MemoryTrace(content="test2", world_id=1, emotion="محايد", valence=0.0,
                         embedding=np.array([0.99, 0.14, 0.0]))
        z.storage.save_trace(t1)
        z.storage.save_trace(t2)
        z.traces = [t1, t2]
        z.reflection_threshold = 0.9

        r = z.reflect()
        assert r['connections'] >= 1
        assert t1.strength > 1.0
        assert t2.strength > 1.0
        z.cleanup()
