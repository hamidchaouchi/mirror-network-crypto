"""
╔══════════════════════════════════════════════════════════════════╗
║         محرك مرآة زيتا — نظام الذاكرة الحية                    ║
║         MirrorZeta Living Memory System v1.0                    ║
╠══════════════════════════════════════════════════════════════════╣
║  طبقات الذاكرة:                                                  ║
║  ├── EpisodicMemory   — أحداث وتفاعلات (قصيرة + طويلة المدى)   ║
║  ├── SemanticMemory   — معاني ومفاهيم مرتبطة بعوالم زيتا        ║
║  ├── ProceduralMemory — مهارات وأنماط إجرائية                   ║
║  └── EmotionalMemory  — السياق العاطفي لكل عالم                 ║
╠══════════════════════════════════════════════════════════════════╣
║  قابلية التوسع (Plugin Architecture):                           ║
║  ├── WorldRegistry    — إضافة عوالم جديدة ديناميكياً            ║
║  ├── StorageBackend   — SQLite الآن، أي DB مستقبلاً             ║
║  └── MemoryHook       — ربط LLM أو قاعدة بيانات خارجية         ║
╚══════════════════════════════════════════════════════════════════╝

المؤلف: Mirror Zeta Project
الترخيص: MIT
"""

from __future__ import annotations

import json
import math
import sqlite3
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn

# ══════════════════════════════════════════════════════════════════
#  الثوابت والأنواع الأساسية
# ══════════════════════════════════════════════════════════════════

WORLDS_DEFAULT = [7, 11, 13, 17, 19, 23, 29, 31]
K_SYNC         = 8.366
H_ALPHA        = 1.889
LEARNING_RATE  = 0.005
NOISE_STD      = 0.02

# خريطة العواطف لكل عالم (قابلة للتعديل والتوسع)
WORLD_EMOTION_MAP: Dict[int, str] = {
    7:  "فضول",
    11: "ثقة",
    13: "تحليل",
    17: "إبداع",
    19: "هدوء",
    23: "يقظة",
    29: "حماس",
    31: "حكمة",
}


class MemoryType(Enum):
    EPISODIC   = "episodic"    # أحداث وتفاعلات
    SEMANTIC   = "semantic"    # معاني ومفاهيم
    PROCEDURAL = "procedural"  # مهارات وأنماط
    EMOTIONAL  = "emotional"   # سياق عاطفي


class MemoryStrength(Enum):
    WEAK   = 0.2   # ذاكرة ضعيفة — ستتلاشى
    MEDIUM = 0.5   # ذاكرة متوسطة
    STRONG = 0.8   # ذاكرة قوية
    CORE   = 1.0   # ذاكرة جوهرية — لا تُمحى


# ══════════════════════════════════════════════════════════════════
#  هياكل البيانات الأساسية
# ══════════════════════════════════════════════════════════════════

@dataclass
class MemoryTrace:
    """
    أثر ذاكرة واحد — الوحدة الأساسية لكل ذكرى.

    الحقول
    ------
    id          : معرّف فريد
    type        : نوع الذاكرة (episodic/semantic/procedural/emotional)
    content     : المحتوى (نص أو بيانات)
    world_id    : العالم المرتبط (7..31)
    strength    : قوة الذاكرة (0.0 → 1.0)
    emotion     : المشاعر المرتبطة
    timestamp   : وقت الإنشاء
    access_count: عدد مرات الاسترجاع
    decay_rate  : معدل التلاشي (يُعاد حسابه تلقائياً)
    metadata    : بيانات إضافية (مرنة)
    """
    id          : str            = field(default_factory=lambda: str(uuid.uuid4())[:8])
    type        : MemoryType     = MemoryType.EPISODIC
    content     : str            = ""
    world_id    : int            = 7
    strength    : float          = 0.5
    emotion     : str            = ""
    timestamp   : float          = field(default_factory=time.time)
    access_count: int            = 0
    decay_rate  : float          = 0.01
    metadata    : Dict[str, Any] = field(default_factory=dict)

    def is_alive(self) -> bool:
        """هل الذاكرة لا تزال حية (قوتها > 0.05)?"""
        return self.current_strength() > 0.05

    def current_strength(self) -> float:
        """القوة الحالية بعد التلاشي الزمني."""
        age = (time.time() - self.timestamp) / 3600  # بالساعات
        decayed = self.strength * math.exp(-self.decay_rate * age)
        return max(0.0, min(1.0, decayed))

    def reinforce(self, boost: float = 0.1) -> None:
        """تعزيز الذاكرة عند استرجاعها (تأثير التكرار)."""
        self.strength  = min(1.0, self.strength + boost)
        self.access_count += 1
        # كلما تكررت، قلّ معدل تلاشيها
        self.decay_rate = max(0.001, self.decay_rate * 0.95)

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["type"] = self.type.value
        return d

    @classmethod
    def from_dict(cls, d: Dict) -> "MemoryTrace":
        d = d.copy()
        d["type"] = MemoryType(d["type"])
        return cls(**d)


