# tmux key bindings

A basic Python application that populates an SQLite database with the key
bindings and descriptions in the tmux manual's **DEFAULT KEY BINDINGS** section.

## Run

Requires mise and uv. The project uses mise-managed Python 3.13 and only the
Python standard library.

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
