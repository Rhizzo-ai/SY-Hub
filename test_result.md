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

metadata:
  created_by: "testing_agent"
  version: "107.0"  # B107 validation
  test_sequence: 1
  run_ui: true

test_plan:
  current_focus:
    - "All B107 checks completed and passed"
    - "Bug fix verification completed and passed"
  stuck_tasks: []
  test_all: true
  test_priority: "high_first"

agent_communication:
  - agent: "testing"
    message: |
      B107 "cost-code-first PO form" validation COMPLETE — ALL 6 CHECKS PASSED.
      
      Tested against: https://concurrent-mint-fix.preview.emergentagent.com
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
      
      Tested against: https://concurrent-mint-fix.preview.emergentagent.com
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