@dataclass
class WorldState:
    """
    الحالة الكاملة لعالم زيتا — الوزن + الذاكرة + العاطفة.
    """
    world_id      : int
    weight        : float
    emotion       : str
    neuron_count  : int   = 0
    activation_pct: float = 0.0
    memory_load   : int   = 0   # عدد الذكريات المرتبطة
    last_active   : float = field(default_factory=time.time)


# ══════════════════════════════════════════════════════════════════
#  Plugin Architecture — قابلية التوسع
# ══════════════════════════════════════════════════════════════════

class StorageBackend(ABC):
    """
    واجهة التخزين المجردة.
    استبدلها بـ PostgreSQL أو Redis مستقبلاً دون تغيير الكود.
    """

    @abstractmethod
    def save(self, trace: MemoryTrace) -> None: ...

    @abstractmethod
    def load_all(self) -> List[MemoryTrace]: ...

    @abstractmethod
    def delete(self, trace_id: str) -> None: ...

    @abstractmethod
    def update(self, trace: MemoryTrace) -> None: ...


class MemoryHook(ABC):
    """
    خطاف يُشغَّل عند كل عملية ذاكرة.
    استخدمه لربط LLM أو قاعدة بيانات خارجية أو تسجيل حدث.
    """

    @abstractmethod
    def on_store(self, trace: MemoryTrace) -> None: ...

    @abstractmethod
    def on_recall(self, traces: List[MemoryTrace], query: str) -> List[MemoryTrace]: ...

    @abstractmethod
    def on_forget(self, trace: MemoryTrace) -> None: ...


class WorldRegistry:
    """
    سجل العوالم — يتيح إضافة عوالم جديدة ديناميكياً دون إعادة بناء النموذج.

    مثال
    ----
    registry = WorldRegistry()
    registry.register_world(37, emotion="اندهاش", description="عالم المفاجآت")
    """

    def __init__(self):
        self._worlds: Dict[int, Dict] = {
            w: {"emotion": WORLD_EMOTION_MAP[w], "description": "", "active": True}
            for w in WORLDS_DEFAULT
        }

    def register_world(
        self,
        world_id: int,
        emotion: str = "محايد",
        description: str = "",
    ) -> None:
        """إضافة عالم جديد (يجب أن يكون عدداً أولياً للاتساق المفاهيمي)."""
        if world_id in self._worlds:
            raise ValueError(f"العالم {world_id} موجود بالفعل.")
        self._worlds[world_id] = {
            "emotion": emotion,
            "description": description,
            "active": True,
        }

    def deactivate_world(self, world_id: int) -> None:
        """تعطيل عالم مؤقتاً (لا يُحذف — البيانات محفوظة)."""
        if world_id not in self._worlds:
            raise KeyError(f"العالم {world_id} غير موجود.")
        self._worlds[world_id]["active"] = False

    def active_worlds(self) -> List[int]:
        return [w for w, info in self._worlds.items() if info["active"]]

    def get_emotion(self, world_id: int) -> str:
        return self._worlds.get(world_id, {}).get("emotion", "محايد")

    def to_tensor(self) -> torch.Tensor:
        return torch.tensor(self.active_worlds(), dtype=torch.float32)

    def __repr__(self) -> str:
        lines = ["WorldRegistry:"]
        for wid, info in sorted(self._worlds.items()):
            status = "✅" if info["active"] else "⏸️"
            lines.append(f"  {status} {wid:3d} — {info['emotion']}")
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
#  طبقات الذاكرة
# ══════════════════════════════════════════════════════════════════

