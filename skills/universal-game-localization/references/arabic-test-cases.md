# Arabic rendering test cases

Use these strings in a test build or text preview. A preview outside the game does not prove in-game support.

## Basic
1. مرحبا بالعالم
2. أين أنت؟
3. هذا اختبار للتعريب.
4. اللاعب: اذهب إلى الباب ثم عد.
5. لا تفتح هذا الباب!
6. تُحفظ الإعدادات تلقائيًا.

## Joining, ligatures, diacritics
7. لا لأ لإ لآ (lam-alef forms)
8. مُحَمَّدٌ كَتَبَ الرِّسَالَةَ (full diacritics - check clipping)
9. استخدامهم للمستخدمين والمستشارين (long connected words)

## Mixed direction and numbers
10. English 123 - العربية
11. ١٢٣٤٥٦٧٨٩٠ / 1234567890
12. النسخة 1.2.3 من اللعبة
13. اضغط [E] للتفاعل أو Esc للخروج

## Punctuation and brackets
14. (اختبار) [قائمة] {متغير}
15. علامات الترقيم: ، ؛ ؟ ! . :
16. «اقتباس» و "اقتباس"

## Placeholders and markup (must stay intact and correctly placed)
17. لديك {0} عناصر من أصل {1}
18. تم حفظ %d ملفات في %s
19. <b>تحذير:</b> الباب مغلق
20. [PLAYER_NAME]، مرحبا بعودتك!

## Layout
21. سطر أول\nسطر ثانٍ (explicit line break)
22. نص طويل جدًا يستخدم لاختبار التفاف الأسطر داخل مربعات الحوار والقوائم عندما لا تتسع الكلمات في سطر واحد من النافذة.
23. زر قصير: حفظ | تحميل | خروج

Record per test: font, engine renderer, shaping/bidi behavior, alignment, line-wrap, glyph coverage, status (VERIFIED/TESTED/FAILED) and screenshot evidence if testing was actually performed.
