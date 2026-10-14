"""Prompts for Table Extraction."""

PROPOSE = (
    "You design the columns of a table from a plain-language request. Propose between two and six "
    "columns, each with a short name and a one-sentence description of what belongs in it. Name and "
    "describe the columns in the same language as the request. Where the document quoted below "
    "already has a word for something, use that word. Do not invent columns the request does not ask "
    "for."
)

SUGGEST = (
    "You propose tables worth pulling out of a document, from an outline and a few passages of it. "
    "Give three tables: things the document lists over and over -- obligations, parties, dates, "
    "amounts, articles -- not a summary of it. Each table has a short title, one plain sentence "
    "asking for what it collects, and between two and six columns, each column with a short name and "
    "a one-sentence description. Write all of it in the language of the document."
)

EXTRACT = (
    "You extract table rows from one passage of a document, for a request. Return one row per item in "
    "the passage that the request asks for, and no rows at all if the passage has none. Something that "
    "only looks like such an item -- a heading, a menu entry, an example of something else -- is not "
    "one. Give one value per column, in the order the columns are listed. Quote each value exactly as "
    "the passage writes it, in the language of the passage -- do not translate, summarise or infer. "
    "Leave a value empty when the passage does not state it; never fill it with a guess or with words "
    "like \"not stated\"."
)

EXTRACT_TABLE = (
    "You extract table rows from one table of a document, given in Markdown, for a request. It may be only "
    "some of the table's rows, under its header. Map every row of the table that the request asks for to "
    "the requested columns -- one row out per matching table row -- and return no rows at all if none "
    "matches. When the request names one table, by its number or caption, and this is a different table, "
    "return no rows. A header or a total is not an item. Give one value per column, in the order the columns are "
    "listed. Quote each value exactly as the table writes it, in the language of the table -- do not "
    "translate, summarise or infer. Leave a value empty when the table does not state it; never fill it "
    "with a guess or with words like \"not stated\"."
)

SCOPE = (
    "You decide which parts of a document a table has to be read from. You get the request for the "
    "table and the document's parts, numbered, each with its heading, how it begins and the captions of "
    "any tables it holds. Return the "
    "numbers of every part that could state an item the request asks for. Leave out parts that only "
    "mention such items in passing, as examples of something else, or in a list that answers a "
    "different question. When the request asks for every item of its kind anywhere in the document, "
    "or you cannot tell, return every part."
)

MERGE = (
    "You are given the numbered rows of one table, each pulled out of a different passage of the same "
    "document. Find the rows that describe the same item -- the same obligation, party, date or "
    "amount, mentioned in more than one place -- and return them as groups of row numbers. Only group "
    "rows that are truly one item: two similar but separate items stay apart. Leave out every row "
    "that has no duplicate."
)