class EpisodicMemory:
    """
    ذاكرة الأحداث — تسجّل كل تفاعل مع طابع زمني وعالم مرتبط.

    الحد الأقصى الافتراضي 10,000 ذكرى — بعدها تُحذف الأضعف.
    """

    MAX_TRACES = 10_000

    def __init__(self):
        self._traces: List[MemoryTrace] = []

    def record(
        self,
        content: str,
        world_id: int,
        emotion: str = "",
        strength: float = 0.5,
        metadata: Optional[Dict] = None,
    ) -> MemoryTrace:
        trace = MemoryTrace(
            type      = MemoryType.EPISODIC,
            content   = content,
            world_id  = world_id,
            emotion   = emotion or WORLD_EMOTION_MAP.get(world_id, "محايد"),
            strength  = strength,
            metadata  = metadata or {},
        )
        self._traces.append(trace)
        if len(self._traces) > self.MAX_TRACES:
            self._prune()
        return trace

    def recall_recent(self, n: int = 10) -> List[MemoryTrace]:
        """أحدث n ذاكرة."""
        alive = [t for t in self._traces if t.is_alive()]
        return sorted(alive, key=lambda t: t.timestamp, reverse=True)[:n]

    def recall_by_world(self, world_id: int) -> List[MemoryTrace]:
        """كل الذكريات المرتبطة بعالم معين."""
        return [t for t in self._traces if t.world_id == world_id and t.is_alive()]

    def recall_by_emotion(self, emotion: str) -> List[MemoryTrace]:
        """الذكريات ذات مشاعر محددة."""
        return [t for t in self._traces if emotion in t.emotion and t.is_alive()]

    def search(self, keyword: str) -> List[MemoryTrace]:
        """بحث نصي بسيط (يمكن استبداله بـ embeddings مستقبلاً)."""
        kw = keyword.lower()
        return [t for t in self._traces if kw in t.content.lower() and t.is_alive()]

    def _prune(self) -> int:
        """حذف أضعف 20% من الذكريات."""
        self._traces.sort(key=lambda t: t.current_strength())
        cut = len(self._traces) // 5
        removed = self._traces[:cut]
        self._traces = self._traces[cut:]
        return len(removed)

    def __len__(self):
        return sum(1 for t in self._traces if t.is_alive())


class SemanticMemory:
    """
    ذاكرة المعاني — تخزّن مفاهيم مجردة مرتبطة بعوالم زيتا.

    كل مفهوم له وزن في كل عالم (يشبه embeddings خفيفة).
    """

    def __init__(self, registry: WorldRegistry):
        self._registry = registry
        # {concept: {world_id: weight}}
        self._concepts: Dict[str, Dict[int, float]] = {}

    def learn_concept(
        self,
        concept: str,
        world_weights: Optional[Dict[int, float]] = None,
        strength: float = 0.5,
    ) -> None:
        """
        تعليم مفهوم جديد.

        world_weights : {world_id: weight} — إذا لم تُحدَّد، توزيع متساوٍ.
        """
        worlds = self._registry.active_worlds()
        if world_weights is None:
            world_weights = {w: strength for w in worlds}
        self._concepts[concept] = {
            w: world_weights.get(w, 0.0) for w in worlds
        }

    def associate(self, concept_a: str, concept_b: str) -> float:
        """
        قوة الترابط بين مفهومين (dot product في فضاء العوالم).
        """
        if concept_a not in self._concepts or concept_b not in self._concepts:
            return 0.0
        worlds = self._registry.active_worlds()
        a = np.array([self._concepts[concept_a].get(w, 0.0) for w in worlds])
        b = np.array([self._concepts[concept_b].get(w, 0.0) for w in worlds])
        norm = (np.linalg.norm(a) * np.linalg.norm(b))
        return float(np.dot(a, b) / norm) if norm > 0 else 0.0

    def dominant_world(self, concept: str) -> Optional[int]:
        """العالم الأقوى ارتباطاً بمفهوم معين."""
        if concept not in self._concepts:
            return None
        return max(self._concepts[concept], key=self._concepts[concept].get)

    def all_concepts(self) -> List[str]:
        return list(self._concepts.keys())

    def reinforce_concept(self, concept: str, world_id: int, delta: float = 0.05) -> None:
        """تقوية ارتباط مفهوم بعالم معين."""
        if concept in self._concepts:
            old = self._concepts[concept].get(world_id, 0.0)
            self._concepts[concept][world_id] = min(1.0, old + delta)


class ProceduralMemory:
    """
    ذاكرة المهارات — تخزّن أنماطاً إجرائية (دوالّ أو استراتيجيات).

    يمكن تشغيل أي مهارة محفوظة باستدعاء .execute(name, *args).
    """

    def __init__(self):
        self._skills: Dict[str, Dict] = {}

    def register_skill(
        self,
        name       : str,
        fn         : Callable,
        description: str = "",
        world_id   : int  = 7,
    ) -> None:
        """تسجيل مهارة جديدة."""
        self._skills[name] = {
            "fn"         : fn,
            "description": description,
            "world_id"   : world_id,
            "call_count" : 0,
            "last_used"  : None,
        }

    def execute(self, name: str, *args, **kwargs) -> Any:
        """تنفيذ مهارة محفوظة وتحديث إحصائياتها."""
        if name not in self._skills:
            raise KeyError(f"المهارة '{name}' غير موجودة.")
        skill = self._skills[name]
        skill["call_count"] += 1
        skill["last_used"]   = time.time()
        return skill["fn"](*args, **kwargs)

    def list_skills(self) -> List[Dict]:
        return [
            {
                "name"       : name,
                "description": info["description"],
                "world_id"   : info["world_id"],
                "call_count" : info["call_count"],
            }
            for name, info in self._skills.items()
        ]

    def __len__(self):
        return len(self._skills)


