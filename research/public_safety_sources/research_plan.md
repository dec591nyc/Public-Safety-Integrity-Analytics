# Public Safety & Integrity Data Source Research Plan

## Main Question

Evaluate the feasibility of dynamic web scraping and rule-based parsing to extract core demographic metrics (Age, Gender, Income, Birth-City, Occupation, Education-Level) from Judicial Yuan judgments, and design a phased integration with the Central Election Commission (CEC) candidate data.

## Key Subtopics

### 1. Judicial Yuan Public Search Scraping Feasibility
- Expected: Analyze the structure of the Judicial Yuan judgment search platform (`https://judgment.judicial.gov.tw/`). Identify rate-limiting thresholds, cookie requirements, request parameters, and how to query recent judgments programmatically.

### 2. Demographic Regex & Parsing Accuracy
- Expected: Evaluate common syntactic patterns used by judges to describe a defendant's background. Develop and test regular expressions for:
  - Age (e.g., `民國XX年生`, `XX歲`)
  - Gender (e.g., `男`, `女`)
  - Occupation (e.g., `業X`, `臨時工`)
  - Education (e.g., `XX學校畢業`, `教育程度為XX`)
  - Income (e.g., `家庭經濟狀況勉可維持`, `家庭生活狀況貧寒`)

### 3. CEC Candidate Name Matching Heuristics
- Expected: Profile the CEC candidate JSON datasets. Establish name-matching criteria to link case defendants with political party candidates while minimizing false positives from name collisions (e.g., matching by county/district or relative age).

### 4. Dynamic Daily Routine Pipelines
- Expected: Design a daily scheduled crawler in Python that only checks for newly published rulings, indexes demographic counters, links opinions, and flushes cache.

## Synthesis

Compare the parsing confidence, storage savings, and legal compliance of this dynamic scraping strategy against the legacy bulk RAR download approach. Propose a finalized schema and a lightweight dashboard layout.\n