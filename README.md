# Mirror Network — Prime Generator v3

**H. Chaouchi 2026**

مولّد أعداد أولية يعتمد على خوارزمية الرنين الطيفي H_gamma كفلتر، مع Miller-Rabin للتحقق النهائي.

## خط الأنابيب

```
① mod 30  →  ② الرنين H_gamma  →  ③ Miller-Rabin  →  ✓ أولي مؤكد
```

## الملفات

```
src/    prime_generator_v3.html   التطبيق الكامل
tests/  test_algorithm.js         اختبار الخوارزمية
docs/   ALGORITHM.md              الشرح الرياضي
```

## الاستخدام

افتح `src/prime_generator_v3.html` في المتصفح مباشرة.

## النتائج

- **0 ضجيج** في الخرج النهائي (Miller-Rabin يضمن ذلك)
- الرنين يستبعد **695 مركبة** قبل الوصول إلى Miller-Rabin
