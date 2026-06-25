#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

user_problem_statement: |
  B107 "cost-code-first PO form" validation — Validate the frontend build
  against the running preview app. Test the cost-code picker (type-to-search
  combobox), line editor, and budget grid rendering. Login is cookie-based
  with test-pm@example.test credentials.
  
  NEW BUG FIX VERIFICATION: Blank quantity validation on PO create form.
  A line with BLANK quantity must be BLOCKED on the form with a friendly
  message (not silently submitted as a £0 line).

backend:
  - task: "N/A - Frontend-only validation"
    implemented: true
    working: "NA"
    file: "N/A"
    stuck_count: 0
    priority: "low"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "testing"
        comment: "B107 validation is frontend-only. Backend endpoints assumed working."

frontend:
  - task: "CHECK 1: Cost-code-first PO form renders"
    implemented: true
    working: true
    file: "frontend/src/pages/projects/PurchaseOrderForm.jsx, frontend/src/components/po/POLineEditor.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: "✅ PASS - PO form renders without blank screen or runtime error. Table header shows 'Cost code' (NOT 'Budget line'). No old budget-line dropdown found (data-testid='po-form-lines-budget-line-0' does not exist). Screenshot: check1-pass-form-rendered.png"
  
  - task: "CHECK 2: Cost-code picker is a type-to-search combobox"
    implemented: true
    working: true
    file: "frontend/src/components/budgets/CostCodePicker.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: "✅ PASS - Cost code picker trigger (data-testid='po-form-lines-cc-0-trigger') found and clickable. Popover opens with search input (data-testid='po-form-lines-cc-0-search'). 10 cost code options visible in list. Screenshot: check2-pass-popover-open.png"
  
  - task: "CHECK 3: Search filters on name/code"
    implemented: true
    working: true
    file: "frontend/src/components/budgets/CostCodePicker.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: "✅ PASS - Search filtering works correctly. 'drain' query returned 2 drainage-related options (e.g., 'EXT-01 External drainage (private)'). 'ACQ' query returned 3 ACQ-related options (ACQ-01 Land/site purchase price, ACQ-02, ACQ-03). Screenshots: check3-pass-drain-search.png, check3-pass-acq-search.png"
  
  - task: "CHECK 4: Selecting a code populates the trigger"
    implemented: true
    working: true
    file: "frontend/src/components/budgets/CostCodePicker.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: "✅ PASS - Clicking ACQ-01 option closed the popover and populated the trigger with 'ACQ-01 — Land / site purchase price'. Selection state persisted correctly. Screenshot: check4-pass-selected.png"
  
  - task: "CHECK 5: Add-line gives a second independent picker"
    implemented: true
    working: true
    file: "frontend/src/components/po/POLineEditor.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: "✅ PASS - '+ Add line' button (data-testid='po-form-lines-add') found and functional. Clicking it created a second line with independent cost code picker (data-testid='po-form-lines-cc-1-trigger'). Screenshot: check5-pass-second-line.png"
  
  - task: "CHECK 6: Budget grid renders"
    implemented: true
    working: true
    file: "frontend/src/pages/projects/BudgetDetail.jsx, frontend/src/components/budgets/BudgetJobCostingGrid.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: "✅ PASS - Budget detail page at /projects/{id}/budgets/{budget_id} renders successfully. 25 budget-related elements found. No runtime errors. Grid shows 'No budget lines for this scope' message (expected for this test budget with 0 unbudgeted lines). Screenshot: check6-pass-budget-grid.png"
  
  - task: "BUG FIX 1: ResizeObserver error overlay eliminated"
    implemented: true
    working: true
    file: "frontend/src/lib/resizeObserverFix.js, frontend/src/components/budgets/CostCodePicker.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: "✅ PASS - ResizeObserver loop guard successfully prevents error overlay. Tested: (A1) Form loads without overlay, (A2) Picker opens without overlay, (A3) Typing 'EXT' filters 4 options without overlay, (A4) Selecting EXT-01 populates trigger without overlay. Console shows NO ResizeObserver errors and NO uncaught JavaScript errors. Fix implemented via side-effect import '@/lib/resizeObserverFix' which wraps ResizeObserver callbacks in requestAnimationFrame. Screenshots: a1-pass-form-loaded.png, a2-pass-picker-opened.png, a3-pass-search-filtered.png, a4-pass-option-selected.png"
  
  - task: "BUG FIX 2: Budget dropdown replaces paste field"
    implemented: true
    working: true
    file: "frontend/src/pages/projects/PurchaseOrderForm.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: "✅ PASS - Budget field is now a <select> dropdown (data-testid='po-form-budget-id') with readable labels. (B1) Confirmed <select> tag (not text input), no UUID/paste placeholder. (B2) Dropdown shows readable label 'R7 spot-check (v1) — Active · current' (not raw UUID). (B3) Single budget auto-selected correctly. (B4) Dropdown options screenshot captured. Auto-selection logic works: single budget chosen outright, otherwise prefers current Active budget. Screenshots: b1-pass-budget-dropdown.png, b3-budget-selected.png, b4-dropdown-options.png"
  
  - task: "PO Draft Creation with Number Prefix"
    implemented: true
    working: true
    file: "frontend/src/pages/projects/PurchaseOrderForm.jsx, frontend/src/components/po/SupplierSelect.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: "✅ PASS - Purchase Order draft creation flow tested end-to-end. Form filled with: Supplier='TEST Supplier — B107' (via data-testid='po-form-supplier-select'), Budget='R7 spot-check (v1)' (auto-selected), Cost code='EXT-01 External drainage', Qty=1, Rate=100. Draft created successfully with PO number 'PO-0002'. Navigation to detail page successful (/purchase-orders/4ed0255d-02bd-44d7-9d41-f4cd4481509d). NO error about 'Project has no default po number prefix configured'. NO runtime error overlay. Form calculations correct (Net £100.00, VAT £20.00, Gross £120.00). Console: 4 × 401 auth errors (non-blocking). PO number prefix configuration is working correctly. Screenshots: po-form-filled.png, po-detail-page.png"
  
  - task: "BUG FIX 3: Blank quantity validation on PO form"
    implemented: true
    working: true
    file: "frontend/src/lib/poPayload.js, frontend/src/pages/projects/PurchaseOrderForm.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: "✅ PASS - Blank quantity validation working correctly. PART 1: Blank quantity field is BLOCKED with error message 'Line 1: quantity is required and must be greater than 0.' (data-testid='po-form-error'). Form does NOT navigate away, stays on /new URL. OPTIONAL: Quantity = 0 also correctly blocked with same error message. PART 2: Valid quantity (1) and unit rate (100) allows successful PO creation. Draft created with PO number 'PO-0001', navigated to detail page (/purchase-orders/dd3d7174-8fc1-4293-a9b6-fdf4cd00052b). Form calculations correct (Net £100.00, VAT £20.00, Gross £120.00). NO runtime error overlay at any point. Console: 4 × 401 auth errors (non-blocking). Validation logic in validatePoLines() function checks: qtyBlank || !Number.isFinite(qty) || qty <= 0. Screenshots: part1-before-submit-blank-qty.png, part1-validation-error-blank-qty.png, optional-validation-error-qty-zero.png, part2-before-submit-valid.png, part2-po-detail-page.png"
  
  - task: "BILL-ENTRY UI: Force-the-choice PO validation (7 test items)"
    implemented: true
    working: true
    file: "frontend/src/components/actuals/CommitmentLinePicker.jsx, frontend/src/components/actuals/CreateActualSheet.jsx, frontend/src/components/actuals/BudgetLinePicker.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "testing"
        comment: "❌ ENVIRONMENT/DATA SETUP ISSUE - Testing BLOCKED. Project d2a3729a-7ec4-408a-95d5-783520d5ff97 has NO active or locked budget. Login successful (test-pm@example.test, no MFA). Form loaded successfully. Budget line picker shows amber warning: 'No active or locked budget on this project. Create or activate a budget before posting actuals.' Cannot test any of the 7 items (GATE, REMAINING DISPLAY, STANDALONE, EMPTY CASE, RESET, SUBMIT PAYLOADS, FULLY-INVOICED) because budget line selection is prerequisite. CODE REVIEW: ✅ CommitmentLinePicker.jsx correctly implements force-the-choice logic with proper data-testids. ✅ CreateActualSheet.jsx validation gate (lines 127-136) correctly blocks submit without PO choice. ✅ BudgetLinePicker.jsx correctly shows empty state when no budget exists. All required data-testids present. REQUIRED ACTION: Activate budget on project with budget lines 'Groundworks' (2 PO lines: £6,000 remaining + £0 fully-invoiced), 'Roofing' (1 PO line: £8,000 remaining), 'Landscaping' (0 PO lines). OR provide different project ID with correct test data. This is test data issue, NOT code defect. Screenshots: 01-form-loaded.png (amber warning visible), error-screenshot.png (form state)."
      - working: true
        agent: "testing"
        comment: "✅ ALL 7 TEST ITEMS PASSED - Force-the-choice PO validation working correctly. Test data setup resolved (budget activated on project d2a3729a-7ec4-408a-95d5-783520d5ff97). Login: test-pm@example.test (no MFA). TEST RESULTS: (1) GATE ✅ PASS - Form blocked without PO choice, error message: 'Choose the purchase order this bill pays, or tick 'No PO available'.' Form stayed open, no navigation. (2) REMAINING DISPLAY ✅ PASS - Found exact text '£6,000.00 remaining of £10,000.00' on selectable PO line. (3) STANDALONE ✅ PASS - Selected £6,000 PO line, then clicked 'No PO available'. PO line deselected correctly. Form submitted successfully. (4) EMPTY CASE ✅ PASS - Landscaping shows empty note: 'No open purchase orders on this budget line — this will be recorded as a standalone cost.' Form submitted successfully (auto-treated as standalone). (5) RESET ✅ PASS - Changed budget line from Groundworks to Roofing. Reset note displayed: 'Purchase order choice reset — budget line changed.' Roofing PO line '£8,000.00 remaining of £8,000.00' shown and unselected. (6) SUBMIT PAYLOADS ✅ PASS - STANDALONE payload: NO 'linked_commitment_id' key present (correct). PO-LINE payload: 'linked_commitment_id' = '2720d328-0776-4738-9fc1-9c934a555e0b' (UUID present, correct). (7) FULLY-INVOICED ✅ PASS - Second PO line on Groundworks shows '(fully invoiced)' and '£0.00 remaining of £5,000.00'. Line is greyed (opacity-50 class). Radio is disabled. Clicking radio does NOT select it (remains unselected). All data-testids present and functional. No console errors. Screenshots: test1-pass-blocked.png, test2-pass.png, test3-pass.png, test4-empty.png, test5-pass.png, test7-pass.png. CONCLUSION: Bill-entry UI force-the-choice validation is PRODUCTION-READY."

