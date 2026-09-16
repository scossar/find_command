# tmux key bindings

A basic Python application that populates an SQLite database with the key
bindings and descriptions in the tmux manual's **DEFAULT KEY BINDINGS** section.

## Run

Requires mise and uv. The project uses mise-managed Python 3.13. SQLite examples
use the standard library; the embedding example also requires Chroma, installed
by `uv sync --locked`.

Set up the tools and virtual environment from the project directory:

```sh
mise trust
mise install
mise exec -- uv sync --locked
```

The mise configuration selects Python and uv, points uv at mise's Python, and
automatically activates `.venv` when mise shell integration is enabled.

Run the application:

```sh
uv run populate.py
```

This creates `tmux_key_bindings.sqlite3` in the current directory. To choose
another file (its parent directory must exist):

```sh
uv run populate.py /tmp/tmux.sqlite3
```

Running it again updates existing entries without duplicating them.

## Search

Search descriptions for a substring:

```sh
uv run search.py pane
uv run search.py "current window"
uv run search.py pane --database /tmp/tmux.sqlite3
```

Each matching key and description is printed on one line. If nothing matches,
the command prints `No matches found.` The database must already be populated.

The query uses `LIKE '%query%'` with a bound SQL parameter. Multiple words match
as one continuous substring. `%` and `_` in the input retain their SQL wildcard
meaning. Results have no relevance ranking or guaranteed order. The database
is opened read-only.

## Full-text search demonstration

```sh
uv run search_fts.py "select window"
uv run search_fts.py "window select" --database /tmp/tmux.sqlite3
```

`search_fts.py` demonstrates FTS5 with the `porter unicode61` tokenizer:

- Text is split into word tokens, and English word forms are stemmed so that
  `select` matches `selected`.
- The input is split into alphanumeric words, with punctuation and underscores
  acting as separators. Each word is quoted and joined with `AND`, producing
  `"select" AND "window"`. FTS operators in user input are treated as words.
- All query words must match somewhere in the description, in any order.

The example matches both `Move to the previously selected window.` and
`Select the next pane in the current window.` Results follow database ID order;
this example does not rank them by relevance.

For demonstration, the script builds a temporary FTS index from the populated
database on each run. The source database is opened read-only, and the index
disappears when the connection closes. A persistent index maintained when data
changes would avoid rebuilding it for every search. Python's SQLite library
must include FTS5 support. No additional Python dependencies are needed.

## FTS5 query syntax

`search_fts_query.py` passes your query unchanged to FTS5's `MATCH` operator:

```sh
uv run search_fts_query.py 'window AND pane'
uv run search_fts_query.py 'window OR pane'
uv run search_fts_query.py '"window pane"'
uv run search_fts_query.py '"current window"'
uv run search_fts_query.py 'window NOT pane'
uv run search_fts_query.py '(window OR session) AND select'
uv run search_fts_query.py 'NEAR(window pane, 5)'
uv run search_fts_query.py 'win*'
uv run search_fts_query.py 'description : ^select'
```

The outer single quotes protect the query from the shell. Inner double quotes
are passed to FTS5 and specify a phrase. Boolean operators are uppercase.
Invalid FTS5 syntax produces an error message and a nonzero exit status.

This command keeps Porter stemming, the temporary index, and database ID
ordering from the previous example. Only `description` is indexed; `key` is
returned for display. SQL parameter binding is still used, but the query is
not split into words or rewritten. Use `--database PATH` for another populated
database. A valid query with no results prints `No matches found.`

## Persistent FTS5 table

After populating the database, create a persistent index:

```sh
uv run create_fts.py
# Or select another populated database:
uv run create_fts.py /tmp/tmux.sqlite3
```

`create_fts.py` creates `main.key_bindings_fts` with Porter stemming and copies
the keys and descriptions into it. The table and index remain in the database
after the script exits. Each run replaces the FTS contents from `key_bindings`
in one transaction, so rerunning it refreshes the index without duplicates.
It does not modify the source table.

Query it from a new SQLite CLI session:

```sh
sqlite3 tmux_key_bindings.sqlite3
```

```sql
SELECT key, description
FROM main.key_bindings_fts
WHERE key_bindings_fts MATCH 'select AND window'
ORDER BY rowid;
```

Run `create_fts.py` again after changing or repopulating `key_bindings`; updates
are not synchronized automatically. `IF NOT EXISTS` preserves an existing
table's definition, so rerunning does not change its tokenizer. The earlier
search scripts still build their own temporary indexes for their demonstrations.

## BM25-ranked full-text search

After running `create_fts.py`, query the persistent index with BM25 ranking:

```sh
uv run search_bm25.py 'pane'
uv run search_bm25.py 'window OR pane'
uv run search_bm25.py '"current window"' --database /tmp/tmux.sqlite3
```

