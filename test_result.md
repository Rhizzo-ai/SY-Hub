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
  Chat 20 / Prompt 2.5D — Implement B38 "AI Capture Cost Dashboard" per
  /app/docs/chat-20-build-pack-v-final.md.
  Scope: backend perm + GET /v1/ai-capture-jobs/stats endpoint, lazy-loaded
  /ai-capture/cost dashboard page, ~24 Jest tests, ~11 pytest tests.
  Zero LOC change to existing AI capture pipeline or actuals state machine.

backend:
  - task: "Migration 0026 — ai_capture.view_costs permission"
    implemented: true
    working: "NA"  # PostgreSQL not in Emergent container; operator-side verification
    file: "backend/alembic/versions/0026_ai_capture_costs_perm.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false  # Will be verified by operator (Rhys) locally
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Migration writes ai_capture / view_costs ENUM extensions, permission row, role grants for super_admin/director/finance, and audit row. Idempotent. Operator runs `alembic upgrade head` locally — Emergent container has no Postgres."
  - task: "GET /v1/ai-capture-jobs/stats endpoint + compute_capture_stats service"
    implemented: true
    working: "NA"
    file: "backend/app/routers/ai_capture.py, backend/app/services/ai_capture.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Endpoint gated by require_permission('ai_capture.view_costs'). Service aggregates totals (SUM/AVG), zero-filled daily series, by-status buckets (Completed/Failed/Discarded only). London-tz bucketing. Integer pence over the wire."
  - task: "test_ai_capture_stats.py — 15 pytest tests"
    implemented: true
    working: "NA"
    file: "backend/tests/test_ai_capture_stats.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Covers permissions (401/403/200), aggregation correctness, validation, seed_rbac catalogue. ruff lint passes. Operator runs against local PostgreSQL."

frontend:
  - task: "Cost dashboard data layer + page + components"
    implemented: true
    working: true
    file: "frontend/src/pages/AICaptureCosts.jsx + components/ai-capture/Cost*.jsx + DateRangePicker.jsx + lib/api/aiCapture.js + hooks/aiCapture.js + lib/aiCaptureCapability.js + lib/schemas/aiCaptureStats.js"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "main"
        comment: "Lazy-loaded via React.lazy with webpackChunkName. Hooks-above-perm-gate (I13). 33 new Jest tests pass (151 total, up from 118). Bundle main 423.99 -> 424.16 kB gz (+0.17, well under +3 kB gate). Recharts split into shared chunk 52. ESLint clean."
  - task: "Route + AppShell NAV entry"
    implemented: true
    working: true
    file: "frontend/src/App.js, frontend/src/components/AppShell.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "main"
        comment: "/ai-capture/cost route placed BEFORE /ai-capture/:jobId so literal segment doesn't collide. NAV entry uses requires: 'ai_capture.view_costs'."

metadata:
  created_by: "main_agent"
  version: "20.0"  # Chat 20
  test_sequence: 0
  run_ui: false

test_plan:
  current_focus:
    - "Operator-side: alembic upgrade head + pytest tests/test_ai_capture_stats.py"
    - "Operator-side: Playwright smoke @ /ai-capture/cost"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
  - agent: "main"
    message: |
      Chat 20 / Prompt 2.5D / B38 implementation complete on Emergent side.
      
      Bundle gates: PASS (main +0.17 kB gz delta; 12.84 kB headroom under 437 kB cap).
      Jest: 151/151 passing (118 baseline + 33 new).
      ESLint + ruff: clean on new files.
      
      Backend verification (alembic + pytest) must run on operator's local
      machine — Emergent container has no PostgreSQL. Build pack expects
      operator (Rhys) to run spot-check on GitHub + local Playwright smoke
      after push to main, per §R8.
      
      No `deep_testing_backend_v2` invocation in this chat: the test suite
      requires PostgreSQL which isn't available here. The new
      `test_ai_capture_stats.py` is structured to run identically to
      existing `test_ai_capture.py` against a live backend + DB.
      
      Closing summary in /app/docs/chat-summaries/chat-20-closing.md.