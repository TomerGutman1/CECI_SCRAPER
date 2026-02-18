# GOV2DB - Quick Reference for New Conversation

## 🚨 Current Situation (Feb 18, 2026)
- **Status:** Algorithm improvements ready, NOT YET DEPLOYED
- **Problems:** 42% duplicates, 50% tag accuracy, 472 fake ministries
- **Solution:** Complete implementation ready in 15+ files

## 📁 Key Files to Check
```bash
# Main implementation plan
.planning/COMPLETE_IMPLEMENTATION_PLAN.md   # Full details

# Current state
.planning/state.md                          # Project status

# Deployment guide
DEPLOYMENT_GUIDE.md                         # Step-by-step

# Updated project instructions
CLAUDE.md                                   # Has new deploy commands
```

## 🚀 Quick Start Commands
```bash
# 1. Check where we are
make deploy-check

# 2. Run pre-deployment tests
python bin/pre_deployment_tests.py --quick

# 3. Deploy everything
make deploy-full

# 4. Verify success
make verify-deployment
```

## 🎯 What Was Created (Not Yet Deployed)

### Smart Detection Systems
- `config/tag_detection_profiles.py` - 45 Hebrew tag profiles
- `config/ministry_detection_rules.py` - 44 ministry validation rules

### AI Optimization
- `src/gov_scraper/processors/unified_ai.py` - 1 call instead of 5-6
- `src/gov_scraper/processors/ai_validator.py` - Semantic validation

### Database Fixes
- `database/migrations/004_fix_duplicates_and_constraints.sql` - Remove 7,230 duplicates

### Monitoring
- `src/gov_scraper/monitoring/quality_monitor.py` - Real-time tracking
- `bin/deploy_improvements.py` - Automated deployment

## ⚠️ Critical Info for Deployment

### Must Do Before Running
1. **Backup database** - ~25K records
2. **Test on 5-10 decisions first**
3. **Run DB migration in Supabase SQL Editor**
4. **Test edge cases** (Gov 28, long content, missing titles)
5. **Verify operativity** - appointments must be DECLARATIVE (not operative)

### Expected Results After Deployment
- Duplicates: 42% → <1%
- Tag accuracy: 50% → 90%+
- API calls: 5-6 → 1-2 per decision
- Cost: $15-20 → $3-5 per 1000
- QA time: 4 hours → 10 minutes

### Rollback If Needed
```bash
# Stop everything
pkill -f sync.py

# Disable new AI
sed -i '' '/USE_UNIFIED_AI/d' .env

# Remove constraint if issues
# In Supabase: ALTER TABLE israeli_government_decisions DROP CONSTRAINT unique_decision_key;
```

## 📊 Key Improvements Summary

1. **Tag Detection:** Each of 45 tags has custom Hebrew keywords + AI hints
2. **Ministry Validation:** Only 44 allowed, no hallucinations
3. **Duplicate Prevention:** UNIQUE constraint + deterministic URLs
4. **AI Efficiency:** Single call for all fields
5. **Monitoring:** Real-time alerts if issues

## 🔧 Problem-Solution Mapping

| What Was Broken | Why | How We Fixed It |
|-----------------|-----|-----------------|
| 42% duplicates | No constraints | UNIQUE key + cleanup |
| 50% tag accuracy | AI confusion from 45 options | Custom profiles per tag |
| 472 fake ministries | No validation | Strict whitelist |
| Wrong URLs | Trusting corrupt catalog | Build deterministically |
| 5-6 AI calls | Separate processing | Unified processor |
| 80% operative bias | Appointments/committees wrongly operative | Reclassified as declarative + balanced prompts |

## 🎯 Testing Priority

### Edge Cases That Must Pass
1. **Gov 28 decision** - URL offset issue
2. **Long content** (>10K chars) - Truncation
3. **Duplicate insertion** - Must be rejected
4. **Fake ministry** - Must not create
5. **Hebrew date** - DD.MM.YYYY conversion
6. **Appointment decision** - Must be DECLARATIVE (not operative)
7. **Committee establishment** - Must be DECLARATIVE (not operative)

## 📝 For New Conversation

Say: "I need to continue the GOV2DB algorithm improvement deployment. Check `.planning/COMPLETE_IMPLEMENTATION_PLAN.md` for full context."

Key points to mention:
- 5 specialized agents created the solution
- 15+ files ready but NOT deployed yet
- Need to test on small sample before full run
- Database has ~25K records that need fixing

---

**Remember:** The implementation is COMPLETE but NOT DEPLOYED. Start with `make deploy-check`.