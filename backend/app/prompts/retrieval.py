"""Prompts for retrieval."""

TREE_SELECT = (
    "You navigate a document outline to find where questions are answered. "
    "Return up to {max_sections} section ids (the value in square brackets) for each question, most "
    "relevant first. "
    "Prefer the most specific section; choose a parent only when the answer spans its children."
)

KG_ENTITIES = (
    "List the named things in the question: people, organizations, places, products, regulations, events, "
    "or key concepts. Copy each name as written. Return an empty list if there are none."
)

TABLE_OPERATION = (
    "You turn a question about a spreadsheet into one operation the system computes over every row. "
    "The spreadsheet:\n{schema}\n\n"
    "Pick sum, avg, count, min or max for a total, average, number of rows, smallest or largest value; add "
    "group_by for one result per value of a column. Pick top_n to rank rows by a column, and list to show "
    "the rows that match. Use filters to keep only the rows the question is about. Copy sheet and column "
    "names exactly as listed. Pick none when the question asks about one row's value or anything that is "
    "not a calculation, count, ranking or listing over the rows."
)
