"""
demo.py — تجربة MirrorZeta خطوة بخطوة
"""
from mirror_zeta import MirrorZetaCore
import json

RESET = "\033[0m"
BOLD  = "\033[1m"
GREEN = "\033[92m"
CYAN  = "\033[96m"
YELLOW= "\033[93m"
RED   = "\033[91m"
DIM   = "\033[2m"

def sep(title="", char="═"):
    w = 64
    if title:
        pad = (w - len(title) - 2) // 2
        print(f"\n{char * pad} {BOLD}{title}{RESET} {char * pad}")
    else:
        print(char * w)

def main():
    print(f"\n{BOLD}{'='*64}")
    print(f"   🧠  MirrorZeta v2.2 — نظام الذاكرة الحية")
    print(f"{'='*64}{RESET}\n")

    # استخدام context manager لضمان إغلاق الموارد
    with MirrorZetaCore(db_path="demo.db", use_vector_search=True) as zeta:

        # ─────────────────────────────────────────────────────────
        sep("المرحلة 1 — تسجيل التجارب")
        # ─────────────────────────────────────────────────────────

        experiences = [
            # (content, world_id, emotion, valence)
            ("أشعر بحماس كبير لتعلم البرمجة العصبية والذكاء الاصطناعي",  7,  "حماس",  0.90),
            ("الشعور بالإثارة والفرح عند فهم مفهوم برمجي جديد",          7,  "فرح",   0.85),
            ("نجحت في حل معضلة رياضية معقدة بطريقة أنيقة وبسيطة",       13, "رضا",   0.80),
            ("هناك مشكلة تقنية صعبة في الخوارزمية تحتاج إلى حل سريع",   11, "قلق",  -0.30),
            ("القلق والخوف من عدم القدرة على فهم النظام المعقد",          11, "خوف",  -0.70),
            ("فرحة كبيرة بعد إنجاز المشروع وتسليمه في الوقت المحدد",    13, "فرح",   0.95),
        ]

        ids = []
        for content, wid, emotion, valence in experiences:
            tid = zeta.experience(content, wid, emotion, valence)
            status = f"{GREEN}✅{RESET}" if tid else f"{RED}❌{RESET}"
            print(f"  {status} [{emotion:6s}] {content[:52]}...")
            if tid:
                ids.append(tid)

        print(f"\n  {BOLD}→ تم تسجيل {len(ids)}/{len(experiences)} ذكرى{RESET}")

        # ─────────────────────────────────────────────────────────
        sep("المرحلة 2 — البحث الدلالي")
        # ─────────────────────────────────────────────────────────

        queries = [
            ("سعيد وحماس للتعلم",   None),
            ("مشكلة تقنية صعبة",    None),
            ("حماس وبرمجة",          7),
            ("قلق وخوف",            11),
            ("إنجاز وفرح",          13),
        ]

        for query, wf in queries:
            label = f"[عالم {wf}]" if wf is not None else "[كل العوالم]"
            print(f"\n  {CYAN}🔍 '{query}' {DIM}{label}{RESET}")
            results = zeta.recall(query, limit=2, world_id=wf)
            if not results:
                print(f"     {DIM}لا نتائج{RESET}")
            for rank, (trace, score) in enumerate(results, 1):
                bar = "█" * int(score * 10) + "░" * (10 - int(score * 10))
                print(f"     {rank}. {bar} {YELLOW}{score:.2f}{RESET}  [{trace.emotion}]  {trace.content[:48]}...")

        # ─────────────────────────────────────────────────────────
        sep("المرحلة 3 — التأمل وبناء الروابط")
        # ─────────────────────────────────────────────────────────

        ref = zeta.reflect()
        print(f"\n  🔗 اتصالات مكتشفة: {BOLD}{ref['connections']}{RESET}")
        print(f"  العتبة المستخدمة:  {ref['threshold']}")

        if ref['relationships']:
            print(f"\n  {BOLD}الروابط:{RESET}")
            for r in ref['relationships']:
                print(f"  • {r['trace1'][:36]}...")
                print(f"    ↔ {r['trace2'][:36]}...")
                print(f"    {DIM}تشابه: {r['similarity']:.4f}{RESET}\n")
        else:
            print(f"\n  {YELLOW}⚠️  لا روابط — يحتاج sentence-transformers لنتائج أفضل{RESET}")

        # ─────────────────────────────────────────────────────────
        sep("المرحلة 4 — ملخص الأعوال")
        # ─────────────────────────────────────────────────────────

        for wid in [7, 11, 13]:
            s = zeta.get_world_summary(wid)
            valence_bar = "+" if s.get('average_valence', 0) > 0 else "-"
            print(f"\n  {BOLD}العالم [{wid}]{RESET}")
            print(f"    ذكريات:         {s['trace_count']}")
            print(f"    مشاعر مهيمنة:  {s.get('dominant_emotion', '?')}")
            print(f"    متوسط الإيجابية: {s.get('average_valence', 0):+.2f}")

        # ─────────────────────────────────────────────────────────
        sep("المرحلة 5 — ملخص ذكرة واحدة")
        # ─────────────────────────────────────────────────────────

        if ids:
            summary = zeta.get_trace_summary(ids[0])
            if summary:
                print(f"\n  ID:      {DIM}{summary['id']}{RESET}")
                print(f"  محتوى:  {summary['content'][:60]}")
                print(f"  عاطفة:  {summary['emotion']}")
                print(f"  قوة:    {summary['strength']:.2f}")
                print(f"  روابط:  {summary['related_count']}")

        # ─────────────────────────────────────────────────────────
        sep("حالة النظام")
        # ─────────────────────────────────────────────────────────

        status = zeta.get_system_status()
        db     = status['database_stats']

        print(f"\n  الإصدار:          {BOLD}{status['version']}{RESET}")
        print(f"  الذكريات (RAM):   {status['in_memory_traces']}")
        print(f"  الذكريات (DB):    {db.get('total_traces', '?')}")
        print(f"  الروابط (DB):     {db.get('relationships', '?')}")
        print(f"  متوسط القوة:      {db.get('average_strength', 0):.2f}")
        print(f"  بحث متجهي:       {'✅' if status['vector_search'] else '❌  (ثبّت sentence-transformers)'}")
        print(f"  FAISS:            {'✅' if status['faiss_index'] else '❌  (ثبّت faiss-cpu)'}")

        sep()
        print(f"\n{GREEN}{BOLD}  ✅ النظام يعمل بنجاح!{RESET}\n")


if __name__ == "__main__":
    main()
