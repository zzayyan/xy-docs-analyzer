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
