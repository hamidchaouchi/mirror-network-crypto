"""
╔══════════════════════════════════════════════════════════════════╗
║         محرك مرآة زيتا — نظام الذاكرة الحية v2.2               ║
║    MirrorZeta Living Memory System v2.2 (Fixed & Production)    ║
╚══════════════════════════════════════════════════════════════════╝
"""

import sqlite3
import json
import time
import logging
import numpy as np
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any, Tuple
from pathlib import Path
from enum import Enum
from datetime import datetime

# ──────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────

def setup_logger(name: str, log_file: Optional[str] = None, level=logging.INFO):
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(level)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    return logger

logger = setup_logger(__name__, log_file="logs/mirror_zeta.log")

# محاولة تحميل المكتبات الاختيارية
try:
    from sentence_transformers import SentenceTransformer
    HAS_TRANSFORMERS = True
    logger.info("✅ SentenceTransformer متوفر")
except ImportError:
    HAS_TRANSFORMERS = False
    logger.warning("⚠️  SentenceTransformer غير متوفر — سيُستخدم بحث نصي بسيط")
    logger.warning("     للتثبيت: pip install sentence-transformers")

try:
    import faiss
    HAS_FAISS = True
    logger.info("✅ FAISS متوفر")
except ImportError:
    HAS_FAISS = False
    logger.warning("⚠️  FAISS غير متوفر — سيُستخدم بحث خطي")
    logger.warning("     للتثبيت: pip install faiss-cpu")


# ══════════════════════════════════════════════════════════════════
# 1. نماذج البيانات
# ══════════════════════════════════════════════════════════════════

class EmotionType(Enum):
    JOY        = "فرح"
    SADNESS    = "حزن"
    ANGER      = "غضب"
    FEAR       = "خوف"
    EXCITEMENT = "حماس"
    CONTENTMENT= "رضا"
    ANXIETY    = "قلق"
    NEUTRAL    = "محايد"


@dataclass
class MemoryTrace:
    """تمثيل ذكرى واحدة مع كامل البيانات الوصفية"""
    content:     str
    world_id:    int
    emotion:     str
    valence:     float          # -1.0 (سلبي) إلى +1.0 (إيجابي)
    id:          str            = field(default_factory=lambda: str(int(time.time() * 1000)))
    timestamp:   float          = field(default_factory=time.time)
    strength:    float          = 1.0
    embedding:   Optional[np.ndarray] = None
    related_ids: List[str]      = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['embedding']   = self.embedding.tolist() if self.embedding is not None else None
        data['related_ids'] = json.dumps(self.related_ids)
        return data

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'MemoryTrace':
        data = dict(data)
        data['related_ids'] = json.loads(data.get('related_ids', '[]'))
        if data.get('embedding'):
            data['embedding'] = np.array(data['embedding'])
        else:
            data['embedding'] = None
        return MemoryTrace(**data)


# ══════════════════════════════════════════════════════════════════
# 2. طبقة التخزين
# ══════════════════════════════════════════════════════════════════