class EmotionalMemory:
    """
    ذاكرة المشاعر — تتبّع الحالة العاطفية لكل عالم عبر الزمن.

    تُستخدَم لضبط decay_rate وتعديل سلوك زيتا بناءً على السياق.
    """

    def __init__(self, registry: WorldRegistry):
        self._registry = registry
        # {world_id: [{"valence": float, "arousal": float, "ts": float}]}
        self._history: Dict[int, List[Dict]] = {
            w: [] for w in registry.active_worlds()
        }

    def record_state(
        self,
        world_id: int,
        valence : float,   # إيجابي/سلبي  [-1, +1]
        arousal : float,   # شدة الانفعال [0, 1]
    ) -> None:
        """تسجيل حالة عاطفية لعالم معين."""
        if world_id not in self._history:
            self._history[world_id] = []
        self._history[world_id].append({
            "valence": max(-1.0, min(1.0, valence)),
            "arousal": max(0.0,  min(1.0, arousal)),
            "ts"     : time.time(),
        })

    def current_mood(self, world_id: int, window: int = 10) -> Dict[str, float]:
        """المزاج الحالي — متوسط آخر `window` حالات."""
        history = self._history.get(world_id, [])[-window:]
        if not history:
            return {"valence": 0.0, "arousal": 0.5, "emotion": self._registry.get_emotion(world_id)}
        avg_v = sum(h["valence"] for h in history) / len(history)
        avg_a = sum(h["arousal"] for h in history) / len(history)
        return {
            "valence": round(avg_v, 3),
            "arousal": round(avg_a, 3),
            "emotion": self._registry.get_emotion(world_id),
        }

    def decay_factor(self, world_id: int) -> float:
        """
        معامل التلاشي المعدَّل بناءً على المشاعر.
        الانفعال العالي → ذاكرة أبطأ في التلاشي.
        """
        mood = self.current_mood(world_id)
        base_decay = 0.01
        # كلما زاد الانفعال، قلّ التلاشي
        return base_decay * (1.0 - mood["arousal"] * 0.5)


# ══════════════════════════════════════════════════════════════════
#  طبقة التخزين الدائم — SQLite
# ══════════════════════════════════════════════════════════════════

