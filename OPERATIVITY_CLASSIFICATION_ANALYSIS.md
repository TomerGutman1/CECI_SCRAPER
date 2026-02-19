# Operativity Classification Analysis & Improvement Plan

## Current Problem
- **Bias Identified:** 94% of recent decisions classified as "אופרטיבית" (should be 60-65%)
- **Root Cause:** AI over-classifies appointments and administrative actions as operative
- **Impact:** Poor search/filter accuracy for users seeking truly operative decisions

## Pattern Analysis from Recent 50 Decisions

### ❌ Wrongly Classified as Operative (Should be Declarative)

**Appointment Patterns:**
- `אישור מינוי מנהל הרשות...` → Should be דקלרטיבית
- `אישור מינוי חברת נתיבי איילון...` → Should be דקלרטיבית
- `מינוי` anywhere in title/content → Strong declarative indicator

**Committee/Administrative Patterns:**
- `הסמכת שר... להגיש לוועדת השרים` → Should be דקלרטיבית
- `ועדת` in title → Often declarative (committee formation/delegation)
- `הכרה בתוספת שכר` → Recognition/acknowledgment = declarative

### ✅ Correctly Should Be Operative
- `הקמת יישובים חדשים` → Creates new settlements (operative)
- `הקצאת תקציב` → Budget allocation (operative)
- `אישור הסכם` + implementation → Agreement approval with action (operative)

## Hebrew Keywords Classification Matrix

### 🔴 **Strong Declarative Indicators** (95% confidence)
```hebrew
מינוי, מינויו, מינויה, מינוים
אישור מינוי
להקים ועדה
ועדת השרים
ועדת הכנסת
הממשלה מביעה
הממשלה רושמת
הממשלה מכירה
להכיר ב
אישור עקרוני (without implementation)
הבעת עמדה
רישום בפניה
הכרה ב
להתנגד להצעת חוק
לתמוך בהצעת חוק (position statements)
```

### 🟡 **Context-Dependent Patterns**
```hebrew
הסמכת - If followed by "ועדה" → declarative, else check context
אישור - If appointment/committee → declarative, if budget/agreement → operative
לאשר - Check what is being approved
```

### 🟢 **Strong Operative Indicators** (90% confidence)
```hebrew
הקצאת תקציב
להקצות
הקמת יישובים
לבנות, לפתח
להטיל מס
לשנות את כללי
להגדיל את מספר
לקבוע תעריף
ביצוע פרויקט
יישום התוכנית
פעולות מעשיות
```

## Current AI Prompt Issues

**Problems with existing `generate_operativity()` function:**
1. Too many operative examples (5) vs declarative (5) - creates balance confusion
2. Appointments mentioned as declarative but rules unclear
3. Missing explicit bias correction ("Don't default to operative")
4. No keyword-based validation layer

## Implementation Plan

### Phase 1: Enhanced AI Prompt ✅
- Add explicit bias correction instructions
- Strengthen declarative definitions
- Add Hebrew keyword examples
- Implement multi-step reasoning: keyword detection → context analysis → classification

### Phase 2: Rule-Based Validation Layer ✅
- Post-processing validation for common patterns
- Override AI classification when pattern confidence > 90%
- Appointment pattern → force declarative
- Committee delegation → force declarative

### Phase 3: Testing & Validation ✅
- Test on recent 50 decisions
- Measure classification balance improvement
- Target: 94% operative → 60-65% operative

## Expected Results
- **Operative Rate:** 94% → 60-65% (normal government balance)
- **Accuracy Improvement:** Better alignment with Israeli government decision patterns
- **User Experience:** More precise filtering and search results