# 🧠 MirrorZeta — نظام الذاكرة الحية

نظام لتخزين التجارب النصية مع بيانات عاطفية، والبحث فيها دلالياً، وكشف الروابط بين الذكريات المتشابهة.

---

## 📁 هيكل المشروع

```
mirror_zeta/
├── mirror_zeta.py      ← المحرك الرئيسي
├── demo.py             ← عرض توضيحي تفاعلي
├── requirements.txt
├── .gitignore
├── logs/               ← ملفات السجلات (تُنشأ تلقائياً)
└── tests/
    └── test_mirror_zeta.py
```

---

## ⚡ تشغيل سريع

```bash
# 1. استنساخ المستودع
git clone https://github.com/YOUR_USERNAME/mirror-zeta.git
cd mirror-zeta

# 2. تثبيت المتطلبات الأساسية
pip install numpy pytest

# 3. (اختياري) للحصول على بحث دلالي حقيقي
pip install sentence-transformers faiss-cpu torch

# 4. تشغيل العرض التوضيحي
python demo.py

# 5. تشغيل الاختبارات
pytest tests/ -v
```

---

## 🔧 المكونات الرئيسية

### `MemoryTrace` — الذكرى

| حقل | النوع | الوصف |
|---|---|---|
| `content` | `str` | نص التجربة |
| `world_id` | `int` | رقم تعريف "العالم" (سياق، مشروع، شخص…) |
| `emotion` | `str` | التسمية العاطفية |
| `valence` | `float [-1, +1]` | شدة المشاعر: -1 سلبي جداً، +1 إيجابي جداً |
| `strength` | `float` | قوة الذكرى (ترتفع كلما تشابكت مع غيرها) |
| `embedding` | `np.ndarray` | متجه المعنى الدلالي |

### `MirrorZetaCore` — الواجهة الرئيسية

```python
from mirror_zeta import MirrorZetaCore

with MirrorZetaCore(db_path="my_memory.db") as zeta:

    # تسجيل تجربة
    id = zeta.experience(
        content  = "أشعر بسعادة كبيرة اليوم",
        world_id = 1,
        emotion  = "فرح",
        valence  = 0.9,
    )

    # بحث دلالي
    results = zeta.recall("سعادة وإيجابية", limit=3)
    for trace, score in results:
        print(f"{score:.2f} | {trace.content}")

    # كشف الروابط بين الذكريات المتشابهة
    report = zeta.reflect()
    print(f"روابط مكتشفة: {report['connections']}")

    # ملخص عالم معين
    summary = zeta.get_world_summary(1)
```

---

## 🌡️ مستويات الأداء

| الإعداد | البحث | `reflect()` |
|---|---|---|
| `numpy` فقط | نصي بسيط | يحتاج embeddings يدوية |
| + `sentence-transformers` | **دلالي كامل** ✅ | **كشف روابط تلقائي** ✅ |
| + `faiss-cpu` | **سريع جداً** ✅ | — |

---

## 🧪 الاختبارات

```bash
pytest tests/ -v                  # كل الاختبارات
pytest tests/ -v -k "storage"     # اختبارات التخزين فقط
pytest tests/ -v -k "core"        # اختبارات المحرك فقط
pytest tests/ --tb=short          # أخطاء مختصرة
```

---

## 📌 ملاحظات

- **`world_id`**: يمكن استخدامه لتمييز السياقات — مثلاً `0` = عمل، `1` = شخصي، `2` = مشروع معين.
- **`reflect()`**: يعمل بشكل مثالي فقط مع `sentence-transformers`. بدونه تحتاج إلى حقن `embedding` يدوياً.
- قاعدة البيانات `SQLite` — لا تحتاج إلى إعداد إضافي.