class SQLiteStorage(StorageBackend):
    """
    تخزين دائم باستخدام SQLite.

    للتبديل إلى PostgreSQL لاحقاً، اكتب فئة PostgreSQLStorage
    ترث من StorageBackend وأدخلها في ZetaMemorySystem.
    """

    def __init__(self, db_path: str = "zeta_memory.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id           TEXT PRIMARY KEY,
                    type         TEXT,
                    content      TEXT,
                    world_id     INTEGER,
                    strength     REAL,
                    emotion      TEXT,
                    timestamp    REAL,
                    access_count INTEGER,
                    decay_rate   REAL,
                    metadata     TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_world ON memories(world_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_type ON memories(type)
            """)

    def save(self, trace: MemoryTrace) -> None:
        d = trace.to_dict()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO memories
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                d["id"], d["type"], d["content"], d["world_id"],
                d["strength"], d["emotion"], d["timestamp"],
                d["access_count"], d["decay_rate"],
                json.dumps(d["metadata"], ensure_ascii=False),
            ))

    def load_all(self) -> List[MemoryTrace]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT * FROM memories").fetchall()
        traces = []
        for row in rows:
            d = {
                "id"          : row[0],
                "type"        : row[1],
                "content"     : row[2],
                "world_id"    : row[3],
                "strength"    : row[4],
                "emotion"     : row[5],
                "timestamp"   : row[6],
                "access_count": row[7],
                "decay_rate"  : row[8],
                "metadata"    : json.loads(row[9]),
            }
            try:
                traces.append(MemoryTrace.from_dict(d))
            except Exception:
                pass
        return traces

    def delete(self, trace_id: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM memories WHERE id = ?", (trace_id,))

    def update(self, trace: MemoryTrace) -> None:
        self.save(trace)  # INSERT OR REPLACE تعمل كتحديث

    def stats(self) -> Dict:
        with sqlite3.connect(self.db_path) as conn:
            total  = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            by_type = conn.execute(
                "SELECT type, COUNT(*) FROM memories GROUP BY type"
            ).fetchall()
            by_world = conn.execute(
                "SELECT world_id, COUNT(*) FROM memories GROUP BY world_id"
            ).fetchall()
        return {
            "total"   : total,
            "by_type" : dict(by_type),
            "by_world": dict(by_world),
        }


# ══════════════════════════════════════════════════════════════════
#  محرك مرآة زيتا المُطوَّر
# ══════════════════════════════════════════════════════════════════

class MirrorZetaEngine(nn.Module):
    """
    النسخة الأصلية من المحرك — محفوظة للتوافق مع الكود القديم.
    (انظر ZetaMemorySystem للنسخة الحية الكاملة)
    """

    def __init__(
        self,
        num_neurons  : int   = 10_000,
        learning_rate: float = LEARNING_RATE,
        noise_std    : float = NOISE_STD,
        registry     : Optional[WorldRegistry] = None,
    ):
        super().__init__()
        self.num_neurons   = num_neurons
        self.learning_rate = learning_rate
        self.noise_std     = noise_std
        self.registry      = registry or WorldRegistry()

        worlds_tensor = self.registry.to_tensor()
        self.register_buffer("worlds", worlds_tensor)

        self.weights = nn.Parameter(self._balanced_init())

    def _balanced_init(self) -> torch.Tensor:
        worlds = self.registry.active_worlds()
        n = len(worlds)
        per_world = self.num_neurons // n
        chunks = []
        for w in worlds:
            chunk = torch.full((per_world,), float(w)) + torch.randn(per_world) * 0.3
            chunks.append(chunk)
        remainder = self.num_neurons - per_world * n
        if remainder > 0:
            chunks.append(torch.full((remainder,), float(worlds[0])) + torch.randn(remainder) * 0.3)
        return torch.cat(chunks)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        resonance = (self.weights * x) * K_SYNC
        return torch.where(resonance > H_ALPHA, resonance, resonance * 0.1)

    @torch.no_grad()
    def apply_zeta_conservation(self) -> torch.Tensor:
        dist        = torch.abs(self.weights.unsqueeze(-1) - self.worlds)
        closest_idx = torch.argmin(dist, dim=-1)
        target      = self.worlds[closest_idx]
        self.weights.add_((target - self.weights) * self.learning_rate)
        self.weights.add_(torch.randn_like(self.weights) * self.noise_std)
        return closest_idx

    def get_distribution_report(self, world_indices: torch.Tensor) -> Dict[int, str]:
        counts = torch.bincount(world_indices, minlength=len(self.registry.active_worlds()))
        report: Dict[int, str] = {}
        for i, world in enumerate(self.registry.active_worlds()):
            pct = (counts[i].item() / self.num_neurons) * 100
            report[int(world)] = f"{counts[i].item()} neurons ({pct:.1f}%)"
        return report

    def activation_rate(self, x: torch.Tensor) -> float:
        with torch.no_grad():
            resonance = (self.weights * x) * K_SYNC
            return (resonance > H_ALPHA).float().mean().item() * 100


# ══════════════════════════════════════════════════════════════════
#  النظام المتكامل — ZetaMemorySystem
# ══════════════════════════════════════════════════════════════════

class ZetaMemorySystem:
    """
    نظام الذاكرة الحية المتكامل.

    يجمع:
    - MirrorZetaEngine  (المحرك العصبي)
    - EpisodicMemory    (أحداث وتفاعلات)
    - SemanticMemory    (معاني ومفاهيم)
    - ProceduralMemory  (مهارات)
    - EmotionalMemory   (سياق عاطفي)
    - SQLiteStorage     (تخزين دائم)
    - WorldRegistry     (سجل العوالم القابل للتوسع)

    مثال سريع
    ----------
    >>> system = ZetaMemorySystem()
    >>> system.experience("رأيت شيئاً مثيراً للاهتمام", valence=0.8, arousal=0.7)
    >>> system.learn("الضوء", world_weights={17: 0.9, 29: 0.7})
    >>> memories = system.recall("مثير")
    >>> report = system.status_report()
    """

    def __init__(
        self,
        num_neurons  : int  = 10_000,
        db_path      : str  = "zeta_memory.db",
        hooks        : Optional[List[MemoryHook]] = None,
        auto_persist : bool = True,
    ):
        # سجل العوالم — نقطة التوسع الأولى
        self.registry  = WorldRegistry()

        # المحرك العصبي
        self.engine = MirrorZetaEngine(
            num_neurons=num_neurons,
            registry=self.registry,
        )

        # طبقات الذاكرة
        self.episodic   = EpisodicMemory()
        self.semantic   = SemanticMemory(self.registry)
        self.procedural = ProceduralMemory()
        self.emotional  = EmotionalMemory(self.registry)

        # التخزين الدائم
        self.storage     = SQLiteStorage(db_path)
        self.auto_persist = auto_persist

        # الخطاطيف — للتوسع بـ LLM أو DB خارجي
        self._hooks: List[MemoryHook] = hooks or []

        # حالة العوالم
        self._world_states: Dict[int, WorldState] = {
            w: WorldState(
                world_id=w,
                weight=float(w),
                emotion=self.registry.get_emotion(w),
            )
            for w in self.registry.active_worlds()
        }

        # تحميل الذاكرة المحفوظة مسبقاً
        self._restore_from_storage()

        # تسجيل المهارات الافتراضية
        self._register_default_skills()

    # ──────────────────────────────────────────
    #  الواجهة الرئيسية
    # ──────────────────────────────────────────

    def experience(
        self,
        event    : str,
        valence  : float = 0.0,
        arousal  : float = 0.5,
        strength : float = 0.5,
        metadata : Optional[Dict] = None,
    ) -> MemoryTrace:
        """
        تسجيل حدث جديد في الذاكرة.

        المعاملات
        ----------
        event   : وصف الحدث
        valence : التكافؤ العاطفي [-1, +1] (سلبي/إيجابي)
        arousal : شدة الانفعال [0, 1]
        strength: قوة الذاكرة الأولية
        """
        # تشغيل المحرك العصبي
        x       = torch.randn(self.engine.num_neurons)
        _       = self.engine(x)
        indices = self.engine.apply_zeta_conservation()

        # إيجاد العالم المهيمن
        dominant_world = int(torch.mode(indices).values.item())
        emotion        = self.registry.get_emotion(dominant_world)

        # تسجيل الحالة العاطفية
        self.emotional.record_state(dominant_world, valence, arousal)

        # ضبط معدل التلاشي بناءً على العاطفة
        decay = self.emotional.decay_factor(dominant_world)

        # إنشاء الأثر
        trace = self.episodic.record(
            content  = event,
            world_id = dominant_world,
            emotion  = emotion,
            strength = strength,
            metadata = metadata or {},
        )
        trace.decay_rate = decay

        # تحديث حالة العالم
        self._update_world_state(dominant_world, indices, x)

        # تشغيل الخطاطيف
        for hook in self._hooks:
            hook.on_store(trace)

        # حفظ دائم
        if self.auto_persist:
            self.storage.save(trace)

        return trace

    def learn(
        self,
        concept      : str,
        world_weights: Optional[Dict[int, float]] = None,
        strength     : float = 0.5,
    ) -> None:
        """
        تعليم مفهوم دلالي جديد.

        مثال
        ----
        system.learn("الإبداع", world_weights={17: 0.9, 29: 0.8})
        """
        self.semantic.learn_concept(concept, world_weights, strength)

    def recall(
        self,
        query       : str,
        memory_types: Optional[List[MemoryType]] = None,
        top_n       : int = 10,
    ) -> List[MemoryTrace]:
        """
        استرجاع الذكريات بناءً على نص أو سياق.

        memory_types: قيّد البحث لأنواع محددة (None = كل الأنواع)
        """
        results = []

        # بحث episodic
        if memory_types is None or MemoryType.EPISODIC in memory_types:
            results.extend(self.episodic.search(query))

        # تعزيز الذكريات المسترجعة
        for trace in results:
            trace.reinforce()
            if self.auto_persist:
                self.storage.update(trace)

        # تشغيل الخطاطيف
        for hook in self._hooks:
            results = hook.on_recall(results, query)

        # ترتيب حسب القوة الحالية
        results.sort(key=lambda t: t.current_strength(), reverse=True)
        return results[:top_n]

    def recall_emotional(self, emotion: str) -> List[MemoryTrace]:
        """استرجاع الذكريات بناءً على مشاعر محددة."""
        return self.episodic.recall_by_emotion(emotion)

    def recall_world(self, world_id: int) -> List[MemoryTrace]:
        """كل الذكريات المرتبطة بعالم معين."""
        return self.episodic.recall_by_world(world_id)

    def run_skill(self, name: str, *args, **kwargs) -> Any:
        """تنفيذ مهارة إجرائية محفوظة."""
        result = self.procedural.execute(name, *args, **kwargs)
        self.experience(
            f"تنفيذ المهارة: {name}",
            valence=0.3,
            arousal=0.4,
            metadata={"skill": name},
        )
        return result

    # ──────────────────────────────────────────
    #  إدارة العوالم
    # ──────────────────────────────────────────

    def add_world(
        self,
        world_id   : int,
        emotion    : str = "محايد",
        description: str = "",
    ) -> None:
        """
        إضافة عالم جديد ديناميكياً.

        ⚠️  الأوزان الحالية للمحرك لا تتغير — العالم الجديد يدخل
             في دورات زيتا التالية تلقائياً.
        """
        self.registry.register_world(world_id, emotion, description)
        self._world_states[world_id] = WorldState(
            world_id=world_id,
            weight=float(world_id),
            emotion=emotion,
        )
        # تحديث tensor العوالم في المحرك
        self.engine.worlds = self.registry.to_tensor()
        self.emotional._history[world_id] = []

    # ──────────────────────────────────────────
    #  التقارير
    # ──────────────────────────────────────────

    def status_report(self) -> str:
        """
        تقرير شامل عن حالة الذاكرة والمحرك.
        """
        x       = torch.randn(self.engine.num_neurons)
        indices = self.engine.apply_zeta_conservation()
        dist_report = self.engine.get_distribution_report(indices)
        act_rate    = self.engine.activation_rate(x)
        db_stats    = self.storage.stats()

        lines = [
            "╔══════════════════════════════════════════╗",
            "║   تقرير نظام الذاكرة الحية — زيتا       ║",
            "╠══════════════════════════════════════════╣",
            f"║  🧠 عصبونات   : {self.engine.num_neurons:>8,}              ║",
            f"║  ⚡ تفعيل     : {act_rate:>7.1f}%              ║",
            f"║  💾 قاعدة بيانات: {db_stats['total']:>6,} ذاكرة          ║",
            f"║  📝 جلسة حالية: {len(self.episodic):>7,} حدث            ║",
            f"║  📚 مفاهيم   : {len(self.semantic.all_concepts()):>7,}               ║",
            f"║  🔧 مهارات   : {len(self.procedural):>7,}               ║",
            "╠══════════════════════════════════════════╣",
            "║  توزيع العصبونات على العوالم:             ║",
        ]

        for world_id, stat in dist_report.items():
            mood    = self.emotional.current_mood(world_id)
            emotion = self.registry.get_emotion(world_id)
            count   = int(stat.split()[0])
            pct     = count / self.engine.num_neurons * 100
            bar     = "█" * int(pct / 2)
            v_icon  = "😊" if mood["valence"] > 0.2 else ("😔" if mood["valence"] < -0.2 else "😐")
            lines.append(
                f"║  {v_icon} {world_id:2d}({emotion[:4]}) | {pct:5.1f}% {bar:<8} ║"
            )

        lines += [
            "╠══════════════════════════════════════════╣",
            "║  العوالم المسجّلة:                        ║",
        ]
        for wid in self.registry.active_worlds():
            em = self.registry.get_emotion(wid)
            lines.append(f"║    ✅ {wid:3d} — {em:<28} ║")

        lines.append("╚══════════════════════════════════════════╝")
        return "\n".join(lines)

    def memory_snapshot(self) -> Dict:
        """
        لقطة كاملة من حالة الذاكرة (قابلة للتصدير بـ JSON).
        """
        x       = torch.randn(self.engine.num_neurons)
        indices = self.engine.apply_zeta_conservation()

        return {
            "timestamp"    : time.time(),
            "engine"       : {
                "num_neurons" : self.engine.num_neurons,
                "activation"  : self.engine.activation_rate(x),
                "distribution": self.engine.get_distribution_report(indices),
            },
            "memory"       : {
                "episodic_alive"   : len(self.episodic),
                "semantic_concepts": len(self.semantic.all_concepts()),
                "skills"           : len(self.procedural),
                "db_total"         : self.storage.stats()["total"],
            },
            "worlds"       : {
                str(w): {
                    "emotion": self.registry.get_emotion(w),
                    "mood"   : self.emotional.current_mood(w),
                }
                for w in self.registry.active_worlds()
            },
        }

    # ──────────────────────────────────────────
    #  داخلي — مساعد
    # ──────────────────────────────────────────

    def _update_world_state(
        self,
        dominant_world: int,
        indices: torch.Tensor,
        x: torch.Tensor,
    ) -> None:
        counts = torch.bincount(indices, minlength=len(self.registry.active_worlds()))
        for i, w in enumerate(self.registry.active_worlds()):
            if w in self._world_states:
                self._world_states[w].neuron_count   = counts[i].item()
                self._world_states[w].activation_pct = self.engine.activation_rate(x)
                self._world_states[w].memory_load     = len(self.episodic.recall_by_world(w))
                if w == dominant_world:
                    self._world_states[w].last_active = time.time()

    def _restore_from_storage(self) -> None:
        """تحميل الذاكرات المحفوظة من SQLite عند بدء التشغيل."""
        traces = self.storage.load_all()
        for trace in traces:
            if trace.is_alive():
                self.episodic._traces.append(trace)

    def _register_default_skills(self) -> None:
        """تسجيل المهارات الافتراضية للمحرك."""
        self.procedural.register_skill(
            name="zeta_conservation",
            fn=self.engine.apply_zeta_conservation,
            description="تطبيق حفظ زيتا على أوزان المحرك",
            world_id=13,
        )
        self.procedural.register_skill(
            name="full_cycle",
            fn=lambda: self.engine(torch.randn(self.engine.num_neurons)),
            description="دورة معالجة كاملة للمحرك",
            world_id=7,
        )

    def add_hook(self, hook: MemoryHook) -> None:
        """إضافة خطاف جديد (للتوسع بـ LLM أو قاعدة بيانات خارجية)."""
        self._hooks.append(hook)


# ══════════════════════════════════════════════════════════════════
#  دالة التدريب — متوافقة مع الواجهة الأصلية
# ══════════════════════════════════════════════════════════════════

def train(
    num_neurons: int  = 10_000,
    epochs     : int  = 100,
    verbose    : bool = True,
    db_path    : str  = "zeta_memory.db",
) -> Tuple["ZetaMemorySystem", Dict[int, str]]:
    """
    تدريب النظام مع دعم الذاكرة الحية.
    متوافق تماماً مع واجهة الإصدار الأصلي.
    """
    system = ZetaMemorySystem(num_neurons=num_neurons, db_path=db_path)

    if verbose:
        print("🚀 بدء التدريب — نظام الذاكرة الحية...")
        print("=" * 55)

    indices = None
    for step in range(epochs):
        data_stream = torch.randn(num_neurons)
        _           = system.engine(data_stream)
        indices     = system.engine.apply_zeta_conservation()

        # تسجيل كل 25 دورة كـ "حدث" في الذاكرة
        if (step + 1) % 25 == 0:
            act_rate = system.engine.activation_rate(data_stream)
            system.experience(
                f"دورة تدريب #{step+1} | تفعيل: {act_rate:.1f}%",
                valence=0.1,
                arousal=0.4,
                metadata={"epoch": step + 1, "activation": act_rate},
            )
            if verbose:
                report = system.engine.get_distribution_report(indices)
                active = sum(1 for v in report.values() if not v.startswith("0"))
                print(f"الدورة {step+1:3d} | عوالم نشطة: {active}/8 | تفعيل: {act_rate:.1f}%")

    final_report = system.engine.get_distribution_report(indices)

    if verbose:
        print("\n" + system.status_report())

    return system, final_report


# ══════════════════════════════════════════════════════════════════
#  نقطة الدخول
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # ── مثال شامل ──────────────────────────────────────────────
    system, report = train(num_neurons=10_000, epochs=100)

    print("\n🧪 اختبار الذاكرة الحية:")
    print("-" * 40)

    # تجربة أحداث
    system.experience("اكتشفت نمطاً رياضياً جميلاً", valence=0.9, arousal=0.8)
    system.experience("فشل في التقارب",               valence=-0.5, arousal=0.6)
    system.experience("حل المشكلة بطريقة مبتكرة",    valence=0.7, arousal=0.9)

    # تعلّم مفاهيم
    system.learn("الرنين",   world_weights={7: 0.8, 13: 0.9})
    system.learn("التقارب",  world_weights={11: 0.7, 19: 0.8})
    system.learn("الابتكار", world_weights={17: 0.9, 29: 0.8})

    # استرجاع
    memories = system.recall("نمط")
    print(f"✅ الذكريات المسترجعة لـ 'نمط': {len(memories)}")
    for m in memories[:3]:
        print(f"   [{m.world_id}|{m.emotion}] {m.content[:50]}")

    # إضافة عالم جديد ديناميكياً
    system.add_world(37, emotion="اندهاش", description="عالم الاكتشافات المفاجئة")
    print(f"\n🌍 تمت إضافة العالم 37 — العوالم الآن: {system.registry.active_worlds()}")

    # حفظ لقطة
    snapshot = system.memory_snapshot()
    with open("zeta_snapshot.json", "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2, default=str)
    print("\n💾 تم حفظ اللقطة في: zeta_snapshot.json")

    # حفظ الأوزان
    torch.save(system.engine.state_dict(), "mirror_zeta_weights.pth")
    print("💾 تم حفظ الأوزان في: mirror_zeta_weights.pth")