`search_bm25.py` passes the FTS5 query unchanged to `MATCH` and orders the
matching records by `bm25(key_bindings_fts)`. It prints the score, key, and
description for every match. SQLite's BM25 scores are negated, so lower (more
negative) scores rank first. Equal scores are ordered by row ID. Scores are
not confidence percentages and are not directly comparable to Chroma distances.

BM25 uses term frequency, how common a term is across the indexed records, and
document length to rank matches. It does not expand the candidate set: an `AND`
query still requires both terms, while `OR` allows either. Porter stemming
comes from the persistent table's tokenizer configuration.

The command opens SQLite read-only and does not create or refresh the index.
Run `create_fts.py` again after changing the source data. Missing tables and
invalid query syntax produce errors; valid queries with no matches print
`No matches found.`

## Generate embeddings with Chroma

After populating SQLite, run:

```sh
uv sync --locked
uv run create_embeddings.py
```

To choose the source database, output directory, or collection:

```sh
uv run create_embeddings.py --database /tmp/tmux.sqlite3 \
  --chroma /tmp/tmux-chroma --collection tmux-key-bindings
```

`create_embeddings.py` reads the original descriptions from SQLite, explicitly
generates embeddings, and stores both the vectors and descriptions in a local,
persistent Chroma collection. It uses Chroma's default `all-MiniLM-L6-v2` model,
which runs locally via ONNX. The first use downloads model files if they are
not already cached. No API key or embedding service is required.

Each record includes its key binding, prefix, SQLite ID, tmux version, and source
as metadata. Only the description is embedded, without stemming. IDs are based
on the unique, case-sensitive key binding. Use a separate collection for a
different dataset.

The default output directory is `data/chroma/` (ignored by Git), and the default
collection is `tmux-key-bindings`. Chroma persists writes automatically. Repeated
runs regenerate embeddings and upsert records without duplicates. This initial
example does not remove records deleted from SQLite or skip unchanged records.
Batches are written separately; a failed run may have saved earlier batches,
and can be rerun. An empty source leaves the collection unchanged.

The embedding script only generates and stores embeddings. The SQLite source
and FTS tables are unchanged.

## Semantic search

After running `create_embeddings.py`, query the existing Chroma collection:

```sh
uv run search_chroma.py 'close the current window'
uv run search_chroma.py 'make a new terminal' --results 3
uv run search_chroma.py 'switch panes' --chroma /tmp/tmux-chroma \
  --collection tmux-key-bindings
```

The query is embedded with the same local model as the descriptions. Chroma
returns the nearest stored vectors, and the command prints their key bindings,
descriptions, and distances, closest first. Lower distances mean closer vectors;
they are not confidence percentages. This is natural-language search, so `AND`,
`OR`, and quotes do not act as FTS5 operators.

The default is five results, capped at the collection size. There is no relevance
threshold: a nonempty collection returns nearest neighbors even for an unrelated
query. The command uses the existing collection and does not regenerate stored
embeddings. To include changed SQLite descriptions, rerun `create_embeddings.py`.

## FTS5 candidates followed by semantic ranking

With both `create_fts.py` and `create_embeddings.py` run on the same source:

```sh
uv run search_fts_semantic.py 'window' 'close the current window'
uv run search_fts_semantic.py 'pane' 'make more room' --results 3
uv run search_fts_semantic.py 'window OR pane' 'switch to the previous one'
```

The first argument is an FTS5 expression; the second is a natural-language
semantic query. The Python `search` function accepts both queries separately,
along with the SQLite path, Chroma path, collection name, and result limit.
The command also supports `--database`, `--chroma`, and `--collection`.

All FTS matches become candidates. Their IDs restrict Chroma's vector search
before retrieval, and semantic distance alone determines the final order.
BM25 scores are not used, and `--results` limits only the final output. Lower
distances rank first. No FTS matches means no results, with no semantic fallback.

For example, `'window' 'close the current window'` can return “Kill the current
window.” Requiring `'close AND window'` excludes it before semantic ranking can
help. This demonstrates the candidate filter's effect on what can be retrieved.

Keep both indexes current by rerunning their creation scripts after source
changes. Missing candidate IDs in Chroma produce an error rather than silently
dropping candidates; changed descriptions with existing IDs are not detected.

## Reciprocal Rank Fusion (RRF)

With both persistent indexes populated, run:

```sh
uv run search_rrf.py 'close the window'
uv run search_rrf.py 'close the window' --candidates 10 --results 5 --k 60
```

`search_rrf.py` reuses the BM25 and Chroma search functions. It splits the input
into alphanumeric words and OR-joins them for FTS5: `close the window` becomes
`"close" OR "the" OR "window"`. Quotes preserve literal words, including words
that resemble FTS operators. Punctuation and underscores separate words. Common
words such as `the` are retained. Chroma receives the original input unchanged.

The searches run independently. Up to `--candidates` entries from each ranked
list contribute to the union of results, deduplicated by case-sensitive key.
For each record, the score is the sum of `1 / (k + rank)` from the lists where
it appears. Ranks start at 1; absence contributes zero. Both lists have equal
weight, and raw BM25 scores and vector distances are not combined.

