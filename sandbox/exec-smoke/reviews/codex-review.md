PASS-with-nits

Correctness notes:
- Counts `notes.md` correctly for whitespace-delimited words and resolves the data path relative to the script location.

Style nits:
- The word definition is implicit; if punctuation-sensitive counting is ever needed, document or replace `str.split()`.
