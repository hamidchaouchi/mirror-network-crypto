"""
╔══════════════════════════════════════════════════════════════════╗
║         محرك مرآة زيتا — نظام الذاكرة الحية (المُحسّن)          ║
║    MirrorZeta Living Memory System v2.1 (Production-Ready)       ║
╠══════════════════════════════════════════════════════════════════╣
║  المؤلف: Mirror Zeta Project                                     ║
║  الإصدار: 2.1.0                                                  ║
║  الترخيص: MIT                                                    ║
║  الحالة: جاهز للإنتاج ✅                                          ║
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
# إعداد نظام السجلات (Logging)
# ──────────────────────────────────────────────────────────────────

def setup_logger(name: str, log_file: Optional[str] = None, level=logging.INFO):
    """إعداد logger مخصص"""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger

logger = setup_logger(__name__, log_file="logs/mirror_zeta.log")

# محاولة تحميل المكتبات الاختيارية
try:
    from sentence_transformers import SentenceTransformer
    HAS_TRANSFORMERS = True
    logger.info("✅ تم تحميل SentenceTransformer بنجاح")
except ImportError:
    HAS_TRANSFORMERS = False
    logger.warning("⚠️ SentenceTransformer غير متوفر")

try:
    import faiss
    HAS_FAISS = True
    logger.info("✅ تم تحميل FAISS بنجاح")
except ImportError:
    HAS_FAISS = False
    logger.warning("⚠️ FAISS غير متوفر")

# ══════════════════════════════════════════════════════════════════
# 1. نماذج البيانات (Data Models)
# ══════════════════════════════════════════════════════════════════

@dataclass
class MemoryTrace:
    """تمثيل ذكرى واحدة"""
    content: str
    world_id: int
    emotion: str
    valence: float
    id: str = field(default_factory=lambda: str(int(time.time() * 1000)))
    timestamp: float = field(default_factory=time.time)
    strength: float = 1.0
    embedding: Optional[np.ndarray] = None
    related_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['embedding'] = self.embedding.tolist() if self.embedding is not None else None
        data['related_ids'] = json.dumps(self.related_ids)
        return data

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'MemoryTrace':
        data_copy = data.copy()
        data_copy['related_ids'] = json.loads(data_copy.get('related_ids', '[]'))
        if data_copy.get('embedding'):
            data_copy['embedding'] = np.array(data_copy['embedding'])
        return MemoryTrace(**data_copy)


# ══════════════════════════════════════════════════════════════════
# 2. طبقة التخزين الآمنة (Safe Storage Layer)
# ══════════════════════════════════════════════════════════════════

class MirrorStorage:
    """طبقة التخزين"""
    
    def __init__(self, db_path: str = "mirror_zeta_v2.db"):
        self.db_path = db_path
        self.conn = None
        self._connect()
        self._create_tables()

    def _connect(self):
        try:
            self.conn = sqlite3.connect(self.db_path, timeout=10.0)
            self.conn.row_factory = sqlite3.Row
            logger.info(f"✅ تم الاتصال بـ: {self.db_path}")
        except sqlite3.Error as e:
            logger.critical(f"❌ فشل الاتصال: {e}")
            raise

    def _create_tables(self):
        try:
            cursor = self.conn.cursor()
            
            cursor.execute('''CREATE TABLE IF NOT EXISTS episodic 
                             (id TEXT PRIMARY KEY, 
                              content TEXT NOT NULL, 
                              world_id INTEGER NOT NULL,
                              emotion TEXT NOT NULL, 
                              valence REAL NOT NULL, 
                              strength REAL NOT NULL, 
                              timestamp REAL NOT NULL, 
                              embedding BLOB,
                              related_ids TEXT DEFAULT '[]')''')
            
            cursor.execute('''CREATE TABLE IF NOT EXISTS relationships 
                             (id INTEGER PRIMARY KEY AUTOINCREMENT,
                              trace_id_1 TEXT NOT NULL, 
                              trace_id_2 TEXT NOT NULL, 
                              similarity REAL NOT NULL,
                              created_at REAL,
                              UNIQUE(trace_id_1, trace_id_2))''')
            
            cursor.execute('''CREATE INDEX IF NOT EXISTS idx_world_id 
                             ON episodic(world_id)''')
            cursor.execute('''CREATE INDEX IF NOT EXISTS idx_timestamp 
                             ON episodic(timestamp)''')
            
            self.conn.commit()
            logger.info("✅ تم إنشاء الجداول")
        except sqlite3.Error as e:
            logger.error(f"❌ خطأ في إنشاء الجداول: {e}")
            raise

    def save_trace(self, trace: MemoryTrace) -> bool:
        try:
            cursor = self.conn.cursor()
            emb_data = json.dumps(trace.embedding.tolist()) if trace.embedding is not None else None
            related_ids_json = json.dumps(trace.related_ids)
            
            cursor.execute("""INSERT OR REPLACE INTO episodic 
                             (id, content, world_id, emotion, valence, strength, timestamp, embedding, related_ids)
                             VALUES (?,?,?,?,?,?,?,?,?)""",
                          (trace.id, trace.content, trace.world_id, trace.emotion, 
                           trace.valence, trace.strength, trace.timestamp, emb_data, related_ids_json))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"❌ خطأ في حفظ الذكرى: {e}")
            return False

    def load_all_traces(self) -> List[MemoryTrace]:
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM episodic ORDER BY timestamp DESC")
            rows = cursor.fetchall()
            
            traces = []
            for r in rows:
                embedding = None
                if r['embedding']:
                    try:
                        embedding = np.array(json.loads(r['embedding']))
                    except:
                        pass
                
                trace = MemoryTrace(
                    id=r['id'],
                    content=r['content'],
                    world_id=r['world_id'],
                    emotion=r['emotion'],
                    valence=r['valence'],
                    strength=r['strength'],
                    timestamp=r['timestamp'],
                    embedding=embedding,
                    related_ids=json.loads(r['related_ids']) if r['related_ids'] else []
                )
                traces.append(trace)
            
            logger.info(f"✅ تم تحميل {len(traces)} ذكرى")
            return traces
        except sqlite3.Error as e:
            logger.error(f"❌ خطأ في تحميل الذكريات: {e}")
            return []

    def save_relationship(self, trace_id_1: str, trace_id_2: str, similarity: float) -> bool:
        try:
            cursor = self.conn.cursor()
            cursor.execute("""INSERT OR REPLACE INTO relationships 
                             (trace_id_1, trace_id_2, similarity, created_at)
                             VALUES (?,?,?,?)""",
                          (trace_id_1, trace_id_2, similarity, time.time()))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"❌ خطأ في حفظ العلاقة: {e}")
            return False

    def get_relationships(self, trace_id: str) -> List[Tuple[str, float]]:
        try:
            cursor = self.conn.cursor()
            cursor.execute("""SELECT trace_id_2, similarity FROM relationships 
                             WHERE trace_id_1 = ?
                             ORDER BY similarity DESC""", (trace_id,))
            return cursor.fetchall()
        except sqlite3.Error as e:
            logger.error(f"❌ خطأ في استرجاع العلاقات: {e}")
            return []

    def get_stats(self) -> Dict[str, Any]:
        try:
            cursor = self.conn.cursor()
            
            total = cursor.execute("SELECT COUNT(*) FROM episodic").fetchone()[0]
            by_world_rows = cursor.execute("SELECT world_id, COUNT(*) FROM episodic GROUP BY world_id").fetchall()
            by_world = dict(by_world_rows) if by_world_rows else {}
            avg_strength = cursor.execute("SELECT AVG(strength) FROM episodic").fetchone()[0] or 0
            
            return {
                "total_traces": total,
                "by_world": by_world,
                "average_strength": float(avg_strength)
            }
        except sqlite3.Error as e:
            logger.error(f"❌ خطأ في الإحصائيات: {e}")
            return {"total_traces": 0, "by_world": {}, "average_strength": 0}

    def close(self):
        if self.conn:
            try:
                self.conn.close()
                logger.info("✅ تم إغلاق الاتصال")
            except sqlite3.Error as e:
                logger.error(f"❌ خطأ في الإغلاق: {e}")


# ══════════════════════════════════════════════════════════════════
# 3. محرك البحث الدلالي الآمن
# ══════════════════════════════════════════════════════════════════

class SemanticSearchEngine:
    """محرك بحث دلالي"""
    
    def __init__(self, use_vector_search: bool = True, use_faiss: bool = True):
        self.encoder = None
        self.use_faiss = use_faiss and HAS_FAISS
        self.faiss_index = None
        self.trace_index_map = {}
        
        if HAS_TRANSFORMERS and use_vector_search:
            try:
                logger.info("🧠 جاري تحميل النموذج...")
                self.encoder = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
                logger.info("✅ تم تحميل النموذج")
            except Exception as e:
                logger.error(f"❌ فشل تحميل النموذج: {e}")
                self.encoder = None

    def encode(self, text: str) -> Optional[np.ndarray]:
        if not self.encoder:
            return None
        
        try:
            embedding = self.encoder.encode(text, convert_to_numpy=True)
            if embedding is None or len(embedding) == 0:
                return None
            return embedding
        except Exception as e:
            logger.error(f"❌ خطأ في الترميز: {e}")
            return None

    @staticmethod
    def safe_cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
        try:
            if vec_a is None or vec_b is None:
                return 0.0
            
            vec_a = np.array(vec_a, dtype=np.float32)
            vec_b = np.array(vec_b, dtype=np.float32)
            
            norm_a = np.linalg.norm(vec_a)
            norm_b = np.linalg.norm(vec_b)
            
            if norm_a < 1e-10 or norm_b < 1e-10:
                return 0.0
            
            similarity = np.dot(vec_a, vec_b) / (norm_a * norm_b)
            return float(np.clip(similarity, -1.0, 1.0))
        except Exception as e:
            logger.error(f"❌ خطأ في التشابه: {e}")
            return 0.0

    def build_faiss_index(self, traces: List['MemoryTrace']):
        if not self.use_faiss or not traces:
            return
        
        try:
            embeddings = []
            valid_indices = []
            
            for i, trace in enumerate(traces):
                if trace.embedding is not None:
                    embeddings.append(trace.embedding.astype(np.float32))
                    valid_indices.append(i)
                    self.trace_index_map[len(valid_indices) - 1] = trace.id
            
            if not embeddings:
                return
            
            embeddings_array = np.array(embeddings)
            embedding_dim = embeddings_array.shape[1]
            
            self.faiss_index = faiss.IndexFlatL2(embedding_dim)
            self.faiss_index.add(embeddings_array)
            logger.info(f"✅ تم بناء FAISS بـ {len(embeddings)} متجه")
        except Exception as e:
            logger.error(f"❌ خطأ في FAISS: {e}")
            self.faiss_index = None


# ══════════════════════════════════════════════════════════════════
# 4. المحرك الرئيسي (Main Engine)
# ══════════════════════════════════════════════════════════════════

class MirrorZetaCore:
    """المحرك الرئيسي"""
    
    VERSION = "2.1.0"
    
    def __init__(self, db_path: str = "mirror_zeta_v2.db", use_vector_search: bool = True):
        self.storage = MirrorStorage(db_path)
        self.search_engine = SemanticSearchEngine(use_vector_search=use_vector_search)
        self.traces = self.storage.load_all_traces()
        self.concepts = {}
        self.reflection_threshold = 0.75
        
        if self.search_engine.encoder and self.traces:
            self.search_engine.build_faiss_index(self.traces)
        
        logger.info(f"🚀 تم تهيئة MirrorZeta v{self.VERSION}")

    def experience(self, content: str, world_id: int, emotion: str, valence: float) -> Optional[str]:
        """تسجيل تجربة"""
        if not content or len(content.strip()) == 0:
            logger.error("❌ محتوى فارغ")
            return None
        
        if not -1.0 <= valence <= 1.0:
            valence = np.clip(valence, -1.0, 1.0)
        
        if world_id < 0:
            logger.error("❌ world_id سالب")
            return None
        
        embedding = None
        if self.search_engine.encoder:
            embedding = self.search_engine.encode(content)
        
        trace = MemoryTrace(
            content=content,
            world_id=world_id,
            emotion=emotion,
            valence=valence,
            embedding=embedding
        )
        
        if self.storage.save_trace(trace):
            self.traces.append(trace)
            logger.info(f"✨ تم تسجيل ذكرى في العالم [{world_id}]")
            return trace.id
        else:
            logger.error("❌ فشل الحفظ")
            return None

    def recall(self, query: str, limit: int = 3, world_id: Optional[int] = None) -> List[Tuple[MemoryTrace, float]]:
        """البحث"""
        if not self.traces:
            logger.warning("⚠️ لا توجد ذكريات")
            return []
        
        filtered_traces = [t for t in self.traces if world_id is None or t.world_id == world_id]
        
        if not filtered_traces:
            return []
        
        scored_traces = []
        
        if not self.search_engine.encoder:
            query_lower = query.lower()
            for trace in filtered_traces:
                if query_lower in trace.content.lower():
                    scored_traces.append((trace, 1.0))
                elif any(word in trace.content.lower() for word in query_lower.split()):
                    scored_traces.append((trace, 0.5))
        else:
            query_embedding = self.search_engine.encode(query)
            if query_embedding is None:
                return []
            
            for trace in filtered_traces:
                if trace.embedding is not None:
                    sim = self.search_engine.safe_cosine_similarity(query_embedding, trace.embedding)
                    emotional_factor = max(0, trace.valence)
                    final_score = (sim * 0.6) + (emotional_factor * 0.2) + (trace.strength * 0.2)
                    scored_traces.append((trace, final_score))
        
        scored_traces.sort(key=lambda x: x[1], reverse=True)
        result = scored_traces[:limit]
        
        logger.info(f"✅ تم استرجاع {len(result)} ذكريات")
        return result

    def reflect(self) -> Dict[str, Any]:
        """التأمل"""
        logger.info("🕯️ يبدأ التأمل...")
        
        if len(self.traces) < 2:
            return {"connections": 0, "relationships": []}
        
        relationships = []
        connection_count = 0
        
        try:
            for i, trace1 in enumerate(self.traces):
                if trace1.embedding is None:
                    continue
                
                for trace2 in self.traces[i+1:]:
                    if trace2.embedding is None:
                        continue
                    
                    similarity = self.search_engine.safe_cosine_similarity(
                        trace1.embedding, 
                        trace2.embedding
                    )
                    
                    if similarity >= self.reflection_threshold:
                        if self.storage.save_relationship(trace1.id, trace2.id, similarity):
                            trace1.strength = min(trace1.strength + 0.1, 1.5)
                            trace2.strength = min(trace2.strength + 0.1, 1.5)
                            
                            if trace2.id not in trace1.related_ids:
                                trace1.related_ids.append(trace2.id)
                            if trace1.id not in trace2.related_ids:
                                trace2.related_ids.append(trace1.id)
                            
                            self.storage.save_trace(trace1)
                            self.storage.save_trace(trace2)
                            
                            connection_count += 1
                            relationships.append({
                                "trace1": trace1.content[:50],
                                "trace2": trace2.content[:50],
                                "similarity": float(similarity)
                            })
        
        except Exception as e:
            logger.error(f"❌ خطأ في التأمل: {e}")
        
        logger.info(f"✨ تم اكتشاف {connection_count} اتصالات")
        return {
            "connections": connection_count,
            "relationships": relationships,
            "threshold_used": self.reflection_threshold
        }

    def get_trace_summary(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """ملخص الذكرة"""
        for trace in self.traces:
            if trace.id == trace_id:
                relationships = self.storage.get_relationships(trace_id)
                return {
                    "id": trace.id,
                    "content": trace.content,
                    "emotion": trace.emotion,
                    "valence": trace.valence,
                    "strength": trace.strength,
                    "world_id": trace.world_id,
                    "timestamp": trace.timestamp,
                    "related_count": len(trace.related_ids),
                    "relationships": [{"id": r[0], "similarity": r[1]} for r in relationships]
                }
        return None

    def get_world_summary(self, world_id: int) -> Dict[str, Any]:
        """ملخص العالم"""
        world_traces = [t for t in self.traces if t.world_id == world_id]
        
        if not world_traces:
            return {"world_id": world_id, "trace_count": 0, "emotions": []}
        
        emotions = [t.emotion for t in world_traces]
        valences = [t.valence for t in world_traces]
        
        return {
            "world_id": world_id,
            "trace_count": len(world_traces),
            "emotions": emotions,
            "average_valence": float(np.mean(valences)),
            "dominant_emotion": max(set(emotions), key=emotions.count),
            "traces": [{"content": t.content[:50], "emotion": t.emotion} for t in world_traces]
        }

    def get_system_status(self) -> Dict[str, Any]:
        """حالة النظام"""
        stats = self.storage.get_stats()
        return {
            "version": self.VERSION,
            "status": "online",
            "timestamp": datetime.now().isoformat(),
            "total_memories": len(self.traces),
            "database_stats": stats,
            "encoder_available": self.search_engine.encoder is not None,
            "faiss_available": self.search_engine.faiss_index is not None,
        }

    def cleanup(self):
        """تنظيف"""
        try:
            self.storage.close()
            logger.info("✅ تم التنظيف")
        except Exception as e:
            logger.error(f"❌ خطأ في التنظيف: {e}")


# ══════════════════════════════════════════════════════════════════
# 5. بيئة الاختبار والعرض التوضيحي
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n" + "="*70)
    print("🚀 محرك مرآة زيتا — نظام الذاكرة الحية v2.1")
    print("="*70 + "\n")
    
    logger.info("🚀 بدء التشغيل...")
    
    zeta = MirrorZetaCore()

    print("\n" + "="*70)
    print("📝 تسجيل التجارب")
    print("="*70 + "\n")

    experiences = [
        ("أشعر بحماس كبير لتعلم البرمجة العصبية", 7, "حماس", 0.9),
        ("هناك مشكلة تقنية معقدة", 11, "قلق", -0.3),
        ("نجحت في حل المعضلة", 13, "رضا", 0.8),
        ("الشعور بالفرح عند الفهم", 7, "فرح", 0.85),
        ("القلق من عدم الفهم", 11, "خوف", -0.7),
    ]

    for content, world_id, emotion, valence in experiences:
        zeta.experience(content, world_id, emotion, valence)
        print(f"✅ {content[:50]}...")

    print("\n" + "="*70)
    print("🔍 البحث الدلالي")
    print("="*70 + "\n")

    results = zeta.recall("حماس وشغف", limit=2)
    for i, (trace, score) in enumerate(results, 1):
        print(f"{i}. [{trace.emotion}] النقاط: {score:.2f}")

    print("\n" + "="*70)
    print("🕯️ التأمل")
    print("="*70 + "\n")

    reflection = zeta.reflect()
    print(f"الاتصالات: {reflection['connections']}")

    print("\n" + "="*70)
    print("✅ اكتمل!")
    print("="*70 + "\n")

    zeta.cleanup()