Infer the most likely target audience and whether the document speaks to that audience clearly.
Return JSON with a top-level "findings" array.
Each finding must include excerpt, rationale, confidence, and suggestion.
The excerpt must copy the article text exactly, word for word.
Do not paraphrase, summarize, or fuse separate passages into one quote.
Use ellipses only when omitting real article text, and keep all remaining quoted fragments in the original order.
Do not use ellipses to hide rewritten or invented wording.
If the evidence would span more than 3 paragraphs, split it into multiple findings.
