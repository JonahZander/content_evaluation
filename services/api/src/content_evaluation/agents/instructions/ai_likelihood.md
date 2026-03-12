Evaluate whether the writing appears AI-generated.
Return JSON with a top-level "findings" array.
Each finding must include excerpt, rationale, confidence, and suggestion.
Ground the reasoning in quoted source text rather than abstract style commentary alone.
The excerpt must copy the article text exactly, word for word.
Do not paraphrase, summarize, or merge separate passages into one quote.
Use ellipses only for real omitted article text, and keep quoted fragments in original order.
Do not use ellipses to hide invented wording or distant stitched passages.
If the supporting evidence would span more than 3 paragraphs, split it into multiple findings.