metadata:
  created_by: "testing_agent"
  version: "107.3"  # B107 validation + blank quantity bug fix + bill-entry UI pre-check COMPLETE
  test_sequence: 4
  run_ui: true

test_plan:
  current_focus:
    - "Bill-entry UI testing COMPLETE - ALL 7 ITEMS PASSED"
    - "All B107 checks completed and passed"
    - "Bug fix verification completed and passed"
    - "PO draft creation with number prefix - COMPLETED AND PASSED"
    - "Blank quantity validation bug fix - COMPLETED AND PASSED"
  stuck_tasks: []
  test_all: true
  test_priority: "high_first"

agent_communication:
  - agent: "testing"
    message: |
      ❌ ENVIRONMENT ISSUE: Cannot proceed with "force-the-choice" bill-entry UI testing
      
      PROBLEM: test-finance@example.test user has MFA (Two-Factor Authentication) enabled
      
      DETAILS:
      - Review request specifies: "LOGIN (cookie-based, no MFA): email = test-finance@example.test"
      - Expected: User should NOT require MFA for headless testing
      - Actual: After successful login POST, app redirects to "Two-factor verification" page
      - Screenshot evidence: 00-login-filled.png shows credentials entered, error-screenshot.png shows MFA prompt
      
      IMPACT:
      - Cannot complete any of the 7 test items for the bill-entry UI
      - Headless Playwright testing cannot proceed past MFA screen (requires manual TOTP code entry)
      
      REQUIRED ACTION:
      1. Disable MFA for test-finance@example.test user in the preview environment, OR
      2. Provide alternative test credentials with finance permissions and no MFA, OR
      3. Provide MFA bypass mechanism for automated testing
      
      NOTE: This is an environment configuration issue, not a feature failure. The bill-entry UI code
      (CommitmentLinePicker.jsx, CreateActualSheet.jsx) appears correctly implemented based on code review.
  
  - agent: "testing"
    message: |
      ❌ ENVIRONMENT/DATA SETUP ISSUE: Bill-entry UI testing BLOCKED - No active budget on test project
      
      PROBLEM: Project d2a3729a-7ec4-408a-95d5-783520d5ff97 has NO active or locked budget
      
      DETAILS:
      - Login: test-pm@example.test / TestUser-Dev-2026! ✅ SUCCESS (no MFA)
      - Navigation: /projects/d2a3729a-7ec4-408a-95d5-783520d5ff97/actuals/new ✅ SUCCESS
      - Form loaded: "Create Draft actual" sheet opened ✅ SUCCESS
      - Budget line picker: Shows amber warning "No active or locked budget on this project. Create or activate a budget before posting actuals."
      - Expected: Budget lines "Groundworks", "Roofing", "Landscaping" with configured PO lines
      - Actual: NO budget lines available (no active/locked budget exists)
      
      IMPACT:
      - Cannot test any of the 7 test items (all require selecting a budget line first)
      - Budget line picker does NOT render dropdown when no budget exists (by design, see BudgetLinePicker.jsx lines 48-57)
      - Purchase order section shows "Select a budget line first." (cannot proceed)
      
      CODE REVIEW FINDINGS:
      ✅ CommitmentLinePicker.jsx: Correctly implements force-the-choice logic with proper data-testids
      ✅ CreateActualSheet.jsx: Validation gate at lines 127-136 correctly blocks submit without PO choice
      ✅ BudgetLinePicker.jsx: Correctly shows empty state when no active/locked budget exists
      ✅ All required data-testids present: commitment-picker, commitment-picker-empty, commitment-picker-line-{id}, commitment-picker-standalone, commitment-picker-error, commitment-reset-note
      
      REQUIRED ACTION:
      1. Activate a budget on project d2a3729a-7ec4-408a-95d5-783520d5ff97 with budget lines:
         - "Groundworks" with 2 PO lines (one selectable £6,000 remaining, one fully-invoiced £0)
         - "Roofing" with 1 PO line (£8,000 remaining)
         - "Landscaping" with 0 PO lines (empty case)
      2. OR provide a different project ID that has the correct test data setup
      3. OR manually set up the test data as specified in the review request
      
      SCREENSHOT EVIDENCE:
      - 01-form-loaded.png: Shows amber warning "No active or locked budget on this project"
      - error-screenshot.png: Shows form state when budget picker cannot render
      
      NOTE: This is a test data/environment setup issue, NOT a code defect. The bill-entry UI code appears correctly implemented based on code review.
      
  - agent: "testing"
    message: |
      ✅ BILL-ENTRY UI PRE-CHECK COMPLETE — ALL 7 TEST ITEMS PASSED
      
      Tested against: https://prod-property-hub.preview.emergentagent.com
      Login: test-pm@example.test / TestUser-Dev-2026! (no MFA)
      Project: d2a3729a-7ec4-408a-95d5-783520d5ff97
      Form URL: /projects/d2a3729a-7ec4-408a-95d5-783520d5ff97/actuals/new
      
      ═══════════════════════════════════════════════════════════════════════════
      TEST RESULTS SUMMARY
      ═══════════════════════════════════════════════════════════════════════════
      
      ✅ TEST 1: GATE - Block submit without PO choice
         - Budget line: "1. Groundworks" selected
         - All required fields filled (Entity, Source type, Description, Net=1000, Supplier)
         - NO PO line selected, NO "No PO available" ticked
         - Clicked "Create Draft" button
         - RESULT: Form BLOCKED (stayed open, no navigation)
         - Error message displayed: "Choose the purchase order this bill pays, or tick 'No PO available'."
         - Screenshot: test1-pass-blocked.png
      
      ✅ TEST 2: REMAINING DISPLAY - Verify £6,000 remaining text
         - Found 2 PO lines on "Groundworks"
         - PO Line 1: "PO-DEMO-A-4a2a73 · Demo line 1" with "£6,000.00 remaining of £10,000.00"
         - EXACT TEXT MATCH: "£6,000.00 remaining of £10,000.00" ✅
         - Screenshot: test2-pass.png
      
      ✅ TEST 3: STANDALONE - Select PO then switch to "No PO available"
         - Step 1: Clicked selectable £6,000 PO line radio → selected ✅
         - Step 2: Clicked "No PO available" radio → PO line deselected, standalone selected ✅
         - Step 3: Clicked "Create Draft" → Form submitted successfully (form closed) ✅
         - Screenshot: test3-pass.png
      
      ✅ TEST 4: EMPTY CASE - Landscaping auto-treated as standalone
         - Budget line: "3. Landscaping" selected
         - Empty note displayed: "No open purchase orders on this budget line — this will be recorded as a standalone cost." ✅
         - NO radio list shown (correct behavior for empty case)
         - Filled required fields and clicked "Create Draft"
         - RESULT: Form submitted successfully (auto-treated as standalone) ✅
         - Screenshot: test4-empty.png
      
      ✅ TEST 5: RESET - Change budget line clears PO selection
         - Selected "Groundworks" and clicked £6,000 PO line radio
         - Changed budget line to "2. Roofing"
         - Reset note displayed: "Purchase order choice reset — budget line changed." ✅
         - Roofing PO line shown: "PO-DEMO-B-4a2a73 · Demo line 1" with "£8,000.00 remaining of £8,000.00"
         - Roofing PO line radio is UNSELECTED (previous selection cleared) ✅
         - Screenshot: test5-pass.png
      
      ✅ TEST 6: SUBMIT PAYLOADS - Capture POST bodies
         
         6a) STANDALONE (Groundworks + "No PO available"):
         POST /api/v1/actuals
         Body: {
           "project_id": "d2a3729a-7ec4-408a-95d5-783520d5ff97",
           "budget_line_id": "3ac4e2c0-0d00-465a-8c32-b53f75ef2ef7",
           "entity_id": "4a9736e1-e223-49f4-8c43-5db2d26f7924",
           "source_type": "Manual_Entry",
           "transaction_date": "2026-06-25",
           "description": "standalone",
           "net_amount": "1000",
           "vat_amount": "0",
           "vat_rate_pct": "20",
           "is_vat_recoverable": true,
           "currency": "GBP",
           "supplier_name_snapshot": "Standalone",
           "is_cis_applicable": false
         }
         ✅ PASS: NO "linked_commitment_id" key present (correct for standalone)
         
         6b) PO-LINE (Groundworks + select £6,000 line):
         POST /api/v1/actuals
         Body: {
           "project_id": "d2a3729a-7ec4-408a-95d5-783520d5ff97",
           "budget_line_id": "3ac4e2c0-0d00-465a-8c32-b53f75ef2ef7",
           "entity_id": "4a9736e1-e223-49f4-8c43-5db2d26f7924",
           "source_type": "Manual_Entry",
           "transaction_date": "2026-06-25",
           "description": "po-line",
           "net_amount": "2000",
           "vat_amount": "0",
           "vat_rate_pct": "20",
           "is_vat_recoverable": true,
           "currency": "GBP",
           "supplier_name_snapshot": "PO Supplier",
           "is_cis_applicable": false,
           "linked_commitment_id": "2720d328-0776-4738-9fc1-9c934a555e0b"
         }
         ✅ PASS: "linked_commitment_id" = "2720d328-0776-4738-9fc1-9c934a555e0b" (UUID present, correct)
      
      ✅ TEST 7: FULLY-INVOICED - Verify greyed/disabled £0 line
         - Found fully-invoiced line on "Groundworks": "PO-DEMO-A-4a2a73 · Demo line 2(fully invoiced)"
         - Text shows: "£0.00 remaining of £5,000.00" ✅
         - Line has "opacity-50" class (greyed) ✅
         - Radio input is DISABLED ✅
         - Attempted to click radio (force=True) → Radio remains UNSELECTED ✅
         - Screenshot: test7-pass.png
      
      ═══════════════════════════════════════════════════════════════════════════
      TECHNICAL VALIDATION
      ═══════════════════════════════════════════════════════════════════════════
      
      Data-testids verified:
      ✅ create-actual-form (form container)
      ✅ budget-line-picker (native <select>)
      ✅ commitment-picker (PO section container)
      ✅ commitment-picker-line-{id} (PO line rows with radio inputs)
      ✅ commitment-picker-standalone ("No PO available" row with radio)
      ✅ commitment-picker-error (inline error message)
      ✅ commitment-reset-note (reset note on budget line change)
      ✅ commitment-picker-empty (empty state note for Landscaping)
      ✅ create-actual-entity (Radix Select for Entity)
      ✅ create-actual-source-type (Radix Select for Source type)
      ✅ create-actual-description (Textarea)
      ✅ create-actual-net (Input for Net amount)
      ✅ create-actual-supplier (Input for Supplier name)
      ✅ create-actual-submit (Submit button)
      
      Budget lines found:
      - "1. Groundworks" (value: 3ac4e2c0-0d00-465a-8c32-b53f75ef2ef7)
        → 2 PO lines: £6,000 remaining (selectable) + £0 fully-invoiced (disabled)
      - "2. Roofing" (value: a5536e16-38a5-4c7d-bcc4-5da18d6f3c88)
        → 1 PO line: £8,000 remaining (selectable)
      - "3. Landscaping" (value: 41e384da-0e70-4859-97a7-ac6061096695)
        → 0 PO lines (empty case, auto-standalone)
      
      Console: No JavaScript runtime errors detected
      Network: All POST requests to /api/v1/actuals captured successfully
      
      ═══════════════════════════════════════════════════════════════════════════
      CONCLUSION
      ═══════════════════════════════════════════════════════════════════════════
      
      The "force-the-choice" bill-entry UI is PRODUCTION-READY. All 7 test items passed:
      1. ✅ GATE validation blocks submit without PO choice
      2. ✅ REMAINING DISPLAY shows correct £6,000 text
      3. ✅ STANDALONE radio deselects PO and submits successfully
      4. ✅ EMPTY CASE auto-treats as standalone with correct note
      5. ✅ RESET clears PO selection when budget line changes
      6. ✅ SUBMIT PAYLOADS correct (standalone omits linked_commitment_id, PO-line includes UUID)
      7. ✅ FULLY-INVOICED line is greyed, disabled, and cannot be selected
      
      No critical issues found. Feature is ready for production deployment.
      
  - agent: "testing"
    message: |
      B107 "cost-code-first PO form" validation COMPLETE — ALL 6 CHECKS PASSED.
      
      Tested against: https://prod-property-hub.preview.emergentagent.com
      Login: test-pm@example.test / TestUser-Dev-2026! (cookie-based, no MFA)
      
      Project ID: b2a265ef-dc30-4779-96f6-e139d1881e07
      Budget ID: 5db0b1ae-e9be-474d-8044-be06b020e61f
      
      ✅ CHECK 1 PASS: PO form renders with "Cost code" header (not "Budget line")
      ✅ CHECK 2 PASS: Cost code picker is a type-to-search combobox with search input
      ✅ CHECK 3 PASS: Search filters work ("drain" → 2 results, "ACQ" → 3 results)
      ✅ CHECK 4 PASS: Selecting ACQ-01 populates trigger and closes popover
      ✅ CHECK 5 PASS: Add line creates second independent picker
      ✅ CHECK 6 PASS: Budget grid renders cleanly (25 elements, no errors)
      
      Console: 5 × 401 resource loading errors (non-blocking, likely background API calls)
      No JavaScript runtime errors detected.
      
      Screenshots saved:
      - check1-pass-form-rendered.png
      - check2-pass-popover-open.png
      - check3-pass-drain-search.png
      - check3-pass-acq-search.png
      - check4-pass-selected.png
      - check5-pass-second-line.png
      - check6-pass-budget-grid.png
      
      Build B107 is PRODUCTION-READY for this feature set.
  
  - agent: "testing"
    message: |
      BUG FIX VERIFICATION COMPLETE — BOTH FIXES VALIDATED SUCCESSFULLY.
      
      Tested against: https://prod-property-hub.preview.emergentagent.com
      Login: test-pm@example.test / TestUser-Dev-2026! (no MFA, preferred for headless)
      Note: test-admin@example.test requires MFA setup which blocks headless testing
      
      Target: /projects/b2a265ef-dc30-4779-96f6-e139d1881e07/purchase-orders/new
      
      ✅ FIX 1 PASS: ResizeObserver error overlay eliminated
        - A1: Form loads without error overlay ✅
        - A2: Cost-code picker opens without error overlay ✅
        - A3: Typing "EXT" filters correctly (4 options) without error overlay ✅
        - A4: Selecting EXT-01 populates trigger without error overlay ✅
        - Console: No ResizeObserver errors detected ✅
        - Console: No uncaught JavaScript errors ✅
      
      ✅ FIX 2 PASS: Budget dropdown replaces paste field
        - B1: Budget field is <select> dropdown (not text input) ✅
        - B2: Dropdown shows readable label "R7 spot-check (v1) — Active · current" (not raw UUID) ✅
        - B3: Single budget auto-selected correctly ✅
        - B4: Dropdown options screenshot captured ✅
      
      Console: 5 × 401 errors (non-blocking, likely background API calls)
      
      Screenshots saved:
      - a1-pass-form-loaded.png
      - a2-pass-picker-opened.png
      - a3-pass-search-filtered.png
      - a4-pass-option-selected.png
      - b1-pass-budget-dropdown.png
      - b3-budget-selected.png
      - b4-dropdown-options.png
      
      BOTH BUG FIXES ARE PRODUCTION-READY.
  
  - agent: "testing"
    message: |
      PO DRAFT CREATION TEST COMPLETE — ✅ PASS
      
      Tested: Purchase Order draft creation with PO number prefix configuration
      URL: /projects/b2a265ef-dc30-4779-96f6-e139d1881e07/purchase-orders/new
      Login: test-pm@example.test / TestUser-Dev-2026! (no MFA)
      
      TEST STEPS EXECUTED:
      1. ✅ Supplier selected: "TEST Supplier — B107" (via data-testid="po-form-supplier-select")
      2. ✅ Budget auto-selected: "R7 spot-check (v1) — Active · current"
      3. ✅ Cost code selected: "EXT-01 — External drainage (private)"
      4. ✅ Quantity entered: 1
      5. ✅ Unit rate entered: 100
      6. ✅ Form submitted via "Create draft" button
      
      RESULTS:
      ✅ Draft created successfully
      ✅ Navigation to PO detail page: /purchase-orders/4ed0255d-02bd-44d7-9d41-f4cd4481509d
      ✅ PO Number assigned: PO-0002
      ✅ NO error about "Project has no default 'po' number prefix configured"
      ✅ NO runtime error overlay at any point
      ✅ Form calculations correct: Net £100.00, VAT £20.00, Gross £120.00
      
      Console: 4 × 401 errors (auth/me, auth/refresh - non-blocking background polling)
      No JavaScript runtime errors detected.
      
      Screenshots saved:
      - po-form-filled.png (form with all fields populated)
      - po-detail-page.png (PO-0002 detail page showing Draft status)
      
      CONCLUSION: PO number prefix configuration is working correctly. The missing prefix issue has been resolved.
  
  - agent: "testing"
    message: |
      BLANK QUANTITY VALIDATION BUG FIX VERIFICATION COMPLETE — ✅ ALL TESTS PASSED
      
      Tested against: https://prod-property-hub.preview.emergentagent.com
      Login: test-pm@example.test / TestUser-Dev-2026! (no MFA)
      Target: /projects/b2a265ef-dc30-4779-96f6-e139d1881e07/purchase-orders/new
      
      ═══════════════════════════════════════════════════════════════════════════
      PART 1: BLANK QUANTITY IS BLOCKED ✅ PASS
      ═══════════════════════════════════════════════════════════════════════════
      
      TEST STEPS:
      1. ✅ Selected supplier: "TEST Supplier — B107"
      2. ✅ Budget auto-selected: "R7 spot-check (v1) — Active · current"
      3. ✅ Selected cost code: "EXT-01 — External drainage (private)"
      4. ✅ LEFT quantity field BLANK (empty string)
      5. ✅ LEFT unit rate field BLANK
      6. ✅ Clicked "Create draft" button
      
      RESULTS:
      ✅ Form submission BLOCKED (no navigation occurred)
      ✅ Error message displayed (data-testid="po-form-error"):
         "Line 1: quantity is required and must be greater than 0."
      ✅ URL remained on /new form (did not navigate away)
      ✅ No PO was created (confirmed by staying on form)
      ✅ Error message is user-friendly and clear
      
      ═══════════════════════════════════════════════════════════════════════════
      OPTIONAL TEST: QUANTITY = 0 IS BLOCKED ✅ PASS
      ═══════════════════════════════════════════════════════════════════════════
      
      TEST STEPS:
      1. ✅ Set quantity = 0 (explicitly)
      2. ✅ Clicked "Create draft" button
      
      RESULTS:
      ✅ Form submission BLOCKED
      ✅ Same error message displayed:
         "Line 1: quantity is required and must be greater than 0."
      ✅ Validation correctly treats qty=0 as invalid (must be > 0)
      
      ═══════════════════════════════════════════════════════════════════════════
      PART 2: VALID QUANTITY ALLOWS SUBMISSION ✅ PASS
      ═══════════════════════════════════════════════════════════════════════════
      
      TEST STEPS:
      1. ✅ Set quantity = 1
      2. ✅ Set unit rate = 100
      3. ✅ Clicked "Create draft" button
      
      RESULTS:
      ✅ Draft created successfully
      ✅ Navigation to PO detail page: /purchase-orders/dd3d7174-8fc1-4293-a9b6-fdf4cd00052b
      ✅ PO Number assigned: PO-0001
      ✅ Status: Draft
      ✅ Line details correct: Qty 1.0000, Rate £100.00, VAT 20.00%
      ✅ Form calculations correct: Net £100.00, VAT £20.00, Gross £120.00
      ✅ NO error messages on detail page
      ✅ NO runtime error overlay at any point
      
      ═══════════════════════════════════════════════════════════════════════════
      TECHNICAL VALIDATION
      ═══════════════════════════════════════════════════════════════════════════
      
      Validation Logic (frontend/src/lib/poPayload.js):
      - validatePoLines() function checks:
        • qtyBlank: quantity === '' || quantity === null || quantity === undefined
        • !Number.isFinite(qty): ensures numeric value
        • qty <= 0: ensures positive quantity
      - Error message format: "Line {N}: quantity is required and must be greater than 0."
      - Form-level validation in PurchaseOrderForm.jsx (line 114-115):
        • const lineError = validatePoLines(lines);
        • if (lineError) { setError(lineError); return; }
      
      Console Analysis:
      ✅ No JavaScript runtime errors
      ✅ No error overlay at any point
      ⚠️ 4 × 401 auth errors (non-blocking, expected background polling)
      
      Screenshots saved:
      - part1-before-submit-blank-qty.png (form with blank quantity)
      - part1-validation-error-blank-qty.png (error message displayed)
      - optional-validation-error-qty-zero.png (qty=0 blocked)
      - part2-before-submit-valid.png (form with valid data)
      - part2-po-detail-page.png (PO-0001 detail page)
      
      ═══════════════════════════════════════════════════════════════════════════
      CONCLUSION: BUG FIX IS PRODUCTION-READY
      ═══════════════════════════════════════════════════════════════════════════
      
      The blank quantity validation is working perfectly:
      • Blank quantities are blocked with a clear, friendly error message
      • Zero quantities are also blocked (qty must be > 0)
      • Valid quantities allow successful PO creation
      • No silent £0 lines can be created
      • Form UX is correct (stays on form when validation fails)
      • No runtime errors or overlays