class MirrorStorage:
    """SQLite storage مع معالجة شاملة للأخطاء والفهرسة"""

    def __init__(self, db_path: str = "mirror_zeta.db"):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        self._connect()
        self._create_tables()

    def _connect(self):
        try:
            self.conn = sqlite3.connect(self.db_path, timeout=10.0, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            logger.info(f"✅ اتصال بقاعدة البيانات: {self.db_path}")
        except sqlite3.Error as e:
            logger.critical(f"❌ فشل الاتصال: {e}")
            raise

    def _create_tables(self):
        try:
            c = self.conn.cursor()
            c.executescript("""
                CREATE TABLE IF NOT EXISTS episodic (
                    id          TEXT PRIMARY KEY,
                    content     TEXT NOT NULL,
                    world_id    INTEGER NOT NULL,
                    emotion     TEXT NOT NULL,
                    valence     REAL NOT NULL,
                    strength    REAL NOT NULL DEFAULT 1.0,
                    timestamp   REAL NOT NULL,
                    embedding   TEXT,
                    related_ids TEXT DEFAULT '[]'
                );
                CREATE TABLE IF NOT EXISTS relationships (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    trace_id_1  TEXT NOT NULL,
                    trace_id_2  TEXT NOT NULL,
                    similarity  REAL NOT NULL,
                    created_at  REAL,
                    UNIQUE(trace_id_1, trace_id_2)
                );
                CREATE INDEX IF NOT EXISTS idx_world_id  ON episodic(world_id);
                CREATE INDEX IF NOT EXISTS idx_timestamp ON episodic(timestamp);
                CREATE INDEX IF NOT EXISTS idx_emotion   ON episodic(emotion);
            """)
            self.conn.commit()
            logger.info("✅ الجداول جاهزة")
        except sqlite3.Error as e:
            logger.error(f"❌ خطأ إنشاء الجداول: {e}")
            raise

    # ── CRUD ──────────────────────────────────────────────────────

    def save_trace(self, trace: MemoryTrace) -> bool:
        try:
            emb = json.dumps(trace.embedding.tolist()) if trace.embedding is not None else None
            self.conn.execute(
                """INSERT OR REPLACE INTO episodic
                   (id, content, world_id, emotion, valence, strength, timestamp, embedding, related_ids)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (trace.id, trace.content, trace.world_id, trace.emotion,
                 trace.valence, trace.strength, trace.timestamp,
                 emb, json.dumps(trace.related_ids))
            )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"❌ خطأ save_trace: {e}")
            return False

    def load_all_traces(self) -> List[MemoryTrace]:
        try:
            rows = self.conn.execute(
                "SELECT * FROM episodic ORDER BY timestamp DESC"
            ).fetchall()
            traces = []
            for r in rows:
                emb = np.array(json.loads(r['embedding'])) if r['embedding'] else None
                traces.append(MemoryTrace(
                    id=r['id'], content=r['content'], world_id=r['world_id'],
                    emotion=r['emotion'], valence=r['valence'], strength=r['strength'],
                    timestamp=r['timestamp'], embedding=emb,
                    related_ids=json.loads(r['related_ids'] or '[]')
                ))
            logger.info(f"✅ تم تحميل {len(traces)} ذكرى")
            return traces
        except sqlite3.Error as e:
            logger.error(f"❌ خطأ load_all_traces: {e}")
            return []

    def get_trace_by_id(self, trace_id: str) -> Optional[MemoryTrace]:
        try:
            row = self.conn.execute(
                "SELECT * FROM episodic WHERE id=?", (trace_id,)
            ).fetchone()
            if not row:
                return None
            emb = np.array(json.loads(row['embedding'])) if row['embedding'] else None
            return MemoryTrace(
                id=row['id'], content=row['content'], world_id=row['world_id'],
                emotion=row['emotion'], valence=row['valence'], strength=row['strength'],
                timestamp=row['timestamp'], embedding=emb,
                related_ids=json.loads(row['related_ids'] or '[]')
            )
        except sqlite3.Error as e:
            logger.error(f"❌ خطأ get_trace_by_id: {e}")
            return None

    def delete_trace(self, trace_id: str) -> bool:
        try:
            self.conn.execute("DELETE FROM episodic WHERE id=?", (trace_id,))
            self.conn.execute(
                "DELETE FROM relationships WHERE trace_id_1=? OR trace_id_2=?",
                (trace_id, trace_id)
            )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"❌ خطأ delete_trace: {e}")
            return False

    def save_relationship(self, id1: str, id2: str, similarity: float) -> bool:
        try:
            self.conn.execute(
                "INSERT OR REPLACE INTO relationships (trace_id_1, trace_id_2, similarity, created_at) VALUES (?,?,?,?)",
                (id1, id2, similarity, time.time())
            )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"❌ خطأ save_relationship: {e}")
            return False

    def get_relationships(self, trace_id: str) -> List[Tuple[str, float]]:
        try:
            rows = self.conn.execute(
                "SELECT trace_id_2, similarity FROM relationships WHERE trace_id_1=? ORDER BY similarity DESC",
                (trace_id,)
            ).fetchall()
            return [(r[0], r[1]) for r in rows]
        except sqlite3.Error as e:
            logger.error(f"❌ خطأ get_relationships: {e}")
            return []

    def get_stats(self) -> Dict[str, Any]:
        try:
            total      = self.conn.execute("SELECT COUNT(*) FROM episodic").fetchone()[0]
            by_world   = dict(self.conn.execute(
                "SELECT world_id, COUNT(*) FROM episodic GROUP BY world_id"
            ).fetchall())
            avg_str    = self.conn.execute("SELECT AVG(strength) FROM episodic").fetchone()[0] or 0.0
            rel_count  = self.conn.execute("SELECT COUNT(*) FROM relationships").fetchone()[0]
            return {
                "total_traces":     total,
                "by_world":         by_world,
                "average_strength": float(avg_str),
                "relationships":    rel_count,
            }
        except sqlite3.Error as e:
            logger.error(f"❌ خطأ get_stats: {e}")
            return {}

    def close(self):
        if self.conn:
            try:
                self.conn.close()
                logger.info("✅ تم إغلاق قاعدة البيانات")
            except sqlite3.Error as e:
                logger.error(f"❌ خطأ close: {e}")


# ══════════════════════════════════════════════════════════════════
# 3. محرك البحث الدلالي
# ══════════════════════════════════════════════════════════════════

class SemanticSearchEngine:
    """بحث دلالي بالمتجهات أو fallback نصي"""

    def __init__(self, use_vector_search: bool = True):
        self.encoder = None
        self.faiss_index = None
        self._index_map: Dict[int, str] = {}   # faiss_pos → trace.id

        if HAS_TRANSFORMERS and use_vector_search:
            try:
                logger.info("🧠 جاري تحميل نموذج اللغة...")
                self.encoder = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
                logger.info("✅ النموذج جاهز")
            except Exception as e:
                logger.error(f"❌ فشل تحميل النموذج: {e}")

        if not self.encoder:
            logger.warning("⚠️  وضع البحث النصي البسيط مفعّل")

    def encode(self, text: str) -> Optional[np.ndarray]:
        if not self.encoder:
            return None
        try:
            return self.encoder.encode(text, convert_to_numpy=True).astype(np.float32)
        except Exception as e:
            logger.error(f"❌ خطأ encode: {e}")
            return None

    @staticmethod
    def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        try:
            if a is None or b is None:
                return 0.0
            a = np.asarray(a, dtype=np.float32)
            b = np.asarray(b, dtype=np.float32)
            na, nb = np.linalg.norm(a), np.linalg.norm(b)
            if na < 1e-10 or nb < 1e-10:
                return 0.0
            return float(np.clip(np.dot(a, b) / (na * nb), -1.0, 1.0))
        except Exception as e:
            logger.error(f"❌ خطأ cosine: {e}")
            return 0.0

    def build_faiss_index(self, traces: List[MemoryTrace]):
        if not HAS_FAISS:
            return
        embeddings, ids = [], []
        for t in traces:
            if t.embedding is not None:
                embeddings.append(t.embedding.astype(np.float32))
                ids.append(t.id)
        if not embeddings:
            return
        arr = np.array(embeddings)
        self.faiss_index = faiss.IndexFlatL2(arr.shape[1])
        self.faiss_index.add(arr)
        self._index_map = {i: tid for i, tid in enumerate(ids)}
        logger.info(f"✅ FAISS index بـ {len(embeddings)} متجه")

    def text_score(self, query: str, content: str) -> float:
        """تشابه نصي بسيط عند غياب النموذج"""
        q_words = set(query.lower().split())
        c_words = set(content.lower().split())
        if not q_words:
            return 0.0
        overlap = len(q_words & c_words)
        return overlap / len(q_words)


# ══════════════════════════════════════════════════════════════════
# 4. المحرك الرئيسي
# ══════════════════════════════════════════════════════════════════

class MirrorZetaCore:
    """المحرك الرئيسي لنظام الذاكرة الحية"""

    VERSION = "2.2.0"

    def __init__(self, db_path: str = "mirror_zeta.db", use_vector_search: bool = True):
        self.storage       = MirrorStorage(db_path)
        self.search_engine = SemanticSearchEngine(use_vector_search)
        self.traces: List[MemoryTrace] = self.storage.load_all_traces()
        self.reflection_threshold = 0.75

        # بناء فهرس FAISS من الذكريات المحفوظة
        if self.search_engine.encoder and self.traces:
            self.search_engine.build_faiss_index(self.traces)

        logger.info(f"🚀 MirrorZeta v{self.VERSION} — {len(self.traces)} ذكرى محملة")

    # ── experience ────────────────────────────────────────────────

    def experience(
        self,
        content: str,
        world_id: int,
        emotion: str,
        valence: float,
    ) -> Optional[str]:
        """تسجيل تجربة / ذكرى جديدة. يُعيد trace.id أو None عند الفشل."""
        if not content or not content.strip():
            logger.error("❌ المحتوى فارغ")
            return None
        if world_id < 0:
            logger.error(f"❌ world_id سالب: {world_id}")
            return None
        valence = float(np.clip(valence, -1.0, 1.0))

        embedding = self.search_engine.encode(content)

        trace = MemoryTrace(
            content=content,
            world_id=world_id,
            emotion=emotion,
            valence=valence,
            embedding=embedding,
        )

        if self.storage.save_trace(trace):
            self.traces.append(trace)
            # تحديث فهرس FAISS إن وُجد
            if embedding is not None and HAS_FAISS and self.search_engine.faiss_index:
                arr = embedding.reshape(1, -1)
                pos = self.search_engine.faiss_index.ntotal
                self.search_engine.faiss_index.add(arr)
                self.search_engine._index_map[pos] = trace.id
            logger.info(f"✨ ذكرى جديدة [{world_id}]: {content[:50]}")
            return trace.id

        logger.error("❌ فشل حفظ الذكرى")
        return None

    # ── recall ────────────────────────────────────────────────────

    def recall(
        self,
        query: str,
        limit: int = 5,
        world_id: Optional[int] = None,
        min_score: float = 0.0,
    ) -> List[Tuple[MemoryTrace, float]]:
        """البحث عن ذكريات مشابهة للاستعلام."""
        pool = [t for t in self.traces if world_id is None or t.world_id == world_id]
        if not pool:
            return []

        results: List[Tuple[MemoryTrace, float]] = []

        if self.search_engine.encoder:
            q_emb = self.search_engine.encode(query)
            if q_emb is None:
                return []
            for t in pool:
                if t.embedding is None:
                    continue
                sim   = self.search_engine.cosine_similarity(q_emb, t.embedding)
                bonus = max(0.0, t.valence) * 0.15 + (t.strength - 1.0) * 0.05
                score = sim * 0.80 + bonus
                if score >= min_score:
                    results.append((t, score))
        else:
            # بحث نصي بسيط
            for t in pool:
                score = self.search_engine.text_score(query, t.content)
                if score >= min_score:
                    results.append((t, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    # ── reflect ───────────────────────────────────────────────────

    def reflect(self) -> Dict[str, Any]:
        """ربط الذكريات المتشابهة وتقوية الروابط بينها."""
        logger.info("🕯️  بدء التأمل...")
        if len(self.traces) < 2:
            return {"connections": 0, "relationships": []}

        connections  = 0
        relationships: List[Dict] = []

        for i, t1 in enumerate(self.traces):
            if t1.embedding is None:
                continue
            for t2 in self.traces[i + 1:]:
                if t2.embedding is None:
                    continue
                sim = self.search_engine.cosine_similarity(t1.embedding, t2.embedding)
                if sim >= self.reflection_threshold:
                    self.storage.save_relationship(t1.id, t2.id, sim)
                    t1.strength = min(t1.strength + 0.1, 2.0)
                    t2.strength = min(t2.strength + 0.1, 2.0)
                    if t2.id not in t1.related_ids:
                        t1.related_ids.append(t2.id)
                    if t1.id not in t2.related_ids:
                        t2.related_ids.append(t1.id)
                    self.storage.save_trace(t1)
                    self.storage.save_trace(t2)
                    connections += 1
                    relationships.append({
                        "trace1":     t1.content[:60],
                        "trace2":     t2.content[:60],
                        "similarity": round(float(sim), 4),
                    })

        logger.info(f"✨ التأمل: {connections} اتصال")
        return {
            "connections":  connections,
            "relationships": relationships,
            "threshold":     self.reflection_threshold,
        }

    # ── helpers ───────────────────────────────────────────────────

    def get_world_summary(self, world_id: int) -> Dict[str, Any]:
        world_traces = [t for t in self.traces if t.world_id == world_id]
        if not world_traces:
            return {"world_id": world_id, "trace_count": 0}
        emotions = [t.emotion for t in world_traces]
        valences = [t.valence for t in world_traces]
        return {
            "world_id":         world_id,
            "trace_count":      len(world_traces),
            "emotions":         emotions,
            "average_valence":  round(float(np.mean(valences)), 3),
            "dominant_emotion": max(set(emotions), key=emotions.count),
            "traces": [{"id": t.id, "content": t.content[:60], "emotion": t.emotion}
                       for t in world_traces],
        }

    def get_trace_summary(self, trace_id: str) -> Optional[Dict[str, Any]]:
        trace = next((t for t in self.traces if t.id == trace_id), None)
        if not trace:
            return None
        rels = self.storage.get_relationships(trace_id)
        return {
            "id":            trace.id,
            "content":       trace.content,
            "emotion":       trace.emotion,
            "valence":       trace.valence,
            "strength":      trace.strength,
            "world_id":      trace.world_id,
            "timestamp":     trace.timestamp,
            "related_count": len(trace.related_ids),
            "relationships": [{"id": r[0], "similarity": r[1]} for r in rels],
        }

    def get_system_status(self) -> Dict[str, Any]:
        stats = self.storage.get_stats()
        return {
            "version":           self.VERSION,
            "status":            "online",
            "timestamp":         datetime.now().isoformat(),
            "in_memory_traces":  len(self.traces),   # FIX: عدد دقيق
            "database_stats":    stats,
            "vector_search":     self.search_engine.encoder is not None,
            "faiss_index":       self.search_engine.faiss_index is not None,
        }

    def cleanup(self):
        try:
            self.storage.close()
            logger.info("✅ تم تنظيف الموارد")
        except Exception as e:
            logger.error(f"❌ خطأ cleanup: {e}")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.cleanup()
