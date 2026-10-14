"""Prompts for answering a question about a document."""

ANSWER = (
    "You answer questions about a document using only the numbered context blocks. "
    "Cite blocks inline as [n]. If the context does not contain the answer, say so. "
    "Answer in the same language as the question."
)

# Queries go in the document's language when known: fulltext, outline and entity names only match the
# document's own words (only the embeddings are multilingual)
QUESTION_LANGUAGE = (
    "Write every query in the SAME language as the latest question: an English question gives English "
    "queries, an Indonesian question gives Indonesian queries, whatever language the examples below are in."
)

DOCUMENT_LANGUAGE = (
    "The document is written in {language}. Write every query in {language}, translating the question when "
    "it is asked in another language, whatever language the examples below are in. Keep names, numbers and "
    "terms the question quotes exactly as written."
)

KEEP_QUESTION_LANGUAGE = "Keep the language of the question. "

KEEP_DOCUMENT_LANGUAGE = "Keep the meaning of the question. "

CONTEXTUALIZE = (
    "You turn the latest question into search queries for a document. {language_rule} Follow these "
    "rules in order.\n"
    "1. Make it standalone, so it makes sense without the earlier conversation: resolve pronouns and "
    "references like \"that\", \"the second one\", or \"the third one\" using the conversation history "
    "-- if the previous answer contains a numbered or bulleted list, an ordinal reference points at "
    "that specific item: put its actual content in the query, don't just say \"the Nth item\".\n"
    "2. A comparison ALWAYS becomes one question per thing being compared. That is any question with "
    "\"bandingkan\", \"perbandingan\", \"perbedaan\", \"beda\", \"lebih ... dari\", \"compare\", "
    "\"comparison\", \"difference\", \"versus\", \"vs\", or \"X or Y, which\". Each question names "
    "exactly ONE of the things and asks ALL the aspects the user asked about for that one thing, "
    "together in one question: split by thing, never by aspect. The "
    "comparison word never appears in them: \"perbedaan X\" or \"compare X\" is not a question about X. "
    "When no aspect is named (\"apa perbedaan X dan Y\", \"bandingkan keduanya\"), ask what the "
    "document says about each one.\n"
    "3. A question about several unrelated topics joined by \"dan\", \"serta\", \"and\" also becomes "
    "one question per topic.\n"
    "4. Never more than {max_queries} questions. A question about one thing stays one question, "
    "unchanged if it is already standalone.\n"
    "5. {keep_language}Never answer it, add facts, or add topics it does not ask "
    "about.\n\n"
    "Examples:\n"
    "- History has \"3. Structured content yields big gains\"; \"what about the third one?\" -> "
    "[\"What does it mean that structured content yields big gains?\"]\n"
    "- \"Bandingkan akurasi dan kecepatan model A dengan model B\" -> [\"Berapa akurasi dan kecepatan "
    "model A?\", \"Berapa akurasi dan kecepatan model B?\"]\n"
    "- \"Apa perbedaan Perda 13/2018 dan Perda 3/2023?\" -> [\"Apa yang dijelaskan tentang Perda "
    "13/2018?\", \"Apa yang dijelaskan tentang Perda 3/2023?\"]\n"
    "- History lists \"1. Paket A 2. Paket B\"; \"bandingkan keduanya\" -> [\"Apa yang dijelaskan "
    "tentang Paket A?\", \"Apa yang dijelaskan tentang Paket B?\"]\n"
    "- \"Mana yang lebih murah, paket A atau paket B?\" -> [\"Berapa harga paket A?\", \"Berapa harga "
    "paket B?\"]\n"
    "- \"Compare the cost and duration of plan A and plan B\" -> [\"What are the cost and duration of "
    "plan A?\", \"What are the cost and duration of plan B?\"]\n"
    "- \"Compare the penalties for the contractor vs the client\" -> [\"What penalties apply to the "
    "contractor?\", \"What penalties apply to the client?\"]\n"
    "- \"Siapa kontraktornya dan kapan tenggatnya?\" -> [\"Siapa kontraktornya?\", \"Kapan "
    "tenggatnya?\"]\n"
    "- \"Berapa nilai kontrak proyek ini?\" -> [\"Berapa nilai kontrak proyek ini?\"]"
)
