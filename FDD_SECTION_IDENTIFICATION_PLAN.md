# FDD Section Identification Plan

## 1. Objective

To create a reliable and automated process that accurately determines the starting and ending page numbers for the 23 standard sections of a Franchise Disclosure Document (FDD) using the JSON output from the MinerU document processing tool.

## 2. Guiding Frameworks

This plan was developed using the following mental models:

-   **COSTAR Framework:** To ensure all aspects of the problem are considered (Context, Objective, Success Criteria, Timeline, Actors, Resources).
-   **5 Whys:** To drill down to the root requirements and constraints of the problem, ensuring the solution is robust.
-   **Funnel-Based Filtering:** The core strategy involves starting with a wide pool of potential section headers and progressively applying stricter rules to funnel down to a single, high-confidence result for each of the 23 FDD Items.

## 3. Key Resources & Data

-   **Primary Input:** `layout_schema.json` or `Custom_Json_Schema_Generated_By_Gemini.json` - The structured JSON output from the MinerU tool, containing text blocks, their type (`title`, `text`), page number (`page_idx`), and location (`bbox`).
-   **Reference Data:** The list of 23 canonical FDD section headers, as determined by industry standards.

## 4. Canonical FDD Section Headers

The process will use the following standardized list of FDD section titles as the ground truth for matching.

1.  The Franchisor, its Predecessors, and its Affiliates
2.  Business Experience
3.  Litigation
4.  Bankruptcy
5.  Initial Fees
6.  Other Fees
7.  Estimated Initial Investment
8.  Restrictions on Sources of Products and Services
9.  Franchisee's Obligations
10. Financing
11. Franchisor's Assistance, Advertising, Computer Systems, and Training
12. Territory
13. Trademarks
14. Patents, Copyrights, and Proprietary Information
15. Obligation to Participate in the Actual Operation of the Franchise Business
16. Restrictions on What the Franchisee May Sell
17. Renewal, Termination, Transfer, and Dispute Resolution
18. Public Figures
19. Financial Performance Representations
20. Outlets and Franchisee Information
21. Financial Statements
22. Contracts
23. Receipt

## 5. Step-by-Step Implementation Plan

The process is designed as a multi-stage funnel that identifies, scores, and validates candidates for each FDD section.

### Step 5.1: Candidate Generation (Broad Funnel)

The first step is to scan the entire document and generate a comprehensive list of all potential section headers.

1.  **Define Candidate Structure:** Create a data class or dictionary to store information about each potential match:
    ```python
    class FddHeaderCandidate:
        item_number: int          # The FDD item number (1-23)
        text: str                 # The full text of the candidate header
        page_num: int             # The page index (`page_idx`)
        confidence_score: float   # A score from 0.0 to 1.0
        source_method: str        # How it was found (e.g., 'title_keyword', 'fuzzy_match')
    ```

2.  **Iterate Through Document:** Loop through each `page` in `pdf_info` and each `para_block` within the page.

3.  **Apply Identification Methods:**
    -   **Method A (High Confidence): Title + Keyword Match**
        -   Filter for blocks where `type == "title"`.
        -   Use a regular expression like `(?i)item\s*(\d{1,2})` to find the keyword "Item" followed by a number.
        -   Create a `FddHeaderCandidate` with a high confidence score (e.g., 0.9).

    -   **Method B (Medium Confidence): Text + Keyword Match**
        -   Filter for blocks where `type == "text"`.
        -   Apply the same regex as above. This catches headers that MinerU may have misclassified.
        -   Create a `FddHeaderCandidate` with a medium confidence score (e.g., 0.7).

    -   **Method C (Lower Confidence): Semantic & Fuzzy Matching**
        -   For each of the 23 canonical headers, perform a fuzzy match (e.g., using `thefuzz` library) and a cosine similarity search (e.g., using `sentence-transformers`) against all text and title blocks.
        -   If a match exceeds a high threshold (e.g., fuzzy ratio > 85 or similarity > 0.80), create a `FddHeaderCandidate`.
        -   Assign a lower confidence score (e.g., 0.6 for titles, 0.4 for text).

4.  **Group Candidates:** Store all generated candidates in a dictionary grouped by `item_number`.
    ```
    # Example Output of Step 1
    all_candidates = {
        5: [candidate_A, candidate_B],
        6: [candidate_C, candidate_D, candidate_E],
        ...
    }
    ```

### Step 5.2: Sequential Validation & Selection (Narrowing the Funnel)

This is the core logic of the plan. It enforces the sequential nature of FDDs to eliminate false positives.

1.  **Initialize Result Dictionary:** Create an empty dictionary `final_sections = {}` to store the single best candidate for each item.

2.  **Iterate and Validate (Item 1 to 23):** Loop from `i = 1` to `23`.
    -   **Get Candidates:** Retrieve the list of candidates for the current item `i` from `all_candidates`.
    -   **Apply Sequential Rule:**
        -   If `i > 1`, get the page number of the previously confirmed section: `previous_item_page = final_sections[i-1].page_num`.
        -   Filter the current candidates, keeping only those where `candidate.page_num >= previous_item_page`. This is the most critical validation step.
    -   **Handle No Valid Candidates:** If the filtered list is empty, it means the section was not found. Record this and continue to the next item.
    -   **Select Best Candidate:** From the remaining valid candidates, select the winner. The best candidate is the one with the **highest `confidence_score`**. If there's a tie in score, select the one that appears earliest in the document (lowest `page_num`).
    -   **Store Winner:** Add the winning candidate to the `final_sections` dictionary.

### Step 5.3: Post-Validation & Sanity Check

After the first pass, perform a final check to ensure the results are logical.

1.  **Global Order Check:** Iterate through `final_sections` from 1 to 22. For each item `i`, verify that `final_sections[i].page_num <= final_sections[i+1].page_num`.
2.  **Flag Errors:** If any item violates this order, flag it as a potential error. This indicates a complex document where the initial selection logic may have failed, possibly requiring manual review or a more advanced backtracking algorithm.

### Step 5.4: Final Output Generation

Transform the validated `final_sections` data into the desired output format.

1.  **Create Final List:** Initialize an empty list, `fdd_section_map`.
2.  **Generate Start/End Pages:**
    -   Iterate from `i = 1` to 23 through the `final_sections`.
    -   If item `i` was found:
        -   `start_page = final_sections[i].page_num`
        -   `end_page` is the `start_page` of the next found item (`i+1`).
        -   For the last found item, the `end_page` can be the last page of the document (`pdf_info[-1].page_idx`).
    -   Append a dictionary to `fdd_section_map`:
        ```json
        {
          "item": 19,
          "section_title": "Financial Performance Representations",
          "found_title": "ITEM 19 – FINANCIAL PERFORMANCE REPRESENTATIONS",
          "start_page": 150,
          "end_page": 165,
          "confidence": 0.9,
          "status": "Found"
        }
        ```

## 6. Future Enhancements

If this process needs to be made more robust, the following enhancements can be considered:

-   **Bounding Box Analysis:** Give preference to candidates located at the top of a page.
-   **Font/Style Analysis:** If font information is available, give higher scores to candidates with larger or bolded fonts, which are typical for headers.
-   **Backtracking Algorithm:** If the post-validation step (5.3) finds an error, implement a backtracking mechanism that revisits the problematic section and tries the second-best candidate to see if it resolves the ordering conflict.
-   **Table of Contents (TOC) Parsing:** If a TOC is detected on early pages, prioritize parsing it to get exact page numbers, which can be used to validate or override the findings from the main process.