Higher RRF scores rank first; ties use key order. Output includes the generated
FTS query, fused score, and rank in each source list (`-` means absent from that
list's candidate window). The default is 20 candidates per list and five final
results. `k` defaults to 60; larger values reduce differences between rank
contributions. These scores are not probabilities.

The lexical helper currently retrieves all FTS matches before slicing to the
candidate limit in Python; a larger-scale implementation could apply that limit
in SQL. Changing the candidate limit can change the fused ranking. Semantic-only
results remain eligible even when FTS5 has no matches.

Use `--database`, `--chroma`, and `--collection` to select matching indexes.
Refresh both after source changes. When a key appears in both lists, its displayed
description comes from FTS5; this example does not detect stale index contents.

## RRF with stop words excluded

`search_rrf_stop_words.py` is a separate version of the RRF example with a
`STOP_WORDS` set applied to the FTS5 query:

```sh
uv run search_rrf_stop_words.py 'close the window'
```

The generated FTS5 query is `"close" OR "window"`. Stop-word matching is
case-insensitive and uses whole extracted words. The original query, including
stop words, still goes to Chroma. The stored FTS index is unchanged.

The command supports the same options, ranking formula, and output as
`search_rrf.py`. If every input word is excluded, it skips FTS5 and fuses only
the semantic results. Empty or punctuation-only input remains an error.

## RRF with stop words and term substitutions

`search_rrf_substitutions.py` adds a `SUBSTITUTIONS` dictionary to the stop-word
example, initially mapping `close` to `kill`, and `bigger` and `smaller` to
`resize`:

```sh
uv run search_rrf_substitutions.py 'close the window'
uv run search_rrf_substitutions.py 'make the pane bigger'
```

The first example generates `"kill" OR "window"` for FTS5; the second generates
`"make" OR "pane" OR "resize"`. Stop words are removed first, then remaining
words are substituted using case-insensitive, whole-word dictionary lookup.
Unmapped words are preserved. Substitutions replace terms rather than adding
alternatives, and do not chain. For example, `closed` is not replaced by the
`close` mapping: this step happens before FTS5 applies stemming.

Chroma receives the original query unchanged. The script supports the same
options and RRF behavior as the other examples, including semantic-only results
when all words are filtered out. Edit `SUBSTITUTIONS` to experiment with other
single-word replacements. The previous examples remain separate for comparison.

## FTS5 vocabulary and missing terms

After creating the persistent FTS5 index:

```sh
uv run create_fts_vocab.py
uv run search_fts_vocab.py 'selected window nonexistentword'
```

`create_fts_vocab.py` creates `key_bindings_vocab` using
`fts5vocab(key_bindings_fts, row)`. It exposes the current index directly, so
there is no vocabulary data to populate or refresh separately. Its columns are
`term` (indexed token), `doc` (number of records containing it), and `cnt`
(total occurrences). The table persists and reflects subsequent FTS index changes.

`search_fts_vocab.search(connection, terms)` returns `(results, missing)`:
BM25-ranked `(key, description, score)` rows and a set of missing original terms.
Inputs are individual words; the CLI splits text into words and OR-joins them.
It does not apply stop words or substitutions. Missing means absent from the
entire FTS index, not merely absent from the top results.

The vocabulary contains stems. To avoid reporting `selected` as missing when
`select` exists, the search example normalizes terms using SQLite's own
`porter unicode61` tokenizer in a small, separate in-memory FTS table. This
matches the configuration in `create_fts.py`; update both if you change the
index tokenizer. Original spellings are preserved in the missing-term set.
The function accepts an empty list (returning empty results and an empty set)
and rejects terms that tokenize to zero or multiple words.

For manual inspection:

```sql
SELECT term, doc, cnt FROM key_bindings_vocab ORDER BY term;
```

The setup script accepts a positional database path; the search command uses
`--database PATH`. Searches leave the persistent database unchanged.

## Data

`data/tmux_key_bindings.json` contains 54 entries transcribed from the local
tmux 3.7c manual (`/usr/share/man/man1/tmux.1.gz`). It is a bundled snapshot;
running the app does not require tmux or read your tmux configuration.

Each row in the `key_bindings` table contains:

- `id`: integer primary key.
- `key`: command key or group of keys, unique and case-sensitive.
- `description`: the manual's description.
- `prefix`: the default prefix, `C-b`.
- `tmux_version`: the source manual's version, `3.7c`.
- `source`: the manual and section name.

Grouped entries such as `0 to 9` and the arrow keys remain grouped as in the
manual. Press the prefix before the command key: the `c` entry means `Ctrl-b`,
then `c`. `C-` means Control and `M-` means Meta (usually Alt).

The dataset covers that section only; separate copy-mode and other mode-specific
tables elsewhere in the manual are outside this initial dataset.
