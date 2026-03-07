# Audit Report: Real Data vs Bot Tracking

**Date**: February 2026
**Data Source**: Manual extraction from Reddit accounts
**Status**: Issues identified and FIXED in refactoring

---

## Executive Summary

**Critical failures identified (now fixed):**
- ~~Cross-account isolation is NOT working~~ → ✅ FIXED with atomic claim-before-act
- ~~Same thread rule violated~~ → ✅ FIXED with thread claiming
- ~~Logging accuracy is poor~~ → ✅ FIXED with proper verification
- ~~False positives in logging~~ → ✅ FIXED by checking message appears

---

## Fixes Applied

### 1. Single Source of Truth
**Before**: 4 separate JSON files that could get out of sync
**After**: Single `state.json` with all user/thread/action data

### 2. Atomic Claim-Before-Act
**Before**: Check file → Act → Write to file (race condition)
**After**: Atomic `claim_user()` returns CLAIMED/ALREADY_CLAIMED/ALREADY_CONTACTED

### 3. Strong Verification
**Before**: Check if username on page (always true)
**After**: Check if OUR message text appears in conversation

### 4. Type Safety
**Before**: String literals ("success", "failed")
**After**: Enums (`ActionResult.SUCCESS`, `ActionResult.FAILED`)

---

## Historical Cross-Account Violations (Pre-Fix)

### Users Contacted by Multiple Accounts

| User | Action 1 | Action 2 |
|------|----------|----------|
| `Hampshire_Coast` | DM by Working_Golf72 | Comment by ilovereddidotcom |
| `Ok-Bother9736` | DM by Working_Golf72 | Comment by This_Photo5976 |
| `Audthebod2018` | DM by Working_Golf72 | Comment by This_Photo5976 |
| `Straight-Pilot-3387` | DM by ilovereddidotcom | Comment by This_Photo5976 |

**Root Cause**: The `users_engaged.json` check happened, but:
1. DM and comment happened in same session before file was written
2. File got cleared/reset between runs
3. Race condition: multiple accounts ran simultaneously

**Fix Applied**: Atomic `claim_user()` with file locking. User is claimed BEFORE any action is attempted.

---

## Historical Same Thread Violations (Pre-Fix)

### r/AskUK Thread: "How healthy or unhealthy are these frozen ready meals"

**ilovereddidotcom** posted **7 comments** in this single thread.
**This_Photo5976** ALSO posted in this thread.

**Root Cause**: `threads_touched.json` was not being checked properly.

**Fix Applied**: Atomic `claim_thread()` with same claim-before-act pattern.

---

## Historical Logging Accuracy Issues (Pre-Fix)

### Working_Golf72
| Metric | Real | Logged | Issue |
|--------|------|--------|-------|
| DMs Sent | 13 | 14 | +1 false positive |
| Comments | 0 | 2 | +2 false positives |

### This_Photo5976
| Metric | Real | Logged | Issue |
|--------|------|--------|-------|
| DMs Sent | 0 | 0 | ✓ Correct |
| Comments | 9 | 15 | +6 false positives |

### ilovereddidotcom
| Metric | Real | Logged | Issue |
|--------|------|--------|-------|
| DMs Sent | 8 | 10 | +2 false positives |
| Comments | 7 | 0 | -7 missed |

**Root Cause**: Logging "success" before actual verification.

**Fix Applied**: `_verify_message_sent()` and `_verify_comment_posted()` check for OUR content on page before reporting success.

---

## Test Messages Found

Several "bananas" test messages were found in real DMs:
- Working_Golf72 → LopsidedAccess7004: "bananas"
- Working_Golf72 → BongDomrei: "bananas"
- ilovereddidotcom → AggressivePost4387: "bananas"

**Impact**: Test messages sent to real users during development.

**Recommendation**: Use `--dry-run` flag for testing.

---

## Current State

After migration, the state file contains:
- **37 users** tracked with their claiming account
- **2 threads** tracked
- All actions have proper timestamps and results

Run `python -m src.main --stats` to see current statistics.

---

## Verification Steps

1. **Run unit tests**:
   ```bash
   pytest tests/test_state.py -v
   ```

2. **Check atomic claim logic**:
   ```python
   from src.state import claim_user, ClaimStatus

   # First claim
   result = claim_user("testuser", "Account_A")
   assert result == ClaimStatus.CLAIMED

   # Same account again
   result = claim_user("testuser", "Account_A")
   assert result == ClaimStatus.ALREADY_CONTACTED

   # Different account
   result = claim_user("testuser", "Account_B")
   assert result == ClaimStatus.ALREADY_CLAIMED
   ```

3. **Verify state file structure**:
   ```bash
   python -c "import json; print(json.dumps(json.load(open('data/state.json')), indent=2)[:500])"
   ```

---

## Recommendations Going Forward

1. **Always use `--dry-run` first** when testing new features
2. **Run `--stats` before and after** each session to verify counts
3. **Check screenshots** in `data/` folder for any errors
4. **Run unit tests** before deploying changes: `pytest tests/ -v